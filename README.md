# Listening Studio

Turn English text into listening practice material: paste a script, pick voices
and accents, and get a single audio file with an A-B repeat player and a
hideable transcript.

**Text-to-speech runs entirely on your machine.** No API key, no per-character
cost, no network round trip.

## What works today

- Monologue and dialogue (`[A]` / `[B]`, or `A:` / `B:`)
- Sentence splitting that survives abbreviations, so `Dr. Chen asked for it by
  3.30 p.m.` stays one segment
- 28 voices across American and British English, filterable by accent and gender
- Dialogue: choose how many speakers, then a voice per speaker
- Per-speaker voice and speed
- Generation speed (server-side) separate from playback rate (browser-only)
- MP3 render with inter-segment pauses and EBU R128 loudness normalization
- Player: seek, playback rate, A-B repeat, transcript show/hide
- Projects save and reopen
- Download the audio as MP3 and the script as PDF
- UI in English or Japanese, switchable from the header

## Interface language

The header carries an English / 日本語 toggle. The first visit follows the
browser's `Accept-Language`, and an explicit choice is remembered per browser.
`<html lang>` follows the choice, so screen readers and browser translation
behave correctly.

API error messages are localized in the frontend by their normalized error
code, so the backend stays language-agnostic. A code with no translation falls
back to the server's own English message rather than showing a bare key.

## Providers

| Provider | Status | Accents |
|---|---|---|
| `kokoro` | working, default, local | american, british |
| `openai` | implemented, unverified; set `OPENAI_API_KEY` | unknown |
| `azure` | implemented, unverified; set `AZURE_SPEECH_KEY` + `AZURE_SPEECH_REGION` | derived from locale |
| `elevenlabs` | implemented, unverified; set `ELEVENLABS_API_KEY` | from voice labels, else unknown |

Kokoro runs on your machine and needs no key. The hosted adapters are written
against each provider's documented REST API and covered by tests with mocked
HTTP, but **none has been exercised against the live service** — no credentials
were available. Treat the first real call as unverified.

Which engine produced a voice is not shown or filterable: it is not a
distinction a listener can hear. Accent and gender are.

### Failover

Off by default (`TTS_FAILOVER_ENABLED`). When enabled, a segment whose provider
is unavailable or rate limited retries on another registered provider — but
only with a voice of the same accent *and* gender, and never when either is
"unknown". A substitute that would obviously sound different is refused and the
render fails instead.

## Quick start

```bash
brew install postgresql@16 ffmpeg espeak-ng
brew services start postgresql@16
createdb -O listening listening_studio   # after creating the `listening` role
```

Backend:

```bash
cd backend
python3 -m venv .venv
.venv/bin/pip install -r requirements-dev.in
cp ../.env.example .env
.venv/bin/alembic upgrade head
.venv/bin/uvicorn app.main:app --reload --port 8000
```

Then import the voice catalog once:

```bash
curl -X POST http://localhost:8000/api/v1/voices/sync
```

Frontend:

```bash
cd frontend
npm install
npm run dev
```

Open <http://localhost:3000/create>.

`espeak-ng` is required, not optional -- see `backend/README.md` for why.

## Tests

```bash
cd backend && .venv/bin/python -m pytest      # 72 tests, no model loading
cd frontend && npm run e2e                    # 5 Playwright specs
```

Backend tests use a throwaway database and a stub TTS provider, so they never
download a model or touch the network. The E2E specs drive the real backend and
really do synthesize audio.

`backend/tests/test_layering.py` enforces the architecture by parsing the AST:
provider SDKs stay inside `infrastructure/tts`, the domain layer imports no
infrastructure, and subprocess calls stay out of the upper layers.

## Documentation

- `docs/SPEC.md` — the product requirements this implements
- `docs/API.md`, `docs/SCHEMA.sql` — the API and schema contracts
- `docs/PLAN.md` — implementation decisions, measured performance, and the
  three gaps found in the handed-over schema

## Known deviation from the SPEC

The SPEC's MVP acceptance criteria require the OpenAI adapter to actually run.
This build uses local providers instead, so no API key is needed. To keep the
deviation small the OpenAI adapter is fully implemented rather than stubbed:
setting `OPENAI_API_KEY` enables it with no code change.
