from __future__ import annotations

from fastapi import APIRouter, Depends, Query
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.deps import Container, get_container
from app.application.voice_service import VoiceFilters
from app.infrastructure.db.session import get_session
from app.schemas.voice import VoiceListOut, VoiceOut, VoiceSyncOut

router = APIRouter(tags=["voices"])


@router.get("/voices", response_model=VoiceListOut)
async def list_voices(
    provider: str | None = None,
    language: str | None = None,
    locale: str | None = None,
    accent: str | None = None,
    gender: str | None = None,
    enabled: bool | None = Query(default=True),
    q: str | None = None,
    session: AsyncSession = Depends(get_session),
    container: Container = Depends(get_container),
) -> VoiceListOut:
    voices = await container.voices.list_voices(
        session,
        VoiceFilters(
            provider=provider,
            language=language,
            locale=locale,
            accent=accent,
            gender=gender,
            enabled=enabled,
            q=q,
        ),
    )
    return VoiceListOut(items=[VoiceOut.model_validate(v) for v in voices])


@router.post("/voices/sync", response_model=VoiceSyncOut)
async def sync_voices(
    session: AsyncSession = Depends(get_session),
    container: Container = Depends(get_container),
) -> VoiceSyncOut:
    created, updated, providers = await container.voices.sync(session)
    await session.commit()
    return VoiceSyncOut(created=created, updated=updated, providers=providers)
