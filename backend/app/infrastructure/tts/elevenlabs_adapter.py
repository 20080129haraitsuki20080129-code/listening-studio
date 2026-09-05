"""ElevenLabs adapter -- interface and stub (SPEC section 8.3, TASKS Phase 2).

ElevenLabs voices carry labels that may include accent, age, gender and use
case, which map naturally onto the Voice Catalog. Those labels are not
guaranteed to be present, so a real implementation must normalize anything
missing to "unknown" rather than guess.
"""

from __future__ import annotations

from app.domain.errors import ProviderUnavailable

from .base import (
    ProviderCapabilities,
    TTSProvider,
    TTSRequest,
    TTSResult,
    VoiceDescriptor,
)


class ElevenLabsAdapter(TTSProvider):
    name = "elevenlabs"
    capabilities = ProviderCapabilities(
        supports_speed=False,
        speed_range=(1.0, 1.0),
        supports_instructions=False,
        native_formats=("mp3",),
    )

    def __init__(self, api_key: str) -> None:
        self._api_key = api_key

    async def synthesize(self, request: TTSRequest) -> TTSResult:
        raise ProviderUnavailable(
            "The ElevenLabs adapter is not implemented yet (planned for Phase 2)."
        )

    async def healthcheck(self) -> bool:
        return False

    async def list_voices(self) -> list[VoiceDescriptor]:
        return []
