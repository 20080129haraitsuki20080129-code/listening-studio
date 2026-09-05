from __future__ import annotations

import uuid

from fastapi import APIRouter, Depends, Response, status
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.deps import Container, get_container
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
)

router = APIRouter(tags=["projects"])


@router.post("/projects", response_model=ProjectOut, status_code=201)
async def create_project(
    payload: ProjectCreate,
    session: AsyncSession = Depends(get_session),
    container: Container = Depends(get_container),
) -> ProjectOut:
    project = await container.projects.create(session, payload)
    await session.commit()
    await session.refresh(project)
    return ProjectOut.model_validate(project)


@router.get("/projects", response_model=list[ProjectSummaryOut])
async def list_projects(
    session: AsyncSession = Depends(get_session),
    container: Container = Depends(get_container),
) -> list[ProjectSummaryOut]:
    projects = await container.projects.list_all(session)
    return [ProjectSummaryOut.model_validate(p) for p in projects]


@router.get("/projects/{project_id}", response_model=ProjectOut)
async def get_project(
    project_id: uuid.UUID,
    session: AsyncSession = Depends(get_session),
    container: Container = Depends(get_container),
) -> ProjectOut:
    project = await container.projects.get(session, project_id)
    return ProjectOut.model_validate(project)


@router.patch("/projects/{project_id}", response_model=ProjectOut)
async def update_project(
    project_id: uuid.UUID,
    payload: ProjectUpdate,
    session: AsyncSession = Depends(get_session),
    container: Container = Depends(get_container),
) -> ProjectOut:
    project = await container.projects.update(session, project_id, payload)
    await session.commit()
    await session.refresh(project)
    return ProjectOut.model_validate(project)


@router.delete("/projects/{project_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_project(
    project_id: uuid.UUID,
    session: AsyncSession = Depends(get_session),
    container: Container = Depends(get_container),
) -> Response:
    await container.projects.soft_delete(session, project_id)
    await session.commit()
    return Response(status_code=status.HTTP_204_NO_CONTENT)


@router.post("/projects/{project_id}/parse", response_model=ParseResponse)
async def parse_project(
    project_id: uuid.UUID,
    payload: ParseRequest,
    session: AsyncSession = Depends(get_session),
    container: Container = Depends(get_container),
) -> ParseResponse:
    project = await container.projects.get(session, project_id)
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


@router.post(
    "/projects/{project_id}/speakers", response_model=SpeakerOut, status_code=201
)
async def create_speaker(
    project_id: uuid.UUID,
    payload: SpeakerCreate,
    session: AsyncSession = Depends(get_session),
    container: Container = Depends(get_container),
) -> SpeakerOut:
    from app.infrastructure.db.models import Speaker

    await container.projects.get(session, project_id)
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
