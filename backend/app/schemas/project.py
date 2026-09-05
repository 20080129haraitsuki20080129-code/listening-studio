from __future__ import annotations

import uuid
from datetime import datetime
from typing import Literal

from pydantic import Field

from .common import ApiModel

Mode = Literal["monologue", "dialogue", "listening_test", "shadowing"]


class ProjectCreate(ApiModel):
    title: str = Field(min_length=1, max_length=200)
    mode: Mode = "monologue"
    source_text: str = ""
    transcript_visible_default: bool = True


class ProjectUpdate(ApiModel):
    title: str | None = Field(default=None, min_length=1, max_length=200)
    mode: Mode | None = None
    source_text: str | None = None
    transcript_visible_default: bool | None = None
    default_voice_id: uuid.UUID | None = None
    default_generation_speed: float | None = Field(default=None, gt=0, le=4.0)
    sentence_pause_ms: int | None = Field(default=None, ge=0, le=60_000)
    paragraph_pause_ms: int | None = Field(default=None, ge=0, le=60_000)
    repeat_count: int | None = Field(default=None, ge=1, le=5)
    pause_between_repeats_ms: int | None = Field(default=None, ge=0, le=60_000)


class SpeakerCreate(ApiModel):
    label: str = Field(min_length=1, max_length=40)
    display_name: str | None = None
    voice_id: uuid.UUID | None = None
    generation_speed: float = Field(default=1.0, gt=0, le=4.0)
    default_pause_before_ms: int = Field(default=0, ge=0, le=60_000)
    default_pause_after_ms: int = Field(default=250, ge=0, le=60_000)


class SpeakerUpdate(ApiModel):
    display_name: str | None = None
    voice_id: uuid.UUID | None = None
    generation_speed: float | None = Field(default=None, gt=0, le=4.0)
    default_pause_before_ms: int | None = Field(default=None, ge=0, le=60_000)
    default_pause_after_ms: int | None = Field(default=None, ge=0, le=60_000)


class SpeedLevelOut(ApiModel):
    level: int
    speed: float
    wpm_typical: int
    wpm_min: int
    wpm_max: int
    reference: str | None = None


class SpeedLevelListOut(ApiModel):
    items: list[SpeedLevelOut]
    default_level: int


class SpeakerRosterSet(ApiModel):
    """How many speakers the dialogue should have."""

    count: int = Field(ge=1, le=8)


class SpeakerOut(ApiModel):
    id: uuid.UUID
    project_id: uuid.UUID
    label: str
    style_key: str | None = None
    display_name: str
    voice_id: uuid.UUID | None
    generation_speed: float
    default_pause_before_ms: int
    default_pause_after_ms: int


class SegmentUpdate(ApiModel):
    text: str | None = None
    speaker_id: uuid.UUID | None = None
    voice_id_override: uuid.UUID | None = None
    generation_speed_override: float | None = Field(default=None, gt=0, le=4.0)
    pause_before_ms: int | None = Field(default=None, ge=0, le=60_000)
    pause_after_ms: int | None = Field(default=None, ge=0, le=60_000)


class SegmentOut(ApiModel):
    id: uuid.UUID
    project_id: uuid.UUID
    order_index: int
    speaker_id: uuid.UUID | None
    text: str
    voice_id_override: uuid.UUID | None
    generation_speed_override: float | None
    pause_before_ms: int
    pause_after_ms: int
    audio_asset_id: uuid.UUID | None
    duration_ms: int | None
    word_count: int = 0


class ProjectOut(ApiModel):
    id: uuid.UUID
    title: str
    mode: Mode
    source_text: str
    styled_dialogue: bool = False
    transcript_visible_default: bool
    default_voice_id: uuid.UUID | None
    default_generation_speed: float
    sentence_pause_ms: int
    paragraph_pause_ms: int
    repeat_count: int
    pause_between_repeats_ms: int
    word_count: int = 0
    actual_wpm: float | None = None
    created_at: datetime
    updated_at: datetime
    speakers: list[SpeakerOut] = Field(default_factory=list)
    segments: list[SegmentOut] = Field(default_factory=list)


class ProjectSummaryOut(ApiModel):
    id: uuid.UUID
    title: str
    mode: Mode
    created_at: datetime
    updated_at: datetime


class ParseRequest(ApiModel):
    source_text: str | None = None
    mode: Mode | None = None
    persist: bool = True


class ParsedSpeakerOut(ApiModel):
    label: str


class ParsedSegmentOut(ApiModel):
    order_index: int
    speaker_label: str | None
    text: str


class ParseResponse(ApiModel):
    speakers: list[ParsedSpeakerOut]
    segments: list[ParsedSegmentOut]
