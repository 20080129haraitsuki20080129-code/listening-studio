# Listening Studio — API Contract

Base:

```text
/api/v1
```

JSON unless audio/file response is explicitly requested.

---

# Health

## GET /health

Response:

```json
{
  "status": "ok"
}
```

---

# Voices

## GET /voices

Query:

```text
provider?
language?
locale?
accent?
gender?
enabled?
q?
```

Response:

```json
{
  "items": [
    {
      "id": "uuid",
      "provider": "openai",
      "provider_voice_id": "marin",
      "name": "Marin",
      "language": "en",
      "locale": null,
      "accent": "unknown",
      "gender": "unknown",
      "age_group": "unknown",
      "style_tags": [],
      "preview_url": null,
      "enabled": true
    }
  ]
}
```

Important:
Do not fabricate gender/accent for voices when official/reliable metadata is unavailable.
Use `unknown`.

## POST /voices/sync

Admin/development endpoint.

Refresh provider voice catalog where supported.

---

# Projects

## POST /projects

Request:

```json
{
  "title": "Climate listening",
  "mode": "monologue",
  "source_text": "Climate change...",
  "transcript_visible_default": true
}
```

## GET /projects/{project_id}

Returns full editable project.

## PATCH /projects/{project_id}

Partial update.

## DELETE /projects/{project_id}

Soft delete preferred.

---

# Parsing

## POST /projects/{project_id}/parse

Request:

```json
{
  "source_text": "[A]\nHello.\n\n[B]\nHi.",
  "mode": "dialogue"
}
```

Response:

```json
{
  "speakers": [
    {
      "label": "A"
    },
    {
      "label": "B"
    }
  ],
  "segments": [
    {
      "order_index": 0,
      "speaker_label": "A",
      "text": "Hello."
    },
    {
      "order_index": 1,
      "speaker_label": "B",
      "text": "Hi."
    }
  ]
}
```

Persist only after explicit project update or use server-side transaction.

---

# Speakers

## POST /projects/{project_id}/speakers

Request:

```json
{
  "label": "A",
  "display_name": "Speaker A",
  "voice_id": "uuid",
  "generation_speed": 1.0,
  "default_pause_before_ms": 0,
  "default_pause_after_ms": 250
}
```

## PATCH /speakers/{speaker_id}

## DELETE /speakers/{speaker_id}

Reject deletion if referenced segments would become invalid unless replacement behavior is explicit.

---

# Segments

## PATCH /segments/{segment_id}

Request example:

```json
{
  "text": "Updated text.",
  "voice_id_override": null,
  "generation_speed_override": 1.05,
  "pause_before_ms": 100,
  "pause_after_ms": 400
}
```

Changing any TTS-affecting field invalidates associated segment render.

## POST /segments/{segment_id}/render

Render only one segment.

Useful for fast preview/editing.

Response:

```json
{
  "audio_asset_id": "uuid",
  "audio_url": "...",
  "duration_ms": 2210
}
```

---

# Renders

## POST /projects/{project_id}/renders

Request:

```json
{
  "format": "mp3"
}
```

Response:

```json
{
  "id": "uuid",
  "status": "queued",
  "progress": 0
}
```

## GET /renders/{render_id}

Response:

```json
{
  "id": "uuid",
  "project_id": "uuid",
  "status": "completed",
  "progress": 100,
  "audio_asset_id": "uuid",
  "audio_url": "...",
  "duration_ms": 124000,
  "error": null
}
```

## POST /renders/{render_id}/cancel

Best-effort cancellation.

---

# Audio

## GET /audio-assets/{audio_asset_id}

Return metadata and signed/public playback URL.

Do not proxy large audio through FastAPI in production unless required.

---

# Errors

All endpoints use:

```json
{
  "error": {
    "code": "VOICE_NOT_FOUND",
    "message": "The selected voice does not exist.",
    "retryable": false,
    "request_id": "..."
  }
}
```

Recommended HTTP mapping:

```text
INVALID_SCRIPT                422
VOICE_NOT_FOUND               404
VOICE_DISABLED                409
PROVIDER_AUTH_FAILED          502
PROVIDER_RATE_LIMITED         429/503
PROVIDER_UNAVAILABLE          503
PROVIDER_REQUEST_FAILED       502
AUDIO_PROCESSING_FAILED       500
STORAGE_FAILED                500
RENDER_CANCELLED              409
```

---

# Idempotency

Render request should accept:

```text
Idempotency-Key
```

Repeated identical request with same key should not create duplicate expensive renders.
