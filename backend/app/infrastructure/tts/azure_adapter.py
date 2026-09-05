"""Azure AI Speech adapter -- interface and stub (SPEC section 8.2, TASKS Phase 2).

Azure's value is fine-grained SSML control (rate, pitch, style, per-voice
pronunciation). Even so, application-level segmentation stays canonical:
other providers cannot reproduce multi-voice SSML, and the render pipeline
must behave the same across all of them.

Voice discovery would call the region's `/cognitiveservices/voices/list`, where
locale maps cleanly onto the accent model -- en-GB to british, en-AU to
australian -- without inventing metadata.
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

LOCALE_TO_ACCENT = {
    "en-US": "american",
    "en-GB": "british",
    "en-AU": "australian",
    "en-CA": "canadian",
    "en-IE": "irish",
    "en-IN": "indian",
    "en-NZ": "new_zealand",
    "en-ZA": "south_african",
    "en-SG": "singaporean",
}


class AzureAdapter(TTSProvider):
    name = "azure"
    capabilities = ProviderCapabilities(
        supports_speed=True,
        speed_range=(0.5, 2.0),
        supports_instructions=False,
        native_formats=("mp3", "wav"),
    )

    def __init__(self, api_key: str, region: str) -> None:
        self._api_key = api_key
        self._region = region

    async def synthesize(self, request: TTSRequest) -> TTSResult:
        raise ProviderUnavailable(
            "The Azure adapter is not implemented yet (planned for Phase 2)."
        )

    async def healthcheck(self) -> bool:
        return False

    async def list_voices(self) -> list[VoiceDescriptor]:
        return []
