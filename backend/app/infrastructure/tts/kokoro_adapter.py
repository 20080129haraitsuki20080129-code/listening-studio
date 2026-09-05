"""Kokoro-82M adapter -- local neural TTS, no API key required.

Runs on-device. Measured RTF ~0.22 on an Apple M1 once warm, so a five minute
passage renders in about a minute.

Two things matter for correctness here:

* Synthesis is synchronous and CPU-bound, so it must not run on the event
  loop. Every call goes through a thread.
* `KPipeline` is expensive to construct (2-6s) and is cached per language.
  The espeak paths must already be in the environment before kokoro is
  imported, which `Settings.apply_espeak_env()` handles at startup.
"""

from __future__ import annotations

import io
import time
from typing import Any

import anyio

from app.domain.errors import ProviderRequestFailed, ProviderUnavailable

from .base import (
    ProviderCapabilities,
    TTSProvider,
    TTSRequest,
    TTSResult,
    VoiceDescriptor,
)

SAMPLE_RATE = 24_000

# Kokoro voice ids encode language/accent and gender in their prefix:
# first char a=American b=British, second char f=female m=male. Reading that
# is derivation from a documented scheme, not invented metadata.
_ACCENT_BY_PREFIX = {"a": "american", "b": "british"}
_GENDER_BY_PREFIX = {"f": "female", "m": "male"}
_LOCALE_BY_ACCENT = {"american": "en-US", "british": "en-GB"}

ENGLISH_VOICE_IDS = (
    "af_alloy",
    "af_aoede",
    "af_bella",
    "af_heart",
    "af_jessica",
    "af_kore",
    "af_nicole",
    "af_nova",
    "af_river",
    "af_sarah",
    "af_sky",
    "am_adam",
    "am_echo",
    "am_eric",
    "am_fenrir",
    "am_liam",
    "am_michael",
    "am_onyx",
    "am_puck",
    "am_santa",
    "bf_alice",
    "bf_emma",
    "bf_isabella",
    "bf_lily",
    "bm_daniel",
    "bm_fable",
    "bm_george",
    "bm_lewis",
)


def describe_voice(voice_id: str) -> VoiceDescriptor:
    accent = _ACCENT_BY_PREFIX.get(voice_id[0])
    gender = _GENDER_BY_PREFIX.get(voice_id[1], "unknown")
    return VoiceDescriptor(
        provider_voice_id=voice_id,
        name=voice_id.split("_", 1)[-1].capitalize(),
        language="en",
        locale=_LOCALE_BY_ACCENT.get(accent or ""),
        accent=accent or "unknown",
        gender=gender,
        age_group="unknown",
        style_tags=["neural", "local"],
    )


class KokoroAdapter(TTSProvider):
    name = "kokoro"
    capabilities = ProviderCapabilities(
        supports_speed=True,
        # Kokoro accepts any positive float, but past this range prosody
        # degrades badly enough to be useless as listening material.
        speed_range=(0.5, 2.0),
        supports_instructions=False,
        native_formats=("wav",),
    )

    def __init__(self, repo_id: str = "hexgrad/Kokoro-82M") -> None:
        self._repo_id = repo_id
        self._pipelines: dict[str, Any] = {}

    def _pipeline(self, lang_code: str) -> Any:
        """Build (and cache) a KPipeline. Called only inside a worker thread."""
        if lang_code not in self._pipelines:
            try:
                from kokoro import KPipeline
            except ImportError as exc:  # pragma: no cover
                raise ProviderUnavailable(
                    "Kokoro is not installed on this server."
                ) from exc
            self._pipelines[lang_code] = KPipeline(
                lang_code=lang_code, repo_id=self._repo_id
            )
        return self._pipelines[lang_code]

    def _synthesize_blocking(self, request: TTSRequest) -> bytes:
        import numpy as np
        import soundfile as sf

        lang_code = request.provider_voice_id[0]
        pipeline = self._pipeline(lang_code)
        chunks = [
            audio
            for _, _, audio in pipeline(
                request.text,
                voice=request.provider_voice_id,
                speed=self.clamp_speed(request.speed),
            )
        ]
        if not chunks:
            raise ProviderRequestFailed("Kokoro produced no audio for this text.")

        audio = np.concatenate(chunks) if len(chunks) > 1 else chunks[0]
        buf = io.BytesIO()
        sf.write(buf, audio, SAMPLE_RATE, format="WAV", subtype="PCM_16")
        return buf.getvalue()

    async def synthesize(self, request: TTSRequest) -> TTSResult:
        started = time.perf_counter()
        try:
            audio_bytes = await anyio.to_thread.run_sync(
                self._synthesize_blocking, request
            )
        except ProviderRequestFailed:
            raise
        except Exception as exc:
            raise ProviderRequestFailed(f"Kokoro synthesis failed: {exc}") from exc

        # Always WAV here; the render pipeline transcodes to the requested
        # output format via FFmpeg.
        return TTSResult(
            audio_bytes=audio_bytes,
            mime_type="audio/wav",
            provider_request_id=None,
            provider_latency_ms=int((time.perf_counter() - started) * 1000),
        )

    async def healthcheck(self) -> bool:
        try:
            await anyio.to_thread.run_sync(self._pipeline, "a")
        except Exception:  # noqa: BLE001 - healthcheck reports, never raises
            return False
        return True

    async def list_voices(self) -> list[VoiceDescriptor]:
        return [describe_voice(v) for v in ENGLISH_VOICE_IDS]

    async def warmup(self) -> None:
        """Pay the lazy-init cost at startup instead of on the first request."""
        await anyio.to_thread.run_sync(self._pipeline, "a")
