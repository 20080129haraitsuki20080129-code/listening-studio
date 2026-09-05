"""TTS provider abstraction (SPEC section 7).

Nothing above this layer may import a provider SDK. `TTSRequest` carries only
domain concepts; translating those into a provider's own parameters is each
adapter's job.
"""

from __future__ import annotations

from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from typing import Literal

OutputFormat = Literal["mp3", "wav", "opus", "aac", "flac"]


@dataclass(frozen=True)
class TTSRequest:
    text: str
    provider_voice_id: str
    model: str | None = None
    speed: float = 1.0
    output_format: OutputFormat = "mp3"
    instructions: str | None = None


@dataclass(frozen=True)
class TTSResult:
    audio_bytes: bytes
    mime_type: str
    provider_request_id: str | None = None
    provider_latency_ms: int | None = None


@dataclass(frozen=True)
class VoiceDescriptor:
    """A voice as the provider reports it, normalized for the Voice Catalog.

    Accent and gender are our metadata, not a TTS API parameter (SPEC 2.2).
    Adapters must leave them "unknown" rather than guessing -- deriving them
    from a documented naming scheme or locale is fine, inventing them is not.
    """

    provider_voice_id: str
    name: str
    language: str = "en"
    locale: str | None = None
    accent: str | None = None
    gender: str = "unknown"
    age_group: str = "unknown"
    style_tags: list[str] = field(default_factory=list)
    provider_model_hint: str | None = None
    metadata: dict = field(default_factory=dict)


@dataclass(frozen=True)
class ProviderCapabilities:
    """What the provider can do natively.

    The render pipeline consults this instead of assuming. When a provider
    cannot change speed itself, the pipeline falls back to an FFmpeg atempo
    pass so `generation_speed` still means the same thing to the user.
    """

    supports_speed: bool = True
    speed_range: tuple[float, float] = (0.25, 4.0)
    supports_instructions: bool = False
    native_formats: tuple[str, ...] = ("mp3",)


class TTSProvider(ABC):
    name: str
    capabilities: ProviderCapabilities

    @abstractmethod
    async def synthesize(self, request: TTSRequest) -> TTSResult: ...

    @abstractmethod
    async def healthcheck(self) -> bool: ...

    async def list_voices(self) -> list[VoiceDescriptor]:
        """Voices this provider offers. Empty when discovery is unsupported."""
        return []

    def clamp_speed(self, speed: float) -> float:
        low, high = self.capabilities.speed_range
        return min(max(speed, low), high)
