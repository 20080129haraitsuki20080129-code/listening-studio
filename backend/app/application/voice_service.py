"""Voice catalog.

Accent and gender are our metadata, not TTS API parameters (SPEC 2.2). The
catalog is the only place the UI filters on, so adapters normalize into it and
anything genuinely unknown stays "unknown" rather than being invented.
"""

from __future__ import annotations

from dataclasses import dataclass

from sqlalchemy import Select, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.domain.errors import VoiceDisabled, VoiceNotFound
from app.infrastructure.db.models import Voice
from app.infrastructure.tts.registry import TTSProviderRegistry


@dataclass(frozen=True)
class VoiceFilters:
    provider: str | None = None
    language: str | None = None
    locale: str | None = None
    accent: str | None = None
    gender: str | None = None
    enabled: bool | None = True
    q: str | None = None


class VoiceService:
    def __init__(self, registry: TTSProviderRegistry) -> None:
        self._registry = registry

    async def list_voices(
        self, session: AsyncSession, filters: VoiceFilters
    ) -> list[Voice]:
        stmt: Select = select(Voice)
        if filters.provider:
            stmt = stmt.where(Voice.provider == filters.provider)
        if filters.language:
            stmt = stmt.where(Voice.language == filters.language)
        if filters.locale:
            stmt = stmt.where(Voice.locale == filters.locale)
        if filters.accent:
            stmt = stmt.where(Voice.accent == filters.accent)
        if filters.gender:
            stmt = stmt.where(Voice.gender == filters.gender)
        if filters.enabled is not None:
            stmt = stmt.where(Voice.enabled.is_(filters.enabled))
        if filters.q:
            stmt = stmt.where(Voice.name.ilike(f"%{filters.q}%"))
        stmt = stmt.order_by(Voice.provider, Voice.accent, Voice.name)
        return list((await session.execute(stmt)).scalars())

    async def require_voice(self, session: AsyncSession, voice_id) -> Voice:
        voice = await session.get(Voice, voice_id)
        if voice is None:
            raise VoiceNotFound
        if not voice.enabled:
            raise VoiceDisabled
        return voice

    async def sync(self, session: AsyncSession) -> tuple[int, int, list[str]]:
        """Refresh the catalog from every registered provider.

        Existing rows keep their id so project references survive a resync.
        """
        created = 0
        updated = 0
        touched: list[str] = []

        for name in self._registry.names():
            adapter = self._registry.get(name)
            descriptors = await adapter.list_voices()
            if not descriptors:
                continue
            touched.append(name)

            existing = {
                voice.provider_voice_id: voice
                for voice in (
                    await session.execute(select(Voice).where(Voice.provider == name))
                ).scalars()
            }

            for descriptor in descriptors:
                row = existing.get(descriptor.provider_voice_id)
                if row is None:
                    session.add(
                        Voice(
                            provider=name,
                            provider_voice_id=descriptor.provider_voice_id,
                            provider_model_hint=descriptor.provider_model_hint,
                            name=descriptor.name,
                            language=descriptor.language,
                            locale=descriptor.locale,
                            accent=descriptor.accent,
                            gender=descriptor.gender,
                            age_group=descriptor.age_group,
                            style_tags=list(descriptor.style_tags),
                            preview_url=descriptor.preview_url,
                            voice_metadata=dict(descriptor.metadata),
                        )
                    )
                    created += 1
                else:
                    row.name = descriptor.name
                    row.language = descriptor.language
                    row.locale = descriptor.locale
                    row.accent = descriptor.accent
                    row.gender = descriptor.gender
                    row.age_group = descriptor.age_group
                    row.style_tags = list(descriptor.style_tags)
                    row.preview_url = descriptor.preview_url
                    row.provider_model_hint = descriptor.provider_model_hint
                    updated += 1

        await session.flush()
        return created, updated, touched
