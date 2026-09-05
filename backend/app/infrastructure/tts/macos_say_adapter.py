"""macOS `say` adapter -- local, offline, no API key.

Kokoro only covers American and British English. This adapter exists to make
the accent filter meaningful: macOS ships voices for en-GB, en-AU, en-IE,
en-IN, en-ZA and en-US, and the accent comes from the OS-reported locale
rather than from guessing.

Only available on macOS.
"""

from __future__ import annotations

import platform
import re
import shutil
import subprocess
import tempfile
import time
from pathlib import Path

import anyio

from app.domain.errors import ProviderRequestFailed, ProviderUnavailable

from .base import (
    ProviderCapabilities,
    TTSProvider,
    TTSRequest,
    TTSResult,
    VoiceDescriptor,
)

_LOCALE_TO_ACCENT = {
    "en_US": "american",
    "en_GB": "british",
    "en_AU": "australian",
    "en_IE": "irish",
    "en_IN": "indian",
    "en_ZA": "south_african",
    "en_NZ": "new_zealand",
    "en_CA": "canadian",
    "en_SC": "scottish",
}

# `say` ships a set of novelty voices (Bells, Zarvox, ...) that are useless
# as listening material. Only real speech voices are catalogued.
_NOVELTY_VOICES = frozenset(
    {
        "Albert",
        "Bad News",
        "Bahh",
        "Bells",
        "Boing",
        "Bubbles",
        "Cellos",
        "Deranged",
        "Good News",
        "Jester",
        "Junior",
        "Kathy",
        "Organ",
        "Superstar",
        "Trinoids",
        "Whisper",
        "Wobble",
        "Zarvox",
        "Bruce",
        "Hysterical",
        "Pipe Organ",
        "Princess",
        "Ralph",
        "Fred",
    }
)

# `say -r` is words per minute. 175 is roughly the default cadence, so
# generation_speed scales from there.
_BASE_WPM = 175

_VOICE_LINE = re.compile(r"^(?P<name>.+?)\s{2,}(?P<locale>[a-z]{2}_[A-Z]{2})\s")


class MacOSSayAdapter(TTSProvider):
    name = "macos_say"
    capabilities = ProviderCapabilities(
        supports_speed=True,
        speed_range=(0.5, 2.0),
        supports_instructions=False,
        native_formats=("aiff",),
    )

    @staticmethod
    def is_available() -> bool:
        return platform.system() == "Darwin" and shutil.which("say") is not None

    def _synthesize_blocking(self, request: TTSRequest) -> bytes:
        rate = int(_BASE_WPM * self.clamp_speed(request.speed))
        with tempfile.TemporaryDirectory() as tmp:
            out = Path(tmp) / "out.aiff"
            proc = subprocess.run(
                [
                    "say",
                    "-v",
                    request.provider_voice_id,
                    "-r",
                    str(rate),
                    "-o",
                    str(out),
                    request.text,
                ],
                capture_output=True,
                timeout=120,
                check=False,
            )
            if proc.returncode != 0 or not out.exists():
                detail = proc.stderr.decode("utf-8", "replace").strip()
                raise ProviderRequestFailed(f"`say` failed: {detail}")
            return out.read_bytes()

    async def synthesize(self, request: TTSRequest) -> TTSResult:
        if not self.is_available():
            raise ProviderUnavailable("`say` is only available on macOS.")
        started = time.perf_counter()
        try:
            audio_bytes = await anyio.to_thread.run_sync(
                self._synthesize_blocking, request
            )
        except ProviderRequestFailed:
            raise
        except Exception as exc:
            raise ProviderRequestFailed(f"`say` synthesis failed: {exc}") from exc
        return TTSResult(
            audio_bytes=audio_bytes,
            mime_type="audio/aiff",
            provider_latency_ms=int((time.perf_counter() - started) * 1000),
        )

    async def healthcheck(self) -> bool:
        return self.is_available()

    def _list_voices_blocking(self) -> list[VoiceDescriptor]:
        proc = subprocess.run(
            ["say", "-v", "?"], capture_output=True, timeout=30, check=False
        )
        if proc.returncode != 0:
            return []

        voices: list[VoiceDescriptor] = []
        for line in proc.stdout.decode("utf-8", "replace").splitlines():
            match = _VOICE_LINE.match(line)
            if not match:
                continue
            name = match.group("name").strip()
            locale = match.group("locale")
            if not locale.startswith("en_") or name in _NOVELTY_VOICES:
                continue
            voices.append(
                VoiceDescriptor(
                    provider_voice_id=name,
                    name=name,
                    language="en",
                    locale=locale.replace("_", "-"),
                    accent=_LOCALE_TO_ACCENT.get(locale, "unknown"),
                    # macOS does not report gender, and inferring it from a
                    # first name would be fabricating metadata (API.md).
                    gender="unknown",
                    age_group="unknown",
                    style_tags=["system", "local"],
                )
            )
        return voices

    async def list_voices(self) -> list[VoiceDescriptor]:
        if not self.is_available():
            return []
        return await anyio.to_thread.run_sync(self._list_voices_blocking)
