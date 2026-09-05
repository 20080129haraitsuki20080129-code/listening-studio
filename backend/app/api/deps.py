"""Composition root.

Everything provider-specific is assembled here and injected downward, so route
handlers and services depend on interfaces rather than concrete adapters.
"""

from __future__ import annotations

import logging
import platform

from app.application.project_service import ProjectService
from app.application.render_service import RenderService
from app.application.tts_service import TTSService
from app.application.voice_service import VoiceService
from app.config import Settings, get_settings
from app.infrastructure.audio.ffmpeg import FFmpeg
from app.infrastructure.db.session import SessionLocal
from app.infrastructure.storage.local_storage import LocalStorage
from app.infrastructure.tts.registry import TTSProviderRegistry

log = logging.getLogger(__name__)


def build_registry(settings: Settings) -> TTSProviderRegistry:
    registry = TTSProviderRegistry()

    if settings.kokoro_enabled:
        from app.infrastructure.tts.kokoro_adapter import KokoroAdapter

        registry.register(KokoroAdapter(repo_id=settings.kokoro_repo_id))

    if settings.macos_say_enabled and platform.system() == "Darwin":
        from app.infrastructure.tts.macos_say_adapter import MacOSSayAdapter

        registry.register(MacOSSayAdapter())

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


class Container:
    def __init__(self, settings: Settings) -> None:
        self.settings = settings
        self.registry = build_registry(settings)
        self.storage = LocalStorage(settings.local_storage_path)
        self.ffmpeg = FFmpeg(settings.ffmpeg_bin, settings.ffprobe_bin)
        self.tts = TTSService(self.registry, self.storage, self.ffmpeg)
        self.voices = VoiceService(self.registry)
        self.projects = ProjectService()
        self.renders = RenderService(self.tts, self.ffmpeg, self.storage, SessionLocal)


_container: Container | None = None


def get_container() -> Container:
    global _container
    if _container is None:
        _container = Container(get_settings())
    return _container
