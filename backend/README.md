# Listening Studio — Backend

FastAPI + PostgreSQL + FFmpeg. Text-to-speech runs locally, so no API key is
needed to use it.

## Prerequisites

```bash
brew install postgresql@16 ffmpeg espeak-ng
brew services start postgresql@16
```

`espeak-ng` is not optional. Kokoro depends on it for grapheme-to-phoneme
conversion, and the copy bundled with `espeakng-loader` has a build-machine
path compiled into it, so synthesis fails with a missing `phontab` unless a
real install is present. `app/config.py` finds it automatically on the usual
macOS and Debian paths; override with `PHONEMIZER_ESPEAK_LIBRARY` and
`ESPEAK_DATA_PATH` if yours lives elsewhere.

## Setup

```bash
python3 -m venv .venv
.venv/bin/pip install -r requirements-dev.in
cp ../.env.example .env
```

Create the database:

```bash
createdb -O listening listening_studio
.venv/bin/alembic upgrade head
```

## Run

```bash
.venv/bin/uvicorn app.main:app --reload --port 8000
```

Startup warms up Kokoro, which takes a few seconds. It is worth it: the first
synthesis is otherwise 3-4s slower than every later one.

Populate the voice catalog once the server is up:

```bash
curl -X POST http://localhost:8000/api/v1/voices/sync
```

Interactive API docs: <http://localhost:8000/docs>

## Phase 2 notes

`app/infrastructure/tts/normalization.py` is the single place provider metadata
becomes catalog metadata. Anything a provider does not state resolves to
`unknown`; nothing is inferred from a name.

Failover is opt-in via `TTS_FAILOVER_ENABLED` and is voice-group aware: a
substitute must match accent *and* gender, and "unknown" never matches. See
`tests/test_failover.py`.

## Tests

```bash
.venv/bin/python -m pytest
```

Tests use a throwaway `listening_studio_test` database and a stub TTS provider,
so they never load the model or hit a network. `tests/test_layering.py` enforces
the architectural boundaries the SPEC requires -- provider SDKs stay inside
`infrastructure/tts`, and the domain layer stays free of infrastructure.

## Providers

| Provider | Status | Accents |
|---|---|---|
| `kokoro` | working, default, local, no key | american, british |
| `openai` | implemented, **unverified** | unknown (OpenAI publishes no accent/gender metadata) |
| `azure` | implemented, **unverified** | derived from the voice's locale |
| `elevenlabs` | implemented, **unverified** | from voice labels, `unknown` when absent |

"Unverified" means the adapter is written against the provider's documented
REST API and its request mapping is covered by `tests/test_adapters.py` with
mocked HTTP, but it has never run against the live service because no
credentials were available. Each registers only when its key is set.

Adding a provider means implementing `TTSProvider` in
`app/infrastructure/tts/` and registering it in `app/api/deps.py`. Nothing
above that layer changes.
