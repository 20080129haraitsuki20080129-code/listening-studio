"""A silent-audio provider so tests exercise the pipeline without real TTS."""

from __future__ import annotations

import math
import struct

from app.infrastructure.tts.base import (
    ProviderCapabilities,
    TTSProvider,
    TTSRequest,
    TTSResult,
    VoiceDescriptor,
)

SAMPLE_RATE = 24_000


def _tone_wav(duration_s: float, freq: float = 220.0) -> bytes:
    frames = int(SAMPLE_RATE * duration_s)
    body = b"".join(
        struct.pack("<h", int(12000 * math.sin(2 * math.pi * freq * i / SAMPLE_RATE)))
        for i in range(frames)
    )
    header = (
        b"RIFF"
        + struct.pack("<I", 36 + len(body))
        + b"WAVEfmt "
        + struct.pack("<IHHIIHH", 16, 1, 1, SAMPLE_RATE, SAMPLE_RATE * 2, 2, 16)
        + b"data"
        + struct.pack("<I", len(body))
    )
    return header + body


class StubTTSProvider(TTSProvider):
    # Stands in for the real Kokoro adapter, so the production `provider`
    # CHECK constraint stays strict and the swap is a pure adapter swap.
    name = "kokoro"
    capabilities = ProviderCapabilities(
        supports_speed=True,
        speed_range=(0.5, 2.0),
        supports_instructions=False,
        native_formats=("wav",),
    )

    def __init__(self) -> None:
        self.calls: list[TTSRequest] = []

    async def synthesize(self, request: TTSRequest) -> TTSResult:
        self.calls.append(request)
        # Roughly proportional to length so duration assertions are meaningful.
        seconds = max(0.2, len(request.text) / 15.0 / request.speed)
        return TTSResult(
            audio_bytes=_tone_wav(seconds),
            mime_type="audio/wav",
            provider_latency_ms=1,
        )

    async def healthcheck(self) -> bool:
        return True

    async def list_voices(self) -> list[VoiceDescriptor]:
        return [
            VoiceDescriptor(
                provider_voice_id="stub_bm",
                name="Stub British Male",
                locale="en-GB",
                accent="british",
                gender="male",
            ),
            VoiceDescriptor(
                provider_voice_id="stub_af",
                name="Stub American Female",
                locale="en-US",
                accent="american",
                gender="female",
            ),
        ]
