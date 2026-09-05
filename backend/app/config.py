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

    # "local" writes to disk; "s3" talks to any S3-compatible store
    # (Supabase Storage, Cloudflare R2, Backblaze B2, S3 itself).
    storage_backend: str = "local"
    local_storage_path: Path = Path("./data/audio")

    s3_bucket: str = ""
    s3_endpoint_url: str = ""
    s3_access_key_id: str = ""
    s3_secret_access_key: str = ""
    s3_region: str = "auto"
    # Set only when the bucket serves objects publicly; otherwise the API
    # proxies them and the bucket stays private.
    s3_public_base_url: str = ""

    # Off by default. TASKS Phase 2 requires failover to be opt-in, because
    # silently swapping to an audibly different voice ruins listening material.
    tts_failover_enabled: bool = False

    kokoro_enabled: bool = True
    kokoro_repo_id: str = "hexgrad/Kokoro-82M"

    phonemizer_espeak_library: str = ""
    espeak_data_path: str = ""

    openai_api_key: str = ""
    openai_tts_model: str = "gpt-4o-mini-tts"
    azure_speech_key: str = ""
    azure_speech_region: str = ""
    elevenlabs_api_key: str = ""

    # ---- Authentication ----
    # Signs the session cookie. Must be set to a long random value in
    # production; a fixed default would let anyone forge a session.
    session_secret: str = "dev-only-insecure-secret-change-me"
    session_cookie_name: str = "listening_session"
    session_max_age_seconds: int = 60 * 60 * 24 * 14
    # Where the browser is sent back to after a provider redirect.
    frontend_base_url: str = "http://localhost:3000"
    # Cross-site cookies need SameSite=None; Secure, which requires HTTPS.
    cookie_secure: bool = False
    cookie_samesite: str = "lax"

    google_client_id: str = ""
    google_client_secret: str = ""
    x_client_id: str = ""
    x_client_secret: str = ""

    # Rate limits, sized so one person cannot exhaust a free tier's CPU,
    # storage or monthly egress. Set a limit to 0 to disable that rule.
    rate_limit_renders_per_hour: int = 60
    rate_limit_writes_per_minute: int = 60

    app_env: str = "development"
    log_level: str = "INFO"
    max_script_chars: int = 50_000
    max_segment_chars: int = 3_500

    ffmpeg_bin: str = "ffmpeg"
    ffprobe_bin: str = "ffprobe"

    @property
    def enabled_oauth_providers(self) -> list[str]:
        """Providers with credentials configured, in display order."""
        providers = []
        if self.google_client_id and self.google_client_secret:
            providers.append("google")
        if self.x_client_id and self.x_client_secret:
            providers.append("x")
        return providers

    @property
    def auth_required(self) -> bool:
        """Whether sign-in is enforced.

        With no provider configured there is no way to sign in, so requiring it
        would lock everyone out of a local checkout. Any configured provider
        turns enforcement on.
        """
        return bool(self.enabled_oauth_providers)

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
