"""Composition root.

Everything provider-specific is assembled here and injected downward, so route
handlers and services depend on interfaces rather than concrete adapters.
"""

from __future__ import annotations

import logging

from fastapi import Depends, Request
from sqlalchemy.ext.asyncio import AsyncSession

from app.application.auth_service import AuthService
from app.application.project_service import ProjectService
from app.application.render_service import RenderService
from app.application.tts_service import TTSService
from app.application.voice_service import VoiceService
from app.config import Settings, get_settings
from app.domain.auth import NotAuthenticated, read_session
from app.infrastructure.audio.ffmpeg import FFmpeg
from app.infrastructure.auth.oauth import build_oauth
from app.infrastructure.db.models import User
from app.infrastructure.db.session import SessionLocal, get_session
from app.infrastructure.storage.base import StorageBackend
from app.infrastructure.storage.local_storage import LocalStorage
from app.infrastructure.tts.registry import TTSProviderRegistry

log = logging.getLogger(__name__)


def build_registry(settings: Settings) -> TTSProviderRegistry:
    registry = TTSProviderRegistry()

    if settings.kokoro_enabled:
        from app.infrastructure.tts.kokoro_adapter import KokoroAdapter

        registry.register(KokoroAdapter(repo_id=settings.kokoro_repo_id))

    # Hosted providers register only when credentials exist, so an unset key
    # means "not offered" rather than a runtime failure mid-render.
    if settings.openai_api_key:
        from app.infrastructure.tts.openai_adapter import OpenAIAdapter

        registry.register(
            OpenAIAdapter(
                api_key=settings.openai_api_key, model=settings.openai_tts_model
            )
        )
    if settings.azure_speech_key and settings.azure_speech_region:
        from app.infrastructure.tts.azure_adapter import AzureAdapter

        registry.register(
            AzureAdapter(
                api_key=settings.azure_speech_key, region=settings.azure_speech_region
            )
        )
    if settings.elevenlabs_api_key:
        from app.infrastructure.tts.elevenlabs_adapter import ElevenLabsAdapter

        registry.register(ElevenLabsAdapter(api_key=settings.elevenlabs_api_key))

    log.info("TTS providers registered: %s", ", ".join(registry.names()) or "none")
    return registry


def build_storage(settings: Settings) -> StorageBackend:
    """Pick a storage backend from configuration.

    Object storage matters wherever the filesystem does not survive a restart,
    which is most free hosting. Local disk stays the default for development.
    """
    if settings.storage_backend != "s3":
        return LocalStorage(settings.local_storage_path)

    missing = [
        name
        for name, value in (
            ("S3_BUCKET", settings.s3_bucket),
            ("S3_ENDPOINT_URL", settings.s3_endpoint_url),
            ("S3_ACCESS_KEY_ID", settings.s3_access_key_id),
            ("S3_SECRET_ACCESS_KEY", settings.s3_secret_access_key),
        )
        if not value
    ]
    if missing:
        # Falling back to disk here would look like it worked and then lose
        # every render when the container restarts.
        raise RuntimeError(
            "STORAGE_BACKEND=s3 but these are unset: " + ", ".join(missing)
        )

    from app.infrastructure.storage.s3_storage import S3Storage

    log.info("Using S3-compatible storage at %s", settings.s3_endpoint_url)
    return S3Storage(
        bucket=settings.s3_bucket,
        endpoint_url=settings.s3_endpoint_url,
        access_key=settings.s3_access_key_id,
        secret_key=settings.s3_secret_access_key,
        region=settings.s3_region,
        public_base_url=settings.s3_public_base_url,
    )


class Container:
    def __init__(self, settings: Settings) -> None:
        self.settings = settings
        self.registry = build_registry(settings)
        self.storage = build_storage(settings)
        self.ffmpeg = FFmpeg(settings.ffmpeg_bin, settings.ffprobe_bin)
        self.tts = TTSService(self.registry, self.storage, self.ffmpeg)
        self.voices = VoiceService(self.registry)
        self.projects = ProjectService()
        self.auth = AuthService()
        self.oauth = build_oauth(settings)
        self.renders = RenderService(self.tts, self.ffmpeg, self.storage, SessionLocal)


_container: Container | None = None


def get_container() -> Container:
    global _container
    if _container is None:
        _container = Container(get_settings())
    return _container


async def get_current_user(
    request: Request,
    session: AsyncSession = Depends(get_session),
    container: Container = Depends(get_container),
) -> User | None:
    """The signed-in user, or None.

    Returns None rather than raising so callers can distinguish "not signed in"
    from "signed in but not allowed".
    """
    token = request.cookies.get(container.settings.session_cookie_name)
    if not token:
        return None
    try:
        claims = read_session(token, container.settings.session_secret)
    except NotAuthenticated:
        return None
    return await session.get(User, claims.user_id)


async def require_user(
    user: User | None = Depends(get_current_user),
    container: Container = Depends(get_container),
) -> User | None:
    """Enforce sign-in wherever a provider is configured.

    A checkout with no provider configured has no way to sign in at all, so
    enforcing it there would lock the developer out of their own machine.
    """
    if not container.settings.auth_required:
        return user
    if user is None:
        raise NotAuthenticated
    return user
