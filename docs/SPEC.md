# Listening Studio — Technical Product Specification

Version: 1.0  
Target: Web application  
Primary use: English listening practice / listening material creation

---

# 1. Product Goal

Listening Studio は単なる Text-to-Speech アプリではない。

目的は、

**任意の英文を、自然な話速・複数の声・異なる英語アクセント・会話構成を持つリスニング教材へ変換すること**

である。

利用者は以下を行える。

1. 英文を入力する
2. Monologue / Dialogue / Listening Test を選ぶ
3. 話者ごとに声を設定する
4. Accent / Gender / Voice / Speed を選択する
5. 音声を生成する
6. ブラウザで再生する
7. Transcriptを隠してリスニング練習する
8. A-B repeatを行う
9. MP3/WAVとして書き出す
10. Projectとして保存し再編集する

---

# 2. Product Principles

## 2.1 Provider-independent

OpenAI、Azure、ElevenLabs等のAPIをUIから直接使用してはならない。

必ず次の構造にする。

```text
UI
↓
Application Service
↓
TTS Domain Interface
↓
Provider Adapter
├── OpenAIAdapter
├── AzureAdapter
└── ElevenLabsAdapter
```

## 2.2 Accent / Gender are metadata

`accent=British` や `gender=female` を全TTS APIの共通パラメータだと仮定してはならない。

これらはアプリ側の Voice Catalog のmetadataとして扱う。

例:

```json
{
  "id": "voice_xxx",
  "provider": "elevenlabs",
  "provider_voice_id": "...",
  "language": "en",
  "locale": "en-US",
  "accent": "american",
  "gender": "female",
  "age_group": "adult",
  "style_tags": ["clear", "neutral", "academic"]
}
```

ユーザーは metadata で絞り込み、最終的には具体的な voice_id を選択する。

## 2.3 Generated speed vs player speed

2種類を分離する。

- `generation_speed`
  - TTS生成時の速度
- `playback_rate`
  - ブラウザ再生時の速度

教材としての「実際の話速」は generation_speed を優先する。

## 2.4 Segment-oriented audio

長文全体を1リクエストで処理する設計を前提にしない。

ScriptをSegmentに分ける。

```text
Script
├── Segment 1
├── Segment 2
├── Segment 3
...
```

各Segmentは別々に再生成可能とする。

---

# 3. Scope

## 3.1 MVP

MVPに含める。

### Script

- 英文入力
- 自動sentence segmentation
- Dialogue parser
- Speaker assignment

### Voice

- Voice一覧
- Provider
- Accent
- Gender
- Locale
- Voice preview
- Voice選択

### Audio

- TTS生成
- MP3
- generation speed
- pause before / after
- 複数segment結合
- 音量normalization

### Player

- play / pause
- seek
- playback rate
- A-B repeat
- transcript show/hide

### Project

- create
- save
- edit
- regenerate
- delete

## 3.2 Post-MVP

後から追加。

- Listening Test builder
- WPM targeting
- accent randomization
- voice randomization
- shadowing mode
- vocabulary extraction
- automatic question generation
- STT pronunciation comparison
- listening history
- difficulty score
- mobile/PWA
- presets such as academic lecture / news / exam

---

# 4. Main Modes

## 4.1 Monologue

1つのvoiceで英文を読む。

Input:

```text
Climate change is altering migration patterns across the world.
```

設定:

```text
Voice: ...
Accent: British
Gender: Female
Generation speed: 1.0
```

## 4.2 Dialogue

入力形式:

```text
[A]
Have you finished the report?

[B]
Not yet. I found something interesting in the data.

[A]
What did you find?
```

Parserは `[SpeakerName]` を話者として認識する。

Speakerごとに:

- voice
- generation speed
- provider
- pause defaults

を設定できる。

## 4.3 Listening Test

MVP後。

構成例:

```text
Intro
↓
Passage
↓
Pause
↓
Passage again
↓
Questions
```

設定:

```json
{
  "repeat_count": 2,
  "pause_between_repeats_ms": 5000,
  "question_pause_ms": 10000,
  "transcript_initially_hidden": true
}
```

## 4.4 Shadowing

MVP後。

Sentenceまたはchunk単位で

```text
audio
↓
pause
↓
repeat
```

を行う。

---

# 5. UX

## 5.1 Main Create Screen

Route:

```text
/create
```

Desktop layout:

```text
┌────────────────────────────────────────────┐
│ Listening Studio                           │
├──────────────────────┬─────────────────────┤
│ Script Editor        │ Voice / Audio       │
│                      │ Settings            │
│ [English text...]    │                     │
│                      │ Mode                │
│                      │ Accent              │
│                      │ Gender              │
│                      │ Voice               │
│                      │ Speed               │
│                      │                     │
├──────────────────────┴─────────────────────┤
│ Timeline / Segments                        │
├────────────────────────────────────────────┤
│ Player                                     │
│ ▶ ━━━━━━━━━━━━━━━━━━━━━━━━━                │
│ A  B  Transcript  0.75 1.0 1.25           │
└────────────────────────────────────────────┘
```

## 5.2 Voice Selector

filter:

```text
Provider
Language
Accent
Gender
Age group
Style tags
```

Voice card:

```text
Voice name
Accent
Gender
Provider
[Preview]
[Select]
```

## 5.3 Dialogue UI

Speaker panel:

```text
Speaker A
Voice: [select]
Accent: British
Gender: Female
Speed: 1.05

Speaker B
Voice: [select]
Accent: American
Gender: Male
Speed: 1.00
```

## 5.4 Segment Editor

各segment:

```text
#12 Speaker B

"The results were completely different..."

Voice: James
Speed: 1.05
Pause before: 300 ms
Pause after: 500 ms

[Regenerate]
```

---

# 6. Domain Model

## Project

```ts
type Project = {
  id: string
  title: string
  mode: "monologue" | "dialogue" | "listening_test" | "shadowing"
  sourceText: string
  transcriptVisibleDefault: boolean
  createdAt: string
  updatedAt: string
}
```

## Speaker

```ts
type Speaker = {
  id: string
  projectId: string
  label: string
  displayName: string
  voiceId: string | null
  generationSpeed: number
  defaultPauseBeforeMs: number
  defaultPauseAfterMs: number
}
```

## Segment

```ts
type Segment = {
  id: string
  projectId: string
  orderIndex: number
  speakerId: string | null
  text: string

  voiceIdOverride: string | null
  generationSpeedOverride: number | null

  pauseBeforeMs: number
  pauseAfterMs: number

  audioAssetId: string | null
  durationMs: number | null
}
```

## Voice

```ts
type Voice = {
  id: string

  provider:
    | "openai"
    | "azure"
    | "elevenlabs"

  providerVoiceId: string
  providerModelHint: string | null

  name: string

  language: string
  locale: string | null

  accent: string | null
  gender: "female" | "male" | "neutral" | "unknown"
  ageGroup: "young" | "adult" | "mature" | "unknown"

  styleTags: string[]

  previewUrl: string | null

  enabled: boolean
}
```

## AudioAsset

```ts
type AudioAsset = {
  id: string
  storageKey: string
  mimeType: string
  format: "mp3" | "wav" | "opus" | "aac" | "flac"
  durationMs: number
  sizeBytes: number
  sha256: string
  createdAt: string
}
```

---

# 7. TTS Abstraction

Python interface:

```python
from abc import ABC, abstractmethod
from dataclasses import dataclass
from typing import Literal

@dataclass
class TTSRequest:
    text: str
    provider_voice_id: str
    model: str | None
    speed: float
    output_format: Literal["mp3", "wav", "opus", "aac", "flac"]
    instructions: str | None = None

@dataclass
class TTSResult:
    audio_bytes: bytes
    mime_type: str
    provider_request_id: str | None
    provider_latency_ms: int | None

class TTSProvider(ABC):

    @abstractmethod
    async def synthesize(self, request: TTSRequest) -> TTSResult:
        ...

    @abstractmethod
    async def healthcheck(self) -> bool:
        ...
```

Provider registry:

```python
class TTSProviderRegistry:
    def __init__(self, providers: dict[str, TTSProvider]):
        self.providers = providers

    def get(self, provider: str) -> TTSProvider:
        if provider not in self.providers:
            raise UnsupportedProvider(provider)
        return self.providers[provider]
```

---

# 8. Provider Notes

Information checked against official provider documentation on 2026-09-02.

## 8.1 OpenAI

Primary endpoint:

```text
POST /v1/audio/speech
```

Current official API reference lists:

Models:

```text
tts-1
tts-1-hd
gpt-4o-mini-tts
gpt-4o-mini-tts-2025-12-15
```

Built-in voices listed:

```text
alloy
ash
ballad
coral
echo
fable
onyx
nova
sage
shimmer
verse
marin
cedar
```

Supported response formats include:

```text
mp3
opus
aac
flac
wav
pcm
```

Current `speed` range:

```text
0.25 – 4.0
```

`instructions` is available for compatible newer speech models and should be used for:

```text
Speak in clear academic English.
Use natural pauses.
Avoid exaggerated emotion.
```

Important:
Do not expose OpenAI model names deeply into the domain model.
Store them as adapter configuration.

Recommended MVP default:

```text
model = gpt-4o-mini-tts
```

## 8.2 Azure AI Speech

Use Azure when fine-grained SSML control is needed.

SSML can control:

- voice
- language
- speaking rate
- pitch
- volume
- pauses
- pronunciation
- multiple voices in one document
- style / role for supported voices

Even though Azure allows multi-voice SSML, application-level segmentation remains the canonical architecture.

Reason:
Other providers may not support identical SSML behavior.

## 8.3 ElevenLabs

TTS endpoint uses a concrete `voice_id`.

Voice metadata can include labels such as:

- accent
- age
- gender
- description
- use_case

Therefore ElevenLabs voice discovery maps naturally into the internal Voice Catalog.

Do not depend on provider labels always being present.
Normalize missing values to `unknown`.

---

# 9. Accent Model

Initial normalized accents:

```text
american
british
australian
canadian
irish
scottish
indian
new_zealand
south_african
singaporean
other
unknown
```

MVP UI may expose only:

```text
American
British
Australian
Canadian
Other
```

Storage should support broader values immediately.

---

# 10. Speed Model

## 10.1 Generation speed

Default:

```text
1.00
```

MVP slider:

```text
0.70 – 1.40
```

Advanced numeric entry may permit provider-supported range.

Provider adapter MUST validate/clamp against provider-specific limits.

## 10.2 Playback rate

Browser-only.

Recommended:

```text
0.5
0.75
0.9
1.0
1.1
1.25
1.5
2.0
```

Changing playback rate MUST NOT modify the stored generated audio.

---

# 11. WPM Targeting

Post-MVP.

User specifies:

```text
Target WPM = 170
```

Algorithm:

1. Generate with initial speed
2. Measure actual duration
3. Compute:

```text
actual_wpm =
word_count / (duration_seconds / 60)
```

4. Estimate:

```text
new_speed =
old_speed * target_wpm / actual_wpm
```

5. regenerate
6. Repeat maximum 2–3 iterations
7. Stop if relative error < 3%

Provider differences mean WPM is measured, not assumed.

---

# 12. Script Parsing

## Monologue

Split using sentence boundaries.

Avoid naive `.split(".")`.

Use a sentence tokenizer capable of handling:

```text
Mr.
Dr.
U.S.
e.g.
decimal numbers
quotations
```

## Dialogue

Recognize:

```text
[A]
text

[B]
text
```

and optionally:

```text
A: text
B: text
```

Canonical stored representation must be segments, not raw markup.

Parser output:

```json
[
  {
    "speaker": "A",
    "text": "Have you finished the report?"
  },
  {
    "speaker": "B",
    "text": "Not yet."
  }
]
```

---

# 13. Audio Rendering Pipeline

```text
Project
↓
Segment validation
↓
resolve effective voice
↓
resolve effective speed
↓
TTS cache lookup
↓
provider synthesize
↓
segment audio
↓
silence insertion
↓
normalization
↓
concatenate
↓
final audio
↓
storage
↓
DB metadata
```

## Effective voice

priority:

```text
segment override
↓
speaker voice
↓
project default
```

## Effective speed

priority:

```text
segment override
↓
speaker speed
↓
project default
```

---

# 14. TTS Cache

Cache key:

```text
sha256(
  provider
  + model
  + provider_voice_id
  + normalized_text
  + speed
  + instructions
  + output_format
)
```

Identical request should reuse audio.

Purpose:

- cost reduction
- latency reduction
- reproducibility

---

# 15. Audio Processing

Use FFmpeg.

Required operations:

- silence generation
- concatenation
- loudness normalization
- duration probing
- output format conversion

Avoid relying only on pydub for production pipeline.

pydub may be used as convenience wrapper.

Recommended final normalization:

EBU R128 / loudnorm.

---

# 16. Player

Frontend player must expose:

```text
play
pause
seek
currentTime
duration
playbackRate
volume
A marker
B marker
A-B loop
```

A-B repeat:

```ts
if (loopEnabled && currentTime >= loopEnd) {
  audio.currentTime = loopStart
  audio.play()
}
```

Transcript states:

```text
visible
hidden
reveal_after_first_play
```

MVP requires visible / hidden.

---

# 17. Storage

Audio files should not be stored directly in PostgreSQL.

Use object storage.

```text
audio/
  projects/{project_id}/
    segments/{segment_id}/{hash}.mp3
    renders/{render_id}.mp3
```

DB stores only metadata and storage key.

Development may use local filesystem adapter.

Production:

```text
S3
Cloudflare R2
compatible object storage
```

---

# 18. Backend Architecture

Recommended:

```text
backend/
  app/
    main.py

    api/
      routes/
        projects.py
        voices.py
        segments.py
        renders.py
        health.py

    domain/
      models/
      services/
      errors.py

    application/
      project_service.py
      render_service.py
      voice_service.py

    infrastructure/
      db/
      storage/
      audio/
      tts/
        base.py
        registry.py
        openai_adapter.py
        azure_adapter.py
        elevenlabs_adapter.py

    schemas/
      project.py
      voice.py
      render.py

    config.py
```

Rules:

- route handler should be thin
- provider SDK calls only in infrastructure/tts
- FFmpeg calls only in infrastructure/audio
- DB models must not leak into frontend schema directly

---

# 19. Frontend Architecture

```text
frontend/
  app/
    page.tsx
    create/
      page.tsx
    projects/
      [id]/
        page.tsx
    voices/
      page.tsx

  components/
    script/
      ScriptEditor.tsx
      DialogueEditor.tsx

    voice/
      VoiceSelector.tsx
      VoiceCard.tsx
      SpeakerVoicePanel.tsx

    player/
      ListeningPlayer.tsx
      ABRepeatControls.tsx
      TranscriptToggle.tsx

    timeline/
      SegmentList.tsx
      SegmentEditor.tsx

  lib/
    api/
    audio/
    types/

  hooks/
    useAudioPlayer.ts
    useProject.ts
```

State:

Use server state library only if needed.
Do not introduce Redux in MVP without clear need.

---

# 20. Rendering Jobs

MVP may render synchronously for short text.

Architecture should support asynchronous jobs.

Render states:

```text
queued
running
completed
failed
cancelled
```

`RenderJob` contains:

```text
id
project_id
status
progress
error_code
error_message
final_audio_asset_id
created_at
started_at
finished_at
```

For production long-form audio:

- API enqueues job
- worker renders
- frontend polls or uses SSE/WebSocket

MVP:
polling is sufficient.

---

# 21. Error Model

Normalized errors:

```text
INVALID_SCRIPT
VOICE_NOT_FOUND
VOICE_DISABLED
PROVIDER_UNAVAILABLE
PROVIDER_RATE_LIMITED
PROVIDER_AUTH_FAILED
PROVIDER_REQUEST_FAILED
AUDIO_PROCESSING_FAILED
STORAGE_FAILED
RENDER_CANCELLED
```

API error response:

```json
{
  "error": {
    "code": "PROVIDER_RATE_LIMITED",
    "message": "Speech generation is temporarily rate limited.",
    "retryable": true
  }
}
```

Never return provider secret details.

---

# 22. Security

Required:

- API keys server-side only
- no TTS secret in browser
- `.env` excluded from git
- user input length limits
- output storage access control
- request rate limits
- MIME validation
- signed URLs where necessary
- provider timeout
- max render duration
- logs must redact secrets

If custom voice upload is added later:
explicit consent workflow is required.

---

# 23. Observability

Structured logs:

```text
request_id
project_id
render_id
provider
model
voice_id
text_chars
latency_ms
cache_hit
result
```

Do NOT log full script by default.

Metrics:

```text
tts_requests_total
tts_failures_total
tts_latency_ms
tts_cache_hit_rate
render_duration_ms
audio_processing_failures
```

---

# 24. Testing

## Unit

- dialogue parser
- sentence parser
- effective voice resolution
- effective speed resolution
- cache key
- provider validation
- WPM calculation
- error mapping

## Adapter

Mock provider HTTP.

Verify mapping:

```text
domain request
→ provider request
```

## Integration

- create project
- parse script
- create speakers
- render
- store asset
- return URL

## E2E

Playwright.

Scenarios:

1. create monologue
2. choose voice
3. generate audio
4. play
5. hide transcript
6. A-B loop
7. save
8. reload

Dialogue:

1. paste `[A] / [B]`
2. assign different voices
3. render
4. confirm speaker segments use different configured voice IDs

---

# 25. Performance Targets

MVP targets:

```text
initial page load: reasonable on standard broadband
voice filter response: < 200 ms client-side
project save API: < 500 ms excluding network extremes
TTS generation: provider-dependent
audio UI remains responsive while rendering
```

Never block browser UI waiting on a long synchronous render.

---

# 26. Acceptance Criteria

MVP is accepted only when all are true.

## Monologue

- English script can be entered
- voice can be selected
- speed can be changed
- generated MP3 plays in browser

## Voice

- user can filter by accent
- user can filter by gender
- user can preview/select voice
- provider metadata is normalized

## Dialogue

Input:

```text
[A]
Hello.

[B]
Hi.
```

The application detects A and B.

A and B can receive different voices.

Generated render contains both.

## Player

- seek works
- playback rate works
- A-B repeat works
- transcript can be hidden

## Project

- save works
- refresh/reopen works
- settings persist

## Architecture

- provider SDK not imported from React
- provider SDK not imported from domain layer
- OpenAI adapter works
- Azure adapter exists
- ElevenLabs adapter exists
- failing provider produces normalized application error

---

# 27. Non-goals for MVP

Do not spend MVP time on:

- AI-generated questions
- pronunciation grading
- gamification
- social features
- payments
- native mobile apps
- complex auth organizations
- collaborative editing
- voice cloning
- realtime speech conversation

---

# 28. Recommended Defaults

```text
Mode:
Monologue

TTS Provider:
OpenAI

OpenAI Model:
gpt-4o-mini-tts

Generation speed:
1.0

Output:
mp3

Sentence pause:
250 ms

Paragraph pause:
600 ms

Playback rate:
1.0

Transcript:
visible
```

---

# 29. Future Listening-Test Preset System

Preset schema:

```json
{
  "id": "academic_lecture",
  "name": "Academic Lecture",
  "generation_speed": 1.05,
  "repeat_count": 1,
  "paragraph_pause_ms": 500,
  "transcript_visible_default": false,
  "voice_filters": {
    "language": "en"
  }
}
```

Avoid claiming presets exactly reproduce a particular exam.
They represent listening-training profiles.

---

# 30. Definition of Done

A feature is done when:

1. product behavior matches this spec
2. validation exists
3. error state exists
4. unit/integration tests exist where appropriate
5. no provider-specific concern leaks into domain/UI
6. user-facing loading state exists
7. relevant README is updated
