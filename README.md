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
- 52 voices across 6 English accents, filterable by accent, gender and provider
- Per-speaker voice and speed
- Generation speed (server-side) separate from playback rate (browser-only)
- MP3 render with inter-segment pauses and EBU R128 loudness normalization
- Player: seek, playback rate, A-B repeat, transcript show/hide
- Projects save and reopen
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
| `kokoro` | working, default | american, british |
| `macos_say` | working, macOS only | american, british, australian, irish, indian, south_african |
| `openai` | fully implemented; set `OPENAI_API_KEY` to enable | unknown |
| `azure` | stub | — |
| `elevenlabs` | stub | — |

Kokoro covers only American and British English, so the macOS `say` adapter is
registered alongside it to fill in the other accents. Both are local and free.

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
