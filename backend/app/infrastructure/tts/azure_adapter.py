"""Azure AI Speech adapter (SPEC section 8.2, TASKS Phase 2).

Azure's strength is fine-grained SSML control. Even so, application-level
segmentation stays canonical: other providers cannot reproduce multi-voice
SSML, and the render pipeline must behave the same across all of them, so this
adapter emits single-voice SSML per segment.

Written against the documented REST API but never exercised against the live
service -- no subscription key was available. The request mapping is covered by
tests with mocked HTTP.
"""

from __future__ import annotations

import time
from xml.sax.saxutils import escape, quoteattr

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
    normalize_gender,
    normalize_language,
)

_TIMEOUT = httpx.Timeout(120.0, connect=10.0)

# Azure names an output format rather than taking a file extension.
_OUTPUT_FORMATS = {
    "mp3": "audio-24khz-48kbitrate-mono-mp3",
    "wav": "riff-24khz-16bit-mono-pcm",
    "opus": "ogg-24khz-16bit-mono-opus",
}
_MIME = {"mp3": "audio/mpeg", "wav": "audio/wav", "opus": "audio/opus"}


class AzureAdapter(TTSProvider):
    name = "azure"
    capabilities = ProviderCapabilities(
        supports_speed=True,
        # SSML `rate` accepts a wide range, but past this prosody degrades far
        # enough to be useless as listening material.
        speed_range=(0.5, 2.0),
        supports_instructions=False,
        native_formats=("mp3", "wav", "opus"),
    )

    def __init__(self, api_key: str, region: str) -> None:
        self._api_key = api_key
        self._region = region

    @property
    def _synth_endpoint(self) -> str:
        return f"https://{self._region}.tts.speech.microsoft.com/cognitiveservices/v1"

    @property
    def _voices_endpoint(self) -> str:
        return (
            f"https://{self._region}.tts.speech.microsoft.com"
            "/cognitiveservices/voices/list"
        )

    def build_ssml(self, request: TTSRequest, locale: str = "en-US") -> str:
        """Wrap one segment in single-voice SSML.

        `rate` is a percentage delta from the voice's natural pace, so 1.05
        becomes "+5.00%".
        """
        speed = self.clamp_speed(request.speed)
        rate = f"{(speed - 1.0) * 100:+.2f}%"
        return (
            '<speak version="1.0" '
            'xmlns="http://www.w3.org/2001/10/Synthesis" '
            f"xml:lang={quoteattr(locale)}>"
            f"<voice name={quoteattr(request.provider_voice_id)}>"
            f'<prosody rate="{rate}">{escape(request.text)}</prosody>'
            "</voice></speak>"
        )

    async def synthesize(self, request: TTSRequest) -> TTSResult:
        if not self._api_key or not self._region:
            raise ProviderUnavailable("Azure Speech is not configured.")

        output_format = _OUTPUT_FORMATS.get(request.output_format)
        if output_format is None:
            raise ProviderRequestFailed(f"Azure cannot return {request.output_format}.")

        started = time.perf_counter()
        try:
            async with httpx.AsyncClient(timeout=_TIMEOUT) as client:
                response = await client.post(
                    self._synth_endpoint,
                    headers={
                        "Ocp-Apim-Subscription-Key": self._api_key,
                        "Content-Type": "application/ssml+xml",
                        "X-Microsoft-OutputFormat": output_format,
                        "User-Agent": "listening-studio",
                    },
                    content=self.build_ssml(request).encode("utf-8"),
                )
        except httpx.TimeoutException as exc:
            raise ProviderUnavailable("Azure Speech timed out.") from exc
        except httpx.HTTPError as exc:
            raise ProviderUnavailable("Could not reach Azure Speech.") from exc

        _raise_for_status(response)
        return TTSResult(
            audio_bytes=response.content,
            mime_type=_MIME.get(request.output_format, "audio/mpeg"),
            provider_request_id=response.headers.get("x-requestid"),
            provider_latency_ms=int((time.perf_counter() - started) * 1000),
        )

    async def healthcheck(self) -> bool:
        if not self._api_key or not self._region:
            return False
        try:
            async with httpx.AsyncClient(timeout=httpx.Timeout(10.0)) as client:
                response = await client.get(
                    self._voices_endpoint,
                    headers={"Ocp-Apim-Subscription-Key": self._api_key},
                )
        except httpx.HTTPError:
            return False
        return response.status_code < 400

    async def list_voices(self) -> list[VoiceDescriptor]:
        if not self._api_key or not self._region:
            return []
        try:
            async with httpx.AsyncClient(timeout=_TIMEOUT) as client:
                response = await client.get(
                    self._voices_endpoint,
                    headers={"Ocp-Apim-Subscription-Key": self._api_key},
                )
        except httpx.HTTPError as exc:
            raise ProviderUnavailable("Could not reach Azure Speech.") from exc
        _raise_for_status(response)

        voices: list[VoiceDescriptor] = []
        for item in response.json():
            locale = item.get("Locale")
            if not locale or not locale.startswith("en-"):
                continue
            voices.append(
                VoiceDescriptor(
                    provider_voice_id=item.get("ShortName", ""),
                    name=item.get("LocalName") or item.get("DisplayName", ""),
                    language=normalize_language(locale),
                    locale=locale,
                    # Azure states a locale but never an accent, so the accent
                    # is derived from the locale rather than guessed.
                    accent=normalize_accent(None, locale),
                    gender=normalize_gender(item.get("Gender")),
                    age_group="unknown",
                    style_tags=list(item.get("StyleList") or []),
                    metadata={"voice_type": item.get("VoiceType")},
                )
            )
        return voices


def _raise_for_status(response: httpx.Response) -> None:
    if response.status_code < 400:
        return
    # Azure echoes request details in error bodies; never propagate them.
    if response.status_code in (401, 403):
        raise ProviderAuthFailed
    if response.status_code == 429:
        raise ProviderRateLimited
    if response.status_code >= 500:
        raise ProviderUnavailable
    raise ProviderRequestFailed(
        f"Azure Speech rejected the request (HTTP {response.status_code})."
    )
