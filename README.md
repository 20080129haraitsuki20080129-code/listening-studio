# Listening Studio

Turn English text into listening practice material: paste a script, pick voices
and accents, and get a single audio file with an A-B repeat player and a
hideable transcript.

**Text-to-speech runs entirely on your machine.** No API key, no per-character
cost, no network round trip.

## What works today

- Monologue and dialogue
- Dialogue speakers marked by **text styling** — bold / italic / underline with
  the usual ⌘/Ctrl+B, I, U — or by `[A]` / `[B]` markers if you prefer typing
- Sentence splitting that survives abbreviations, so `Dr. Chen asked for it by
  3.30 p.m.` stays one segment
- 28 voices across American and British English, filterable by accent and gender
- Up to 8 speakers, one per style combination
- Per-speaker voice and speed
- Seven speed levels labelled by pace in words per minute, separate from the
  browser-only playback rate
- Repeat the passage up to five times with a configurable gap
- Word counts per segment and per script
- MP3 render with inter-segment pauses and EBU R128 loudness normalization
- Player: seek, playback rate, A-B repeat, transcript show/hide
- Projects save and reopen
- Download the audio as MP3 and the script as PDF, speakers lettered A, B, C
- UI in English or Japanese, switchable from the header

## Marking speakers

Bold, italic and underline are independent, so there are exactly eight
combinations — which is where the eight-speaker ceiling comes from:

| Voice | Style | | Voice | Style |
|---|---|---|---|---|
| 1 | plain | | 5 | bold + italic |
| 2 | **bold** | | 6 | bold + underline |
| 3 | *italic* | | 7 | italic + underline |
| 4 | underline | | 8 | bold + italic + underline |

The mapping is fixed: bold is always Voice 2, whatever else the script
contains, so it never shifts as you edit.

Styling is read per line, not per character, so emphasising a single word
inside a turn does not hand that word to a different speaker.

`[A]` / `[B]` markers still work. When a script has no styling, markers decide;
when it has neither, the whole script is one speaker.

The transcript PDF always letters speakers A, B, C, however they were marked.
The letters follow position rather than the stored label: a styled dialogue
using plain, bold and underline stores A, B and D internally, and printing "D"
with no C in sight would read as a mistake. Position also keeps the letters
lined up with the editor's numbered slots, so Voice 3 is always C.

## Speed levels

Generation speed is chosen as one of seven levels, each labelled by the pace it
produces rather than by a bare multiplier:

| Level | Multiplier | Pace |
|---|---|---|
| 1 | 0.70 | 95–105 wpm |
| 2 | 0.80 | 105–125 wpm |
| 3 | 0.90 | 125–140 wpm |
| 4 | 1.00 | 140–150 wpm (default) |
| 5 | 1.10 | 150–160 wpm |
| 6 | 1.20 | 160–170 wpm |
| 7 | 1.30 | 170–185 wpm |

The bands are **measured, not assumed** — SPEC section 11 is explicit that
provider differences make WPM something you measure. They come from timing a
47-word passage on Kokoro with two voices, and the ranges bracket both because
voices differ by a few words per minute at the same multiplier.

The scale stops at 1.30 because Kokoro's pace jumps discontinuously above it:
1.30 gives about 176 wpm and 1.40 about 213, so a level there would not sit
evenly between its neighbours.

The levels are served from `GET /speed-levels` rather than hard-coded in the
UI, because the bands describe the speech engine; a different engine would need
different ones.

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
