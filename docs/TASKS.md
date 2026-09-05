# Listening Studio — Implementation Tasks

Codexは原則この順番で進める。

---

# Phase 0 — Repository Bootstrap

- [ ] monorepo root
- [ ] `frontend/`
- [ ] `backend/`
- [ ] Docker Compose
- [ ] PostgreSQL
- [ ] frontend env
- [ ] backend env
- [ ] lint/format
- [ ] backend pytest
- [ ] frontend Playwright setup
- [ ] root README

Completion:
both frontend and backend boot locally.

---

# Phase 1 — MVP Core

## Backend

- [ ] FastAPI
- [ ] health endpoint
- [ ] DB connection
- [ ] migrations
- [ ] Project CRUD
- [ ] Voice CRUD/read catalog
- [ ] Speaker CRUD
- [ ] Segment CRUD
- [ ] monologue parser
- [ ] dialogue parser
- [ ] TTSProvider interface
- [ ] provider registry
- [ ] OpenAI adapter
- [ ] Azure adapter stub
- [ ] ElevenLabs adapter stub
- [ ] local storage adapter
- [ ] FFmpeg wrapper
- [ ] segment rendering
- [ ] project rendering
- [ ] TTS cache
- [ ] normalized error system

## Frontend

- [ ] create page
- [ ] script editor
- [ ] mode selector
- [ ] voice selector
- [ ] accent filter
- [ ] gender filter
- [ ] speed slider
- [ ] speaker voice panel
- [ ] segment list
- [ ] generate button
- [ ] render status
- [ ] audio player
- [ ] playback speed
- [ ] transcript hide/show
- [ ] A-B repeat
- [ ] project save/reopen

---

# Phase 2 — Provider Expansion

- [ ] Azure real adapter
- [ ] Azure voice import
- [ ] Azure SSML mapping
- [ ] ElevenLabs real adapter
- [ ] ElevenLabs voice import
- [ ] normalize voice metadata
- [ ] provider health screen
- [ ] failover policy if enabled

Important:
Automatic failover must not silently switch to an obviously different voice.
If failover is implemented, it should be opt-in or voice-group aware.

---

# Phase 3 — Listening Test Mode

- [ ] repeat count
- [ ] repeat gap
- [ ] intro segment
- [ ] question segment
- [ ] question pause
- [ ] transcript hidden by default
- [ ] test preset schema
- [ ] render test package

---

# Phase 4 — WPM

- [ ] word counting
- [ ] actual WPM display
- [ ] target WPM input
- [ ] iterative speed adjustment
- [ ] tolerance threshold
- [ ] max attempts

---

# Phase 5 — Practice Features

- [ ] sentence repeat
- [ ] shadowing pause
- [ ] accent randomizer
- [ ] voice randomizer
- [ ] listening history
- [ ] bookmarks

---

# Test Gate Before MVP Merge

Must pass:

- [ ] parser unit tests
- [ ] TTS request mapping tests
- [ ] cache tests
- [ ] project API integration tests
- [ ] render integration test with mocked TTS
- [ ] E2E monologue
- [ ] E2E dialogue
- [ ] E2E A-B repeat
- [ ] no API secret shipped to frontend
