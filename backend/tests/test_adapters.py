"""Adapter tests: domain request -> provider request.

TASKS.md asks for these to run against mocked provider HTTP. Azure and
ElevenLabs have never been exercised against the live services (no credentials
were available), so these mapping tests are the only guarantee that the
requests are shaped as the providers document.
"""

from __future__ import annotations

import httpx
import pytest

from app.domain.errors import (
    ProviderAuthFailed,
    ProviderRateLimited,
    ProviderRequestFailed,
    ProviderUnavailable,
)
from app.infrastructure.tts.azure_adapter import AzureAdapter
from app.infrastructure.tts.base import TTSRequest
from app.infrastructure.tts.elevenlabs_adapter import ElevenLabsAdapter
from app.infrastructure.tts.normalization import (
    normalize_accent,
    normalize_age_group,
    normalize_gender,
)
from app.infrastructure.tts.openai_adapter import OpenAIAdapter


def mock_client(handler, monkeypatch):
    """Point every AsyncClient this adapter creates at a mock transport."""
    original = httpx.AsyncClient

    def factory(*args, **kwargs):
        kwargs["transport"] = httpx.MockTransport(handler)
        return original(*args, **kwargs)

    monkeypatch.setattr(httpx, "AsyncClient", factory)


REQUEST = TTSRequest(
    text="Hello there.",
    provider_voice_id="voice-1",
    speed=1.05,
    output_format="mp3",
)


class TestAzureMapping:
    def test_ssml_encodes_speed_as_a_rate_delta(self):
        adapter = AzureAdapter("key", "eastus")
        ssml = adapter.build_ssml(
            TTSRequest(text="Hi.", provider_voice_id="en-GB-RyanNeural", speed=1.05)
        )
        assert 'rate="+5.00%"' in ssml
        assert 'name="en-GB-RyanNeural"' in ssml

    def test_slower_than_natural_is_a_negative_rate(self):
        adapter = AzureAdapter("key", "eastus")
        ssml = adapter.build_ssml(
            TTSRequest(text="Hi.", provider_voice_id="v", speed=0.9)
        )
        assert 'rate="-10.00%"' in ssml

    def test_text_is_xml_escaped(self):
        adapter = AzureAdapter("key", "eastus")
        ssml = adapter.build_ssml(
            TTSRequest(text='Tom & "Jerry" <b>', provider_voice_id="v", speed=1.0)
        )
        assert "&amp;" in ssml and "&lt;b&gt;" in ssml
        # The raw markup must not survive into the document.
        assert "<b>" not in ssml

    async def test_synthesize_sends_ssml_and_output_format(self, monkeypatch):
        seen: dict = {}

        def handler(request: httpx.Request) -> httpx.Response:
            seen["url"] = str(request.url)
            seen["headers"] = dict(request.headers)
            seen["body"] = request.content.decode()
            return httpx.Response(200, content=b"AUDIO")

        mock_client(handler, monkeypatch)
        adapter = AzureAdapter("secret-key", "westus")
        result = await adapter.synthesize(REQUEST)

        assert result.audio_bytes == b"AUDIO"
        assert "westus.tts.speech.microsoft.com" in seen["url"]
        assert seen["headers"]["ocp-apim-subscription-key"] == "secret-key"
        assert seen["headers"]["content-type"] == "application/ssml+xml"
        assert seen["headers"]["x-microsoft-outputformat"].endswith("mp3")
        assert "<speak" in seen["body"]

    async def test_voice_list_derives_accent_from_locale(self, monkeypatch):
        payload = [
            {
                "ShortName": "en-GB-RyanNeural",
                "Locale": "en-GB",
                "DisplayName": "Ryan",
                "Gender": "Male",
                "StyleList": ["chat"],
            },
            {
                "ShortName": "en-AU-NatashaNeural",
                "Locale": "en-AU",
                "DisplayName": "Natasha",
                "Gender": "Female",
            },
            {
                "ShortName": "ja-JP-NanamiNeural",
                "Locale": "ja-JP",
                "DisplayName": "Nanami",
                "Gender": "Female",
            },
        ]
        mock_client(lambda r: httpx.Response(200, json=payload), monkeypatch)

        voices = await AzureAdapter("k", "eastus").list_voices()
        # Non-English voices are filtered out.
        assert len(voices) == 2
        assert {v.accent for v in voices} == {"british", "australian"}
        assert voices[0].gender == "male"

    @pytest.mark.parametrize(
        "status,expected",
        [
            (401, ProviderAuthFailed),
            (403, ProviderAuthFailed),
            (429, ProviderRateLimited),
            (500, ProviderUnavailable),
            (400, ProviderRequestFailed),
        ],
    )
    async def test_http_errors_map_to_normalized_errors(
        self, status, expected, monkeypatch
    ):
        mock_client(
            lambda r: httpx.Response(status, text="secret-key=abc123"), monkeypatch
        )
        with pytest.raises(expected) as caught:
            await AzureAdapter("k", "eastus").synthesize(REQUEST)
        # The provider body can echo credentials; it must not reach the message.
        assert "abc123" not in str(caught.value)

    async def test_unconfigured_adapter_refuses_cleanly(self):
        with pytest.raises(ProviderUnavailable):
            await AzureAdapter("", "").synthesize(REQUEST)


class TestElevenLabsMapping:
    async def test_synthesize_posts_to_the_voice_endpoint(self, monkeypatch):
        seen: dict = {}

        def handler(request: httpx.Request) -> httpx.Response:
            seen["url"] = str(request.url)
            seen["headers"] = dict(request.headers)
            seen["json"] = request.content.decode()
            return httpx.Response(200, content=b"AUDIO")

        mock_client(handler, monkeypatch)
        result = await ElevenLabsAdapter("xi-secret").synthesize(REQUEST)

        assert result.audio_bytes == b"AUDIO"
        assert "/v1/text-to-speech/voice-1" in seen["url"]
        assert "output_format=mp3_44100_128" in seen["url"]
        assert seen["headers"]["xi-api-key"] == "xi-secret"
        assert "Hello there." in seen["json"]

    async def test_speed_is_not_sent_and_is_left_to_the_pipeline(self, monkeypatch):
        seen: dict = {}
        mock_client(
            lambda r: (
                seen.update(body=r.content.decode()),
                httpx.Response(200, content=b"A"),
            )[1],
            monkeypatch,
        )
        await ElevenLabsAdapter("k").synthesize(REQUEST)
        # supports_speed is False, so the render pipeline time-stretches with
        # FFmpeg rather than the adapter silently ignoring the requested speed.
        assert "speed" not in seen["body"]
        assert ElevenLabsAdapter("k").capabilities.supports_speed is False

    async def test_missing_labels_normalize_to_unknown(self, monkeypatch):
        payload = {
            "voices": [
                {
                    "voice_id": "a",
                    "name": "Rachel",
                    "labels": {
                        "accent": "american",
                        "gender": "female",
                        "age": "young",
                    },
                },
                {"voice_id": "b", "name": "Unlabelled", "labels": {}},
                {"voice_id": "c", "name": "NoLabelsKey"},
            ]
        }
        mock_client(lambda r: httpx.Response(200, json=payload), monkeypatch)

        voices = await ElevenLabsAdapter("k").list_voices()
        assert (voices[0].accent, voices[0].gender, voices[0].age_group) == (
            "american",
            "female",
            "young",
        )
        # SPEC 8.3: absent metadata must never be invented.
        for voice in voices[1:]:
            assert voice.accent == "unknown"
            assert voice.gender == "unknown"
            assert voice.age_group == "unknown"


class TestOpenAIMapping:
    async def test_speed_capable_model_sends_speed(self, monkeypatch):
        seen: dict = {}
        mock_client(
            lambda r: (
                seen.update(body=r.content.decode()),
                httpx.Response(200, content=b"A"),
            )[1],
            monkeypatch,
        )
        adapter = OpenAIAdapter("sk-test", model="tts-1")
        assert adapter.capabilities.supports_speed is True
        await adapter.synthesize(REQUEST)
        assert '"speed"' in seen["body"]

    async def test_model_without_speed_support_omits_it(self, monkeypatch):
        seen: dict = {}
        mock_client(
            lambda r: (
                seen.update(body=r.content.decode()),
                httpx.Response(200, content=b"A"),
            )[1],
            monkeypatch,
        )
        adapter = OpenAIAdapter("sk-test", model="gpt-4o-mini-tts")
        # This family rejects `speed`; the pipeline time-stretches instead.
        assert adapter.capabilities.supports_speed is False
        await adapter.synthesize(REQUEST)
        assert '"speed"' not in seen["body"]

    async def test_builtin_voices_do_not_claim_accent_or_gender(self):
        voices = await OpenAIAdapter("sk-test").list_voices()
        assert voices
        # OpenAI publishes neither, and API.md forbids inventing them.
        assert {v.accent for v in voices} == {"unknown"}
        assert {v.gender for v in voices} == {"unknown"}


class TestNormalization:
    @pytest.mark.parametrize(
        "raw,expected",
        [
            ("American", "american"),
            ("US", "american"),
            ("british", "british"),
            ("UK", "british"),
            ("Australian", "australian"),
            ("  Irish  ", "irish"),
            ("nonsense", "unknown"),
            (None, "unknown"),
        ],
    )
    def test_accent_aliases(self, raw, expected):
        assert normalize_accent(raw) == expected

    def test_locale_is_the_fallback_for_accent(self):
        assert normalize_accent(None, "en-AU") == "australian"
        assert normalize_accent("nonsense", "en-GB") == "british"
        assert normalize_accent(None, "fr-FR") == "unknown"

    @pytest.mark.parametrize(
        "raw,expected",
        [
            ("Female", "female"),
            ("M", "male"),
            ("non-binary", "neutral"),
            ("", "unknown"),
            (None, "unknown"),
            ("alien", "unknown"),
        ],
    )
    def test_gender_aliases(self, raw, expected):
        assert normalize_gender(raw) == expected

    @pytest.mark.parametrize(
        "raw,expected",
        [
            ("young", "young"),
            ("middle aged", "adult"),
            ("old", "mature"),
            (None, "unknown"),
            ("ancient", "unknown"),
        ],
    )
    def test_age_aliases(self, raw, expected):
        assert normalize_age_group(raw) == expected
