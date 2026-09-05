from __future__ import annotations

import asyncio
import uuid

from fastapi import APIRouter, Depends, Header, Response
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.deps import Container, get_container
from app.api.downloads import content_disposition, safe_filename
from app.domain.errors import InvalidScript, NotFound
from app.infrastructure.db.models import AudioAsset, RenderJob
from app.infrastructure.db.session import get_session
from app.schemas.render import AudioAssetOut, RenderCreate, RenderOut

router = APIRouter(tags=["renders"])

# Background tasks are garbage-collected if nothing holds a reference.
_running: set[asyncio.Task] = set()


async def _to_out(
    session: AsyncSession, container: Container, job: RenderJob
) -> RenderOut:
    audio_url = None
    duration_ms = None
    if job.final_audio_asset_id:
        asset = await session.get(AudioAsset, job.final_audio_asset_id)
        if asset is not None:
            audio_url = container.storage.public_url(asset.storage_key)
            duration_ms = asset.duration_ms
    error = None
    if job.error_code:
        error = {"code": job.error_code, "message": job.error_message}
    return RenderOut(
        id=job.id,
        project_id=job.project_id,
        status=job.status,
        progress=job.progress,
        audio_asset_id=job.final_audio_asset_id,
        audio_url=audio_url,
        duration_ms=duration_ms,
        error=error,
    )


@router.post(
    "/projects/{project_id}/renders", response_model=RenderOut, status_code=202
)
async def create_render(
    project_id: uuid.UUID,
    payload: RenderCreate,
    idempotency_key: str | None = Header(default=None, alias="Idempotency-Key"),
    session: AsyncSession = Depends(get_session),
    container: Container = Depends(get_container),
) -> RenderOut:
    await container.projects.get(session, project_id)

    # Repeating a request with the same key must not start a second expensive
    # render (API.md); hand back the job already in flight.
    if idempotency_key:
        existing = (
            await session.execute(
                select(RenderJob).where(
                    RenderJob.project_id == project_id,
                    RenderJob.idempotency_key == idempotency_key,
                )
            )
        ).scalar_one_or_none()
        if existing is not None:
            return await _to_out(session, container, existing)

    job = RenderJob(
        project_id=project_id,
        status="queued",
        progress=0,
        output_format=payload.format,
        idempotency_key=idempotency_key,
    )
    session.add(job)
    await session.commit()
    await session.refresh(job)

    task = asyncio.create_task(container.renders.run_job(job.id))
    _running.add(task)
    task.add_done_callback(_running.discard)

    return await _to_out(session, container, job)


@router.get("/renders/{render_id}", response_model=RenderOut)
async def get_render(
    render_id: uuid.UUID,
    session: AsyncSession = Depends(get_session),
    container: Container = Depends(get_container),
) -> RenderOut:
    job = await session.get(RenderJob, render_id)
    if job is None:
        raise NotFound("The render does not exist.")
    return await _to_out(session, container, job)


@router.post("/renders/{render_id}/cancel", response_model=RenderOut)
async def cancel_render(
    render_id: uuid.UUID,
    session: AsyncSession = Depends(get_session),
    container: Container = Depends(get_container),
) -> RenderOut:
    job = await session.get(RenderJob, render_id)
    if job is None:
        raise NotFound("The render does not exist.")
    if job.status in ("queued", "running"):
        job.status = "cancelled"
        await session.commit()
        await session.refresh(job)
    return await _to_out(session, container, job)


@router.get("/audio-assets/{audio_asset_id}", response_model=AudioAssetOut)
async def get_audio_asset(
    audio_asset_id: uuid.UUID,
    session: AsyncSession = Depends(get_session),
    container: Container = Depends(get_container),
) -> AudioAssetOut:
    asset = await session.get(AudioAsset, audio_asset_id)
    if asset is None:
        raise NotFound("The audio asset does not exist.")
    return AudioAssetOut(
        id=asset.id,
        storage_key=asset.storage_key,
        mime_type=asset.mime_type,
        format=asset.format,
        duration_ms=asset.duration_ms,
        size_bytes=asset.size_bytes,
        audio_url=container.storage.public_url(asset.storage_key),
    )


@router.get("/renders/{render_id}/download")
async def download_render(
    render_id: uuid.UUID,
    session: AsyncSession = Depends(get_session),
    container: Container = Depends(get_container),
) -> Response:
    """The finished audio, as an attachment named after the project."""
    job = await session.get(RenderJob, render_id)
    if job is None:
        raise NotFound("The render does not exist.")
    if job.status != "completed" or job.final_audio_asset_id is None:
        raise InvalidScript("This render has not finished yet.")

    asset = await session.get(AudioAsset, job.final_audio_asset_id)
    if asset is None:
        raise NotFound("The rendered audio is no longer available.")

    project = await container.projects.get(session, job.project_id)
    data = await container.storage.get(asset.storage_key)
    filename = safe_filename(project.title, asset.format)
    return Response(
        content=data,
        media_type=asset.mime_type,
        headers={"Content-Disposition": content_disposition(filename)},
    )


@router.get("/projects/{project_id}/transcript.pdf")
async def download_transcript(
    project_id: uuid.UUID,
    session: AsyncSession = Depends(get_session),
    container: Container = Depends(get_container),
) -> Response:
    """The script as a PDF, with speaker labels and per-segment durations."""
    from app.infrastructure.documents.transcript_pdf import (
        TranscriptLine,
        build_transcript_pdf,
    )

    project = await container.projects.get(session, project_id)
    rows = await container.projects.transcript_lines(session, project)
    if not rows:
        raise InvalidScript("Parse the script before downloading a transcript.")

    total = sum(duration or 0 for _, _, _, duration in rows) or None
    pdf = build_transcript_pdf(
        title=project.title,
        mode=project.mode,
        lines=[
            TranscriptLine(index=i, speaker=speaker, text=text, duration_ms=duration)
            for i, speaker, text, duration in rows
        ],
        total_duration_ms=total,
        word_count=project.word_count,
    )
    filename = safe_filename(project.title, "pdf")
    return Response(
        content=pdf,
        media_type="application/pdf",
        headers={"Content-Disposition": content_disposition(filename)},
    )


@router.get("/audio-files/{path:path}")
async def serve_audio_file(
    path: str, container: Container = Depends(get_container)
) -> Response:
    """Development-only passthrough.

    Production serves audio from object storage via signed URLs rather than
    proxying it through the API (SPEC section 17).
    """
    data = await container.storage.get(path)
    suffix = path.rsplit(".", 1)[-1].lower()
    from app.infrastructure.audio.ffmpeg import MIME_BY_FORMAT

    return Response(
        content=data,
        media_type=MIME_BY_FORMAT.get(suffix, "application/octet-stream"),
        headers={"Accept-Ranges": "bytes", "Cache-Control": "public, max-age=3600"},
    )
