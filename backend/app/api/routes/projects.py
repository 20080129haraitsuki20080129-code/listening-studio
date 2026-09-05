from __future__ import annotations

import uuid

from fastapi import APIRouter, Depends, Response, status
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.deps import Container, get_container, require_user
from app.domain.speed_levels import DEFAULT_LEVEL, SPEED_LEVELS
from app.infrastructure.db.models import User
from app.infrastructure.db.session import get_session
from app.schemas.project import (
    ParsedSegmentOut,
    ParsedSpeakerOut,
    ParseRequest,
    ParseResponse,
    ProjectCreate,
    ProjectOut,
    ProjectSummaryOut,
    ProjectUpdate,
    SpeakerCreate,
    SpeakerOut,
    SpeakerRosterSet,
    SpeedLevelListOut,
    SpeedLevelOut,
)

router = APIRouter(tags=["projects"])


def _owner(user: User | None) -> uuid.UUID | None:
    """The id to scope queries by, or None when sign-in is switched off."""
    return user.id if user else None


@router.get("/speed-levels", response_model=SpeedLevelListOut)
async def list_speed_levels() -> SpeedLevelListOut:
    """The seven generation-speed presets, labelled by words per minute.

    Served rather than hard-coded in the UI because the bands were measured
    against the speech engine; a different engine would need different ones.
    """
    return SpeedLevelListOut(
        items=[SpeedLevelOut.model_validate(level) for level in SPEED_LEVELS],
        default_level=DEFAULT_LEVEL,
    )


@router.post("/projects", response_model=ProjectOut, status_code=201)
async def create_project(
    payload: ProjectCreate,
    session: AsyncSession = Depends(get_session),
    container: Container = Depends(get_container),
    user: User | None = Depends(require_user),
) -> ProjectOut:
    project = await container.projects.create(session, payload, _owner(user))
    await session.commit()
    await session.refresh(project)
    return ProjectOut.model_validate(project)


@router.get("/projects", response_model=list[ProjectSummaryOut])
async def list_projects(
    session: AsyncSession = Depends(get_session),
    container: Container = Depends(get_container),
    user: User | None = Depends(require_user),
) -> list[ProjectSummaryOut]:
    projects = await container.projects.list_all(session, _owner(user))
    return [ProjectSummaryOut.model_validate(p) for p in projects]


@router.get("/projects/{project_id}", response_model=ProjectOut)
async def get_project(
    project_id: uuid.UUID,
    session: AsyncSession = Depends(get_session),
    container: Container = Depends(get_container),
    user: User | None = Depends(require_user),
) -> ProjectOut:
    project = await container.projects.get(session, project_id, _owner(user))
    return ProjectOut.model_validate(project)


@router.patch("/projects/{project_id}", response_model=ProjectOut)
async def update_project(
    project_id: uuid.UUID,
    payload: ProjectUpdate,
    session: AsyncSession = Depends(get_session),
    container: Container = Depends(get_container),
    user: User | None = Depends(require_user),
) -> ProjectOut:
    project = await container.projects.update(
        session, project_id, payload, _owner(user)
    )
    await session.commit()
    await session.refresh(project)
    return ProjectOut.model_validate(project)


@router.delete("/projects/{project_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_project(
    project_id: uuid.UUID,
    session: AsyncSession = Depends(get_session),
    container: Container = Depends(get_container),
    user: User | None = Depends(require_user),
) -> Response:
    await container.projects.soft_delete(session, project_id, _owner(user))
    await session.commit()
    return Response(status_code=status.HTTP_204_NO_CONTENT)


@router.post("/projects/{project_id}/parse", response_model=ParseResponse)
async def parse_project(
    project_id: uuid.UUID,
    payload: ParseRequest,
    session: AsyncSession = Depends(get_session),
    container: Container = Depends(get_container),
    user: User | None = Depends(require_user),
) -> ParseResponse:
    project = await container.projects.get(session, project_id, _owner(user))
    source_text = (
        payload.source_text if payload.source_text is not None else project.source_text
    )
    mode = payload.mode or project.mode

    parsed = container.projects.parse(source_text, mode)

    if payload.persist:
        project.source_text = source_text
        project.mode = mode
        await container.projects.apply_parse(session, project, parsed)
        await session.commit()

    labels: dict[str, None] = {}
    for item in parsed:
        if item.speaker_label:
            labels.setdefault(item.speaker_label, None)

    return ParseResponse(
        speakers=[ParsedSpeakerOut(label=label) for label in labels],
        segments=[
            ParsedSegmentOut(
                order_index=item.order_index,
                speaker_label=item.speaker_label,
                text=item.text,
            )
            for item in parsed
        ],
    )


@router.put("/projects/{project_id}/speakers", response_model=list[SpeakerOut])
async def set_speaker_roster(
    project_id: uuid.UUID,
    payload: SpeakerRosterSet,
    session: AsyncSession = Depends(get_session),
    container: Container = Depends(get_container),
    user: User | None = Depends(require_user),
) -> list[SpeakerOut]:
    project = await container.projects.get(session, project_id, _owner(user))
    speakers = await container.projects.set_speaker_roster(
        session, project, payload.count
    )
    await session.commit()
    return [SpeakerOut.model_validate(s) for s in speakers]


@router.post(
    "/projects/{project_id}/speakers", response_model=SpeakerOut, status_code=201
)
async def create_speaker(
    project_id: uuid.UUID,
    payload: SpeakerCreate,
    session: AsyncSession = Depends(get_session),
    container: Container = Depends(get_container),
    user: User | None = Depends(require_user),
) -> SpeakerOut:
    from app.infrastructure.db.models import Speaker

    await container.projects.get(session, project_id, _owner(user))
    if payload.voice_id is not None:
        await container.voices.require_voice(session, payload.voice_id)

    speaker = Speaker(
        project_id=project_id,
        label=payload.label,
        display_name=payload.display_name or f"Speaker {payload.label}",
        voice_id=payload.voice_id,
        generation_speed=payload.generation_speed,
        default_pause_before_ms=payload.default_pause_before_ms,
        default_pause_after_ms=payload.default_pause_after_ms,
    )
    session.add(speaker)
    await session.commit()
    await session.refresh(speaker)
    return SpeakerOut.model_validate(speaker)
