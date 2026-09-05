# Provider Documentation References

Checked 2026-09-02.

## OpenAI

Create speech API:
https://developers.openai.com/api/reference/resources/audio/subresources/speech/methods/create

Key points used in this specification:
- `POST /v1/audio/speech`
- current documented TTS models
- current built-in voices
- `speed` documented as 0.25–4.0
- output format options
- `instructions` support for compatible models

## Microsoft Azure AI Speech

SSML overview:
https://learn.microsoft.com/en-us/azure/ai-services/speech-service/speech-synthesis-markup

Text-to-speech overview:
https://learn.microsoft.com/en-us/azure/ai-services/speech-service/text-to-speech

Key points:
- rate
- pitch
- volume
- pauses
- pronunciation
- language/voice
- multiple voices within SSML documents

## ElevenLabs

TTS:
https://elevenlabs.io/docs/api-reference/text-to-speech/convert

Voice information:
https://elevenlabs.io/docs/api-reference/voices/get

Key points:
- concrete `voice_id`
- voice metadata/labels may include accent, age, gender and use case
- metadata availability must not be assumed

## Rule

Provider APIs change.
Do not hard-code provider capabilities outside adapter/config layers.
