"""Application configuration.

Everything provider-specific lives here or in the adapter layer -- never in
domain or API code.
"""

from __future__ import annotations

import os
from functools import lru_cache
from pathlib import Path

from pydantic_settings import BaseSettings, SettingsConfigDict

# The dylib bundled with espeakng-loader has a build-machine path compiled into
# it and fails with "Error processing file '/Users/runner/work/.../phontab'".
# phonemizer's EspeakWrapper.set_data_path() only sets a class attribute and
# cannot override that, so we point at a real espeak-ng install instead.
_ESPEAK_LIBRARY_CANDIDATES = (
    "/opt/homebrew/lib/libespeak-ng.dylib",  # macOS, Apple Silicon
    "/usr/local/lib/libespeak-ng.dylib",  # macOS, Intel
    "/usr/lib/x86_64-linux-gnu/libespeak-ng.so.1",  # Debian/Ubuntu
    "/usr/lib/libespeak-ng.so.1",
)
_ESPEAK_DATA_CANDIDATES = (
    "/opt/homebrew/share/espeak-ng-data",
    "/usr/local/share/espeak-ng-data",
    "/usr/lib/x86_64-linux-gnu/espeak-ng-data",
    "/usr/share/espeak-ng-data",
)


def _first_existing(candidates: tuple[str, ...]) -> str | None:
    return next((c for c in candidates if Path(c).exists()), None)


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_file=".env", env_file_encoding="utf-8", extra="ignore"
    )

    database_url: str = (
        "postgresql+psycopg://listening:listening@localhost:5432/listening_studio"
    )

    storage_backend: str = "local"
    local_storage_path: Path = Path("./data/audio")

    kokoro_enabled: bool = True
    kokoro_repo_id: str = "hexgrad/Kokoro-82M"

    phonemizer_espeak_library: str = ""
    espeak_data_path: str = ""

    macos_say_enabled: bool = True

    openai_api_key: str = ""
    openai_tts_model: str = "gpt-4o-mini-tts"
    azure_speech_key: str = ""
    azure_speech_region: str = ""
    elevenlabs_api_key: str = ""

    app_env: str = "development"
    log_level: str = "INFO"
    max_script_chars: int = 50_000
    max_segment_chars: int = 3_500

    ffmpeg_bin: str = "ffmpeg"
    ffprobe_bin: str = "ffprobe"

    def resolve_espeak(self) -> tuple[str | None, str | None]:
        """Return (library_path, data_path), auto-detecting when unset."""
        lib = self.phonemizer_espeak_library or _first_existing(
            _ESPEAK_LIBRARY_CANDIDATES
        )
        data = self.espeak_data_path or _first_existing(_ESPEAK_DATA_CANDIDATES)
        return lib, data

    def apply_espeak_env(self) -> None:
        """Export espeak paths so phonemizer picks them up at import time.

        Must run before anything imports kokoro/misaki.
        """
        lib, data = self.resolve_espeak()
        if lib:
            os.environ.setdefault("PHONEMIZER_ESPEAK_LIBRARY", lib)
        if data:
            os.environ.setdefault("ESPEAK_DATA_PATH", data)


@lru_cache
def get_settings() -> Settings:
    return Settings()
