"""ElevenLabs adapter (SPEC section 8.3, TASKS Phase 2).

ElevenLabs voices carry free-form labels that may include accent, age, gender
and use case, which map naturally onto the Voice Catalog. SPEC 8.3 warns those
labels are not guaranteed, so everything goes through the shared normalizer and
anything absent becomes "unknown" rather than a guess.

Written against the documented REST API but never exercised against the live
service -- no API key was available. The request mapping is covered by tests
with mocked HTTP.
"""

from __future__ import annotations

import time

import httpx

from app.domain.errors import (
    ProviderAuthFailed,
    ProviderRateLimited,
    ProviderRequestFailed,
    ProviderUnavailable,
)

from .base import (
    ProviderCapabilities,
    TTSProvider,
    TTSRequest,
    TTSResult,
    VoiceDescriptor,
)
from .normalization import (
    normalize_accent,
    normalize_age_group,
    normalize_gender,
)

_BASE = "https://api.elevenlabs.io/v1"
_TIMEOUT = httpx.Timeout(120.0, connect=10.0)

_OUTPUT_FORMATS = {
    "mp3": "mp3_44100_128",
    "wav": "pcm_44100",
}
_MIME = {"mp3": "audio/mpeg", "wav": "audio/wav"}


class ElevenLabsAdapter(TTSProvider):
    name = "elevenlabs"
    capabilities = ProviderCapabilities(
        # Speed support varies by model and is not dependable across the
        # range this app offers. Declaring it unsupported makes the render
        # pipeline time-stretch with FFmpeg instead, so generation_speed
        # behaves the same here as with every other provider.
        supports_speed=False,
        speed_range=(1.0, 1.0),
        supports_instructions=False,
        native_formats=("mp3", "wav"),
    )

    def __init__(self, api_key: str, model: str = "eleven_multilingual_v2") -> None:
        self._api_key = api_key
        self._model = model

    async def synthesize(self, request: TTSRequest) -> TTSResult:
        if not self._api_key:
            raise ProviderUnavailable("ElevenLabs is not configured.")

        output_format = _OUTPUT_FORMATS.get(request.output_format)
        if output_format is None:
            raise ProviderRequestFailed(
                f"ElevenLabs cannot return {request.output_format}."
            )

        started = time.perf_counter()
        try:
            async with httpx.AsyncClient(timeout=_TIMEOUT) as client:
                response = await client.post(
                    f"{_BASE}/text-to-speech/{request.provider_voice_id}",
                    params={"output_format": output_format},
                    headers={
                        "xi-api-key": self._api_key,
                        "Accept": "audio/mpeg",
                    },
                    json={
                        "text": request.text,
                        "model_id": request.model or self._model,
                    },
                )
        except httpx.TimeoutException as exc:
            raise ProviderUnavailable("ElevenLabs timed out.") from exc
        except httpx.HTTPError as exc:
            raise ProviderUnavailable("Could not reach ElevenLabs.") from exc

        _raise_for_status(response)
        return TTSResult(
            audio_bytes=response.content,
            mime_type=_MIME.get(request.output_format, "audio/mpeg"),
            provider_request_id=response.headers.get("request-id"),
            provider_latency_ms=int((time.perf_counter() - started) * 1000),
        )

    async def healthcheck(self) -> bool:
        if not self._api_key:
            return False
        try:
            async with httpx.AsyncClient(timeout=httpx.Timeout(10.0)) as client:
                response = await client.get(
                    f"{_BASE}/voices", headers={"xi-api-key": self._api_key}
                )
        except httpx.HTTPError:
            return False
        return response.status_code < 400

    async def list_voices(self) -> list[VoiceDescriptor]:
        if not self._api_key:
            return []
        try:
            async with httpx.AsyncClient(timeout=_TIMEOUT) as client:
                response = await client.get(
                    f"{_BASE}/voices", headers={"xi-api-key": self._api_key}
                )
        except httpx.HTTPError as exc:
            raise ProviderUnavailable("Could not reach ElevenLabs.") from exc
        _raise_for_status(response)

        voices: list[VoiceDescriptor] = []
        for item in response.json().get("voices", []):
            labels = item.get("labels") or {}
            accent = normalize_accent(labels.get("accent"))
            voices.append(
                VoiceDescriptor(
                    provider_voice_id=item.get("voice_id", ""),
                    name=item.get("name", ""),
                    language="en",
                    locale=None,
                    accent=accent,
                    gender=normalize_gender(labels.get("gender")),
                    age_group=normalize_age_group(labels.get("age")),
                    style_tags=[
                        value
                        for key, value in labels.items()
                        if key in ("use_case", "description") and value
                    ],
                    preview_url=item.get("preview_url"),
                    metadata={"category": item.get("category")},
                )
            )
        return voices


def _raise_for_status(response: httpx.Response) -> None:
    if response.status_code < 400:
        return
    if response.status_code in (401, 403):
        raise ProviderAuthFailed
    if response.status_code == 429:
        raise ProviderRateLimited
    if response.status_code >= 500:
        raise ProviderUnavailable
    raise ProviderRequestFailed(
        f"ElevenLabs rejected the request (HTTP {response.status_code})."
    )
