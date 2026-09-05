from __future__ import annotations

import uuid

from .common import ApiModel


class VoiceOut(ApiModel):
    id: uuid.UUID
    provider: str
    provider_voice_id: str
    name: str
    language: str
    locale: str | None
    accent: str | None
    gender: str
    age_group: str
    style_tags: list[str]
    preview_url: str | None
    enabled: bool


class VoiceListOut(ApiModel):
    items: list[VoiceOut]


class VoiceSyncOut(ApiModel):
    created: int
    updated: int
    providers: list[str]
