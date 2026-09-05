from __future__ import annotations

import logging
from contextlib import asynccontextmanager

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from app.config import get_settings

# espeak paths must be in the environment before anything imports kokoro.
get_settings().apply_espeak_env()

from app.api.deps import get_container  # noqa: E402
from app.api.errors import register_error_handlers, request_id_middleware  # noqa: E402
from app.api.routes import health, projects, renders, segments, voices  # noqa: E402

log = logging.getLogger(__name__)

API_PREFIX = "/api/v1"


@asynccontextmanager
async def lifespan(app: FastAPI):
    settings = get_settings()
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

app.add_middleware(
    CORSMiddleware,
    allow_origins=["http://localhost:3000", "http://127.0.0.1:3000"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
    expose_headers=["X-Request-ID"],
)
app.middleware("http")(request_id_middleware)
register_error_handlers(app)

for module in (health, voices, projects, segments, renders):
    app.include_router(module.router, prefix=API_PREFIX)
