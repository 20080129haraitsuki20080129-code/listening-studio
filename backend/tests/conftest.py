from __future__ import annotations

import asyncio
from collections.abc import AsyncIterator

import pytest
import pytest_asyncio
from httpx import ASGITransport, AsyncClient
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine

from app.config import get_settings
from app.infrastructure.db.models import Base

TEST_DB_URL = get_settings().database_url + "_test"


@pytest.fixture(scope="session")
def event_loop():
    loop = asyncio.new_event_loop()
    yield loop
    loop.close()


@pytest_asyncio.fixture(scope="session")
async def engine():
    """Isolated test database, created and dropped around the session."""
    import psycopg

    admin_url = get_settings().database_url.replace(
        "postgresql+psycopg://", "postgresql://"
    )
    base_name = admin_url.rsplit("/", 1)[-1]
    admin_dsn = admin_url.rsplit("/", 1)[0] + "/postgres"

    with psycopg.connect(admin_dsn, autocommit=True) as conn:
        conn.execute(f'DROP DATABASE IF EXISTS "{base_name}_test"')
        conn.execute(f'CREATE DATABASE "{base_name}_test"')

    eng = create_async_engine(TEST_DB_URL, poolclass=None)
    async with eng.begin() as conn:
        await conn.exec_driver_sql("CREATE EXTENSION IF NOT EXISTS pgcrypto")
        await conn.run_sync(Base.metadata.create_all)
    yield eng
    await eng.dispose()

    with psycopg.connect(admin_dsn, autocommit=True) as conn:
        conn.execute(f'DROP DATABASE IF EXISTS "{base_name}_test"')


@pytest_asyncio.fixture
async def session(engine) -> AsyncIterator[AsyncSession]:
    factory = async_sessionmaker(engine, expire_on_commit=False)
    async with factory() as s:
        yield s
        await s.rollback()


@pytest_asyncio.fixture
async def client(engine) -> AsyncIterator[AsyncClient]:
    """App wired to the test DB, with a stub provider instead of real TTS.

    CI must never load Kokoro: it is slow and downloads a model.
    """
    from app.api import deps
    from app.infrastructure.db import session as session_module
    from app.infrastructure.tts.registry import TTSProviderRegistry

    from .stubs import StubTTSProvider

    factory = async_sessionmaker(engine, expire_on_commit=False)
    session_module.SessionLocal = factory

    container = deps.Container.__new__(deps.Container)
    container.settings = get_settings()
    container.registry = TTSProviderRegistry({"kokoro": StubTTSProvider()})

    from app.domain.rate_limit import SlidingWindowLimiter

    # A fresh limiter per test, so one test's requests cannot exhaust another's
    # allowance.
    container.limiter = SlidingWindowLimiter()

    import tempfile
    from pathlib import Path

    from app.application.project_service import ProjectService
    from app.application.render_service import RenderService
    from app.application.tts_service import TTSService
    from app.application.voice_service import VoiceService
    from app.infrastructure.audio.ffmpeg import FFmpeg
    from app.infrastructure.storage.local_storage import LocalStorage

    tmpdir = tempfile.mkdtemp(prefix="ls-test-")
    container.storage = LocalStorage(Path(tmpdir))
    container.ffmpeg = FFmpeg()
    container.tts = TTSService(container.registry, container.storage, container.ffmpeg)
    container.voices = VoiceService(container.registry)
    container.projects = ProjectService()
    from app.application.auth_service import AuthService

    container.auth = AuthService()
    container.renders = RenderService(
        container.tts, container.ffmpeg, container.storage, factory
    )

    deps._container = container

    from app.main import app

    async def _override_session():
        async with factory() as s:
            yield s

    app.dependency_overrides[session_module.get_session] = _override_session

    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test/api/v1") as c:
        yield c

    app.dependency_overrides.clear()
    deps._container = None
