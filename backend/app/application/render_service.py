"""Rendering (SPEC section 13).

Per segment: resolve effective voice and speed, synthesize (or hit the cache),
then assemble the project with silences and one loudness pass over the whole
track.
"""

from __future__ import annotations

import logging
import uuid
from collections.abc import Sequence
from dataclasses import dataclass
from datetime import UTC, datetime

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from app.application.tts_service import TTSService
from app.domain.errors import (
    AppError,
    InvalidScript,
    ProviderRateLimited,
    ProviderUnavailable,
    VoiceNotFound,
)
from app.domain.resolution import ResolutionInput, resolve_speed, resolve_voice_id
from app.infrastructure.audio.ffmpeg import FFmpeg
from app.infrastructure.db.models import (
    AudioAsset,
    Project,
    RenderJob,
    Segment,
    Speaker,
    Voice,
)
from app.infrastructure.storage.base import StorageBackend

log = logging.getLogger(__name__)


@dataclass(frozen=True)
class RenderedSegment:
    segment: Segment
    asset: AudioAsset
    pause_before_ms: int


class RenderService:
    def __init__(
        self,
        tts: TTSService,
        ffmpeg: FFmpeg,
        storage: StorageBackend,
        session_factory: async_sessionmaker[AsyncSession],
        *,
        failover_enabled: bool = False,
        available_providers: Sequence[str] = (),
    ) -> None:
        self._tts = tts
        self._ffmpeg = ffmpeg
        self._storage = storage
        self._session_factory = session_factory
        self._failover_enabled = failover_enabled
        self._available_providers = tuple(available_providers)

    async def _equivalent_voice(
        self, session: AsyncSession, voice: Voice
    ) -> Voice | None:
        """A stand-in on another provider with the same accent and gender.

        TASKS Phase 2 forbids silently failing over to an obviously different
        voice, so a substitute must match on both axes the user actually chose
        from. An accent or gender of "unknown" is not a match for anything --
        we cannot claim two unknowns sound alike.
        """
        if voice.accent in (None, "unknown") or voice.gender == "unknown":
            return None
        candidates = (
            await session.execute(
                select(Voice)
                .where(
                    Voice.provider != voice.provider,
                    Voice.provider.in_(self._available_providers),
                    Voice.accent == voice.accent,
                    Voice.gender == voice.gender,
                    Voice.enabled.is_(True),
                )
                .order_by(Voice.provider, Voice.name)
                .limit(1)
            )
        ).scalar_one_or_none()
        return candidates

    # ---------- resolution ----------

    async def _resolve(
        self, session: AsyncSession, project: Project, segment: Segment
    ) -> tuple[Voice, float]:
        speaker: Speaker | None = None
        if segment.speaker_id is not None:
            speaker = await session.get(Speaker, segment.speaker_id)

        source = ResolutionInput(
            segment_voice_id=segment.voice_id_override,
            segment_speed=(
                float(segment.generation_speed_override)
                if segment.generation_speed_override is not None
                else None
            ),
            speaker_voice_id=speaker.voice_id if speaker else None,
            speaker_speed=(float(speaker.generation_speed) if speaker else None),
            project_voice_id=project.default_voice_id,
            project_speed=float(project.default_generation_speed),
        )

        voice_id = resolve_voice_id(source)
        if voice_id is None:
            raise InvalidScript(
                "No voice is configured for this segment. Set a project default "
                "voice or assign one to the speaker."
            )
        voice = await session.get(Voice, voice_id)
        if voice is None:
            raise VoiceNotFound
        return voice, resolve_speed(source)

    # ---------- single segment ----------

    async def render_segment(
        self,
        session: AsyncSession,
        project: Project,
        segment: Segment,
        *,
        output_format: str = "mp3",
    ) -> AudioAsset:
        if not segment.text.strip():
            raise InvalidScript("Segment text is empty.")

        voice, speed = await self._resolve(session, project, segment)
        try:
            result = await self._tts.synthesize(
                session,
                provider=voice.provider,
                provider_voice_id=voice.provider_voice_id,
                text=segment.text,
                speed=speed,
                output_format=output_format,
                model=voice.provider_model_hint,
            )
        except (ProviderUnavailable, ProviderRateLimited):
            if not self._failover_enabled:
                raise
            substitute = await self._equivalent_voice(session, voice)
            if substitute is None:
                raise
            log.warning(
                "Failing over segment %s from %s to %s (%s/%s)",
                segment.id,
                voice.provider,
                substitute.provider,
                substitute.accent,
                substitute.gender,
            )
            result = await self._tts.synthesize(
                session,
                provider=substitute.provider,
                provider_voice_id=substitute.provider_voice_id,
                text=segment.text,
                speed=speed,
                output_format=output_format,
                model=substitute.provider_model_hint,
            )
        segment.audio_asset_id = result.audio_asset.id
        segment.duration_ms = result.audio_asset.duration_ms
        await session.flush()
        return result.audio_asset

    # ---------- whole project ----------

    async def render_project(
        self,
        session: AsyncSession,
        project: Project,
        *,
        output_format: str = "mp3",
        job: RenderJob | None = None,
    ) -> AudioAsset:
        segments = list(
            (
                await session.execute(
                    select(Segment)
                    .where(Segment.project_id == project.id)
                    .order_by(Segment.order_index)
                )
            ).scalars()
        )
        segments = [s for s in segments if s.text.strip()]
        if not segments:
            raise InvalidScript("The project has no segments to render.")

        parts: list[tuple[bytes, str]] = []
        gaps: list[int] = []
        previous_pause_after = 0

        for index, segment in enumerate(segments):
            asset = await self.render_segment(
                session, project, segment, output_format=output_format
            )
            audio = await self._storage.get(asset.storage_key)

            # The gap before a segment is whatever the previous segment asked
            # to trail plus whatever this one asks to lead, so neither setting
            # is silently dropped.
            gap = segment.pause_before_ms + previous_pause_after
            gaps.append(
                0 if index == 0 and gap == segment.pause_before_ms == 0 else gap
            )
            parts.append((audio, asset.format))
            previous_pause_after = segment.pause_after_ms

            if job is not None:
                job.progress = int((index + 1) / len(segments) * 90)
                # Commit per segment rather than holding one transaction for
                # the whole render: a long-open transaction pins a pooled
                # connection and blocks unrelated API requests. It also makes
                # progress visible to the polling client.
                await session.commit()

        # Hearing the passage more than once is how listening material is
        # normally used, so the whole sequence repeats with a gap between
        # hearings (SPEC section 4.3). Segment audio is reused rather than
        # re-synthesized -- the cache already holds it.
        repeats = max(1, int(project.repeat_count or 1))
        if repeats > 1:
            single_parts, single_gaps = list(parts), list(gaps)
            for _ in range(repeats - 1):
                for offset, part in enumerate(single_parts):
                    parts.append(part)
                    gaps.append(
                        project.pause_between_repeats_ms
                        if offset == 0
                        else single_gaps[offset]
                    )

        final_bytes = await self._ffmpeg.concat(
            parts, gaps, out_format=output_format, normalize=True
        )
        duration_ms = await self._ffmpeg.duration_ms(final_bytes, output_format)
        asset = await self._tts.store_render(
            session, final_bytes, output_format, duration_ms
        )
        if job is not None:
            job.progress = 100
        await session.flush()
        return asset

    # ---------- background job ----------

    async def run_job(self, job_id: uuid.UUID) -> None:
        """Execute a queued render in its own session.

        Runs detached from the request, so failures are recorded on the job
        row rather than surfacing as an unhandled task exception.
        """
        async with self._session_factory() as session:
            job = await session.get(RenderJob, job_id)
            if job is None or job.status == "cancelled":
                return
            project = await session.get(Project, job.project_id)
            if project is None:
                job.status = "failed"
                job.error_code = "NOT_FOUND"
                job.error_message = "The project no longer exists."
                job.finished_at = datetime.now(UTC)
                await session.commit()
                return

            job.status = "running"
            job.started_at = datetime.now(UTC)
            await session.commit()

            try:
                asset = await self.render_project(
                    session,
                    project,
                    output_format=job.output_format,
                    job=job,
                )
            except AppError as exc:
                await session.rollback()
                await _fail_job(session, job_id, exc.code, exc.message)
                return
            except Exception as exc:  # noqa: BLE001 - job must record any failure
                await session.rollback()
                await _fail_job(session, job_id, "AUDIO_PROCESSING_FAILED", str(exc))
                return

            refreshed = await session.get(RenderJob, job_id)
            if refreshed is not None and refreshed.status == "cancelled":
                await session.commit()
                return
            if refreshed is not None:
                refreshed.status = "completed"
                refreshed.progress = 100
                refreshed.final_audio_asset_id = asset.id
                refreshed.finished_at = datetime.now(UTC)
            await session.commit()


async def _fail_job(
    session: AsyncSession, job_id: uuid.UUID, code: str, message: str
) -> None:
    job = await session.get(RenderJob, job_id)
    if job is None:
        return
    job.status = "failed"
    job.error_code = code
    job.error_message = message
    job.finished_at = datetime.now(UTC)
    await session.commit()
