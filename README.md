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
- Seven speed levels labelled by pace, anchored to exam, news and argument
  speech, separate from the browser-only playback rate
- The pace actually achieved is measured from the rendered audio and reported
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

## Signing in

Projects belong to the person who made them. Sign-in is delegated to Google or
X, so **no password is ever stored here** — there is no credential to leak.

Configure either provider (both are free to register) and enforcement turns on:

```bash
# Google — https://console.cloud.google.com/apis/credentials
#   Authorised redirect URI: <backend>/api/v1/auth/google/callback
GOOGLE_CLIENT_ID=...
GOOGLE_CLIENT_SECRET=...

# X — https://developer.x.com/en/portal/dashboard
#   Callback URI: <backend>/api/v1/auth/x/callback
X_CLIENT_ID=...
X_CLIENT_SECRET=...

SESSION_SECRET=$(openssl rand -hex 32)
```

With neither configured the app runs open, because there would be no way to
sign in at all — convenient locally, never acceptable in production. The server
**refuses to start** with `APP_ENV=production` while `SESSION_SECRET` is the
default or `COOKIE_SECURE` is off.

Accounts are keyed on (provider, account id), never on email: addresses change
hands, and X does not release one at this scope, so matching on email could let
two different people share an account.

Projects created before sign-in existed have no owner and are simply
unreachable once it is on, rather than falling to whoever asks first.

### What is and is not protected

Every project, segment, speaker and render is scoped to its owner — reading
someone else's returns 403, and a segment id is not a way around it.

Audio files are the deliberate exception. The TTS cache shares one rendered
sentence between everyone who asks for the same text in the same voice, so an
audio asset genuinely has no single owner. Those endpoints require sign-in and
then rely on the id being an unguessable content hash — a capability URL, which
is the model SPEC section 17 anticipates with signed URLs.

## Speed levels

Generation speed is chosen as one of seven levels, labelled by the pace it
produces and anchored to material people recognise:

| Level | Multiplier | Typical pace | Varies by voice | Anchor |
|---|---|---|---|---|
| 1 | 0.76 | 105 wpm | 96–110 | |
| 2 | 0.84 | 124 wpm | 111–131 | |
| 3 | 0.92 | 135 wpm | 121–142 | |
| 4 | 1.08 | 150 wpm | 136–156 | university entrance exam (default) |
| 5 | 1.16 | 158 wpm | 143–165 | |
| 6 | 1.30 | 175 wpm | 162–183 | native news broadcast |
| 7 | 1.34 | 203 wpm | 181–214 | heated native argument |

The anchor figures are widely cited approximations, not published standards.

Everything else is **measured, not assumed** — SPEC section 11 is explicit that
provider differences make WPM something you measure. The figures come from a
127-word passage read by four Kokoro voices, synthesized one sentence at a time
exactly as the render pipeline does.

Three things measurement showed, which shape the scale:

- **Voices differ by about 20 wpm** at the same multiplier — more than the gap
  between neighbouring levels. So a level advertises a typical pace and the
  observed spread, and the app reports the **actual** rate once rendered.
- **Kokoro's response is not linear**, so the multipliers are not evenly
  spaced; they were picked so the resulting pace lands on the anchors. Pace
  also steps up sharply between 1.30 and 1.34 (175 to 203 wpm), which is why
  the gap from level 6 to 7 is the widest — no multiplier gives the ~190 wpm
  in between.
- **Very short passages come out slower than the label.** Each utterance
  carries fixed overhead, and with few words there is little to amortize it
  over: at multiplier 1.00, 9 words gives 127 wpm, 29 words 142, and it is
  flat from there through 127 words. The labels describe passages of a
  sentence or two upward, which is what listening material actually is.

Measured against the running app with a 5-sentence passage, levels 1, 4, 6 and
7 came out at 109, 155, 181 and 211 wpm — each inside its advertised spread.

The levels are served from `GET /speed-levels` rather than hard-coded in the
UI, because they describe the speech engine; a different engine would need
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

## Deploying

See [DEPLOY.md](DEPLOY.md). The stack it describes — Netlify, Hugging Face
Spaces and Supabase — is free and none of it asks for a card.

Kokoro needs PyTorch and about 1GB of memory, so the backend has to be a real
container: Netlify Functions, Vercel and the other serverless tiers can host
the frontend but not the backend.

## Documentation

- `docs/SPEC.md` — the product requirements this implements
- `docs/API.md`, `docs/SCHEMA.sql` — the API and schema contracts
- [DEPLOY.md](DEPLOY.md) — deployment, and what each free tier actually allows
- `docs/PLAN.md` — implementation decisions, measured performance, and the
  three gaps found in the handed-over schema

## Known deviation from the SPEC

The SPEC's MVP acceptance criteria require the OpenAI adapter to actually run.
This build uses local providers instead, so no API key is needed. To keep the
deviation small the OpenAI adapter is fully implemented rather than stubbed:
setting `OPENAI_API_KEY` enables it with no code change.
