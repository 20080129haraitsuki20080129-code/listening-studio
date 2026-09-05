from __future__ import annotations

import uuid

from fastapi import APIRouter, Depends, Response, status
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.deps import (
    Container,
    get_container,
    rate_limit_renders,
    require_user,
)
from app.infrastructure.db.models import User
from app.infrastructure.db.session import get_session
from app.schemas.project import SegmentOut, SegmentUpdate, SpeakerOut, SpeakerUpdate
from app.schemas.render import SegmentRenderOut

router = APIRouter(tags=["segments"])


def _owner(user: User | None) -> uuid.UUID | None:
    return user.id if user else None


@router.patch("/segments/{segment_id}", response_model=SegmentOut)
async def update_segment(
    segment_id: uuid.UUID,
    payload: SegmentUpdate,
    session: AsyncSession = Depends(get_session),
    container: Container = Depends(get_container),
    user: User | None = Depends(require_user),
) -> SegmentOut:
    data = payload.model_dump(exclude_unset=True)
    if data.get("voice_id_override") is not None:
        await container.voices.require_voice(session, data["voice_id_override"])
    segment = await container.projects.update_segment(
        session, segment_id, data, _owner(user)
    )
    await session.commit()
    await session.refresh(segment)
    return SegmentOut.model_validate(segment)


@router.post(
    "/segments/{segment_id}/render",
    response_model=SegmentRenderOut,
    dependencies=[Depends(rate_limit_renders)],
)
async def render_segment(
    segment_id: uuid.UUID,
    session: AsyncSession = Depends(get_session),
    container: Container = Depends(get_container),
    user: User | None = Depends(require_user),
) -> SegmentRenderOut:
    segment = await container.projects.get_segment(session, segment_id, _owner(user))
    project = await container.projects.get(session, segment.project_id, _owner(user))
    asset = await container.renders.render_segment(session, project, segment)
    await session.commit()
    return SegmentRenderOut(
        audio_asset_id=asset.id,
        audio_url=container.storage.public_url(asset.storage_key),
        duration_ms=asset.duration_ms,
    )


@router.delete("/speakers/{speaker_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_speaker(
    speaker_id: uuid.UUID,
    session: AsyncSession = Depends(get_session),
    container: Container = Depends(get_container),
    user: User | None = Depends(require_user),
) -> Response:
    await container.projects.delete_speaker(session, speaker_id, _owner(user))
    await session.commit()
    return Response(status_code=status.HTTP_204_NO_CONTENT)


@router.patch("/speakers/{speaker_id}", response_model=SpeakerOut)
async def update_speaker(
    speaker_id: uuid.UUID,
    payload: SpeakerUpdate,
    session: AsyncSession = Depends(get_session),
    container: Container = Depends(get_container),
    user: User | None = Depends(require_user),
) -> SpeakerOut:
    data = payload.model_dump(exclude_unset=True)
    if data.get("voice_id") is not None:
        await container.voices.require_voice(session, data["voice_id"])
    speaker = await container.projects.get_speaker(session, speaker_id, _owner(user))
    for field, value in data.items():
        setattr(speaker, field, value)
    await session.commit()
    await session.refresh(speaker)
    return SpeakerOut.model_validate(speaker)
