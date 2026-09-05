"""OpenAI speech adapter.

Fully implemented rather than stubbed, even though the MVP runs on local
providers: setting OPENAI_API_KEY is enough to switch to it with no code
change. Called over HTTP so the SDK is not a dependency of the server.
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

_ENDPOINT = "https://api.openai.com/v1/audio/speech"
_TIMEOUT = httpx.Timeout(120.0, connect=10.0)

_MIME_BY_FORMAT = {
    "mp3": "audio/mpeg",
    "opus": "audio/opus",
    "aac": "audio/aac",
    "flac": "audio/flac",
    "wav": "audio/wav",
}

# Built-in voice ids. OpenAI publishes no accent or gender for these, and
# API.md forbids inventing metadata, so both stay "unknown" and these voices
# simply do not appear under an accent filter.
BUILTIN_VOICES = (
    "alloy",
    "ash",
    "ballad",
    "coral",
    "echo",
    "fable",
    "onyx",
    "nova",
    "sage",
    "shimmer",
    "verse",
    "marin",
    "cedar",
)

# `speed` is not accepted by the gpt-4o-mini-tts family; only the tts-1 models
# take it. Declaring supports_speed=False makes the render pipeline apply an
# FFmpeg atempo pass instead, so generation_speed still works either way.
_SPEED_CAPABLE_PREFIXES = ("tts-1",)


class OpenAIAdapter(TTSProvider):
    name = "openai"

    def __init__(self, api_key: str, model: str = "gpt-4o-mini-tts") -> None:
        self._api_key = api_key
        self._model = model
        supports_speed = model.startswith(_SPEED_CAPABLE_PREFIXES)
        self.capabilities = ProviderCapabilities(
            supports_speed=supports_speed,
            speed_range=(0.25, 4.0) if supports_speed else (1.0, 1.0),
            supports_instructions=not supports_speed,
            native_formats=("mp3", "opus", "aac", "flac", "wav"),
        )

    async def synthesize(self, request: TTSRequest) -> TTSResult:
        if not self._api_key:
            raise ProviderUnavailable("OpenAI is not configured.")

        model = request.model or self._model
        payload: dict = {
            "model": model,
            "voice": request.provider_voice_id,
            "input": request.text,
            "response_format": request.output_format,
        }
        if self.capabilities.supports_speed:
            payload["speed"] = self.clamp_speed(request.speed)
        if request.instructions and self.capabilities.supports_instructions:
            payload["instructions"] = request.instructions

        started = time.perf_counter()
        try:
            async with httpx.AsyncClient(timeout=_TIMEOUT) as client:
                response = await client.post(
                    _ENDPOINT,
                    headers={"Authorization": f"Bearer {self._api_key}"},
                    json=payload,
                )
        except httpx.TimeoutException as exc:
            raise ProviderUnavailable("OpenAI timed out.") from exc
        except httpx.HTTPError as exc:
            raise ProviderUnavailable("Could not reach OpenAI.") from exc

        _raise_for_status(response)
        return TTSResult(
            audio_bytes=response.content,
            mime_type=_MIME_BY_FORMAT.get(request.output_format, "audio/mpeg"),
            provider_request_id=response.headers.get("x-request-id"),
            provider_latency_ms=int((time.perf_counter() - started) * 1000),
        )

    async def healthcheck(self) -> bool:
        return bool(self._api_key)

    async def list_voices(self) -> list[VoiceDescriptor]:
        return [
            VoiceDescriptor(
                provider_voice_id=voice_id,
                name=voice_id.capitalize(),
                language="en",
                locale=None,
                accent="unknown",
                gender="unknown",
                age_group="unknown",
                style_tags=[],
                provider_model_hint=self._model,
            )
            for voice_id in BUILTIN_VOICES
        ]


def _raise_for_status(response: httpx.Response) -> None:
    if response.status_code < 400:
        return
    # The provider's body can echo request details; never propagate it.
    if response.status_code in (401, 403):
        raise ProviderAuthFailed
    if response.status_code == 429:
        raise ProviderRateLimited
    if response.status_code >= 500:
        raise ProviderUnavailable
    raise ProviderRequestFailed(
        f"OpenAI rejected the request (HTTP {response.status_code})."
    )
