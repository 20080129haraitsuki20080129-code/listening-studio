from __future__ import annotations

import logging
from contextlib import asynccontextmanager

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from starlette.middleware.sessions import SessionMiddleware

from app.config import get_settings

# espeak paths must be in the environment before anything imports kokoro.
get_settings().apply_espeak_env()

from app.api.deps import get_container  # noqa: E402
from app.api.errors import register_error_handlers, request_id_middleware  # noqa: E402
from app.api.routes import (  # noqa: E402
    auth,
    health,
    projects,
    renders,
    segments,
    voices,
)

log = logging.getLogger(__name__)

API_PREFIX = "/api/v1"


DEFAULT_SESSION_SECRET = "dev-only-insecure-secret-change-me"


def _guard_production_secrets(settings) -> None:
    """Refuse to start a production server that anyone could forge sessions on.

    Failing loudly at boot is far better than serving traffic with a signing
    key that is published in the repository.
    """
    if settings.app_env != "production":
        return
    problems = []
    if settings.session_secret == DEFAULT_SESSION_SECRET:
        problems.append("SESSION_SECRET is still the development default")
    if len(settings.session_secret) < 32:
        problems.append("SESSION_SECRET is shorter than 32 characters")
    if not settings.cookie_secure:
        problems.append("COOKIE_SECURE must be true when served over HTTPS")
    if problems:
        raise RuntimeError("Refusing to start in production: " + "; ".join(problems))


@asynccontextmanager
async def lifespan(app: FastAPI):
    settings = get_settings()
    _guard_production_secrets(settings)
    logging.basicConfig(
        level=settings.log_level,
        format="%(asctime)s %(levelname)-5s [%(name)s] %(message)s",
    )
    container = get_container()

    # Pay Kokoro's lazy initialization cost now: the first synthesis is
    # otherwise 3-4s slower than every later one.
    if "kokoro" in container.registry:
        try:
            await container.registry.get("kokoro").warmup()
            log.info("Kokoro warmed up")
        except Exception as exc:  # noqa: BLE001 - startup must not hard-fail
            log.warning("Kokoro warmup failed: %s", exc)

    yield


app = FastAPI(title="Listening Studio API", version="0.1.0", lifespan=lifespan)

_settings = get_settings()

# Authlib keeps the OAuth state and PKCE verifier here between the redirect out
# and the callback back.
app.add_middleware(
    SessionMiddleware,
    secret_key=_settings.session_secret,
    same_site="lax",
    https_only=_settings.cookie_secure,
)

app.add_middleware(
    CORSMiddleware,
    # The browser sends the session cookie, so the origin has to be named
    # exactly -- a wildcard is not allowed with credentials.
    allow_origins=sorted(
        {
            "http://localhost:3000",
            "http://127.0.0.1:3000",
            _settings.frontend_base_url,
        }
    ),
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
    expose_headers=["X-Request-ID"],
)
app.middleware("http")(request_id_middleware)
register_error_handlers(app)

for module in (health, auth, voices, projects, segments, renders):
    app.include_router(module.router, prefix=API_PREFIX)
