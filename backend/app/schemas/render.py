from __future__ import annotations

import uuid
from typing import Literal

from .common import ApiModel

OutputFormat = Literal["mp3", "wav", "opus", "aac", "flac"]


class RenderCreate(ApiModel):
    format: OutputFormat = "mp3"


class RenderOut(ApiModel):
    id: uuid.UUID
    project_id: uuid.UUID
    status: str
    progress: int
    audio_asset_id: uuid.UUID | None = None
    audio_url: str | None = None
    duration_ms: int | None = None
    error: dict | None = None


class SegmentRenderOut(ApiModel):
    audio_asset_id: uuid.UUID
    audio_url: str
    duration_ms: int


class AudioAssetOut(ApiModel):
    id: uuid.UUID
    storage_key: str
    mime_type: str
    format: str
    duration_ms: int
    size_bytes: int
    audio_url: str
