from __future__ import annotations

import uuid

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.config import get_settings
from app.domain.errors import InvalidScript, NotFound
from app.domain.parsing import ParsedSegment, parse_script, speaker_labels
from app.infrastructure.db.models import Project, Segment, Speaker
from app.schemas.project import ProjectCreate, ProjectUpdate

# Fields whose change invalidates a segment's rendered audio.
_TTS_AFFECTING = frozenset(
    {"text", "voice_id_override", "generation_speed_override", "speaker_id"}
)


class ProjectService:
    async def create(self, session: AsyncSession, payload: ProjectCreate) -> Project:
        self._check_length(payload.source_text)
        project = Project(
            title=payload.title,
            mode=payload.mode,
            source_text=payload.source_text,
            transcript_visible_default=payload.transcript_visible_default,
        )
        session.add(project)
        await session.flush()
        return project

    async def get(self, session: AsyncSession, project_id: uuid.UUID) -> Project:
        project = await session.get(Project, project_id)
        if project is None or project.deleted_at is not None:
            raise NotFound("The project does not exist.")
        return project

    async def list_all(self, session: AsyncSession) -> list[Project]:
        stmt = (
            select(Project)
            .where(Project.deleted_at.is_(None))
            .order_by(Project.updated_at.desc())
        )
        return list((await session.execute(stmt)).scalars())

    async def update(
        self, session: AsyncSession, project_id: uuid.UUID, payload: ProjectUpdate
    ) -> Project:
        project = await self.get(session, project_id)
        data = payload.model_dump(exclude_unset=True)
        if "source_text" in data:
            self._check_length(data["source_text"])
        for field, value in data.items():
            setattr(project, field, value)
        await session.flush()
        return project

    async def soft_delete(self, session: AsyncSession, project_id: uuid.UUID) -> None:
        from datetime import UTC, datetime

        project = await self.get(session, project_id)
        project.deleted_at = datetime.now(UTC)
        await session.flush()

    # ---------- parsing ----------

    def parse(self, source_text: str, mode: str) -> list[ParsedSegment]:
        self._check_length(source_text)
        parsed = parse_script(source_text, mode)
        if not parsed:
            raise InvalidScript("The script produced no segments.")
        settings = get_settings()
        for segment in parsed:
            if len(segment.text) > settings.max_segment_chars:
                raise InvalidScript(
                    f"A segment exceeds the {settings.max_segment_chars} character limit."
                )
        return parsed

    async def apply_parse(
        self,
        session: AsyncSession,
        project: Project,
        parsed: list[ParsedSegment],
    ) -> Project:
        """Replace the project's segments with a parse result.

        Speakers are matched by label so their voice settings survive a
        re-parse of edited text.
        """
        existing_speakers = {
            speaker.label: speaker
            for speaker in (
                await session.execute(
                    select(Speaker).where(Speaker.project_id == project.id)
                )
            ).scalars()
        }

        for label in speaker_labels(parsed):
            if label not in existing_speakers:
                speaker = Speaker(
                    project_id=project.id,
                    label=label,
                    display_name=f"Speaker {label}",
                )
                session.add(speaker)
                existing_speakers[label] = speaker
        await session.flush()

        old = (
            await session.execute(
                select(Segment).where(Segment.project_id == project.id)
            )
        ).scalars()
        for segment in old:
            await session.delete(segment)
        await session.flush()

        for item in parsed:
            speaker = (
                existing_speakers.get(item.speaker_label)
                if item.speaker_label
                else None
            )
            session.add(
                Segment(
                    project_id=project.id,
                    order_index=item.order_index,
                    speaker_id=speaker.id if speaker else None,
                    text=item.text,
                    pause_after_ms=(
                        project.paragraph_pause_ms
                        if item.starts_paragraph
                        else project.sentence_pause_ms
                    ),
                )
            )
        await session.flush()
        await session.refresh(project)
        return project

    # ---------- segments ----------

    async def get_segment(
        self, session: AsyncSession, segment_id: uuid.UUID
    ) -> Segment:
        segment = await session.get(Segment, segment_id)
        if segment is None:
            raise NotFound("The segment does not exist.")
        return segment

    async def update_segment(
        self, session: AsyncSession, segment_id: uuid.UUID, data: dict
    ) -> Segment:
        segment = await self.get_segment(session, segment_id)
        for field, value in data.items():
            setattr(segment, field, value)
        # Changing anything that feeds the TTS request makes the stored audio
        # stale, so drop it rather than serve audio that no longer matches.
        if _TTS_AFFECTING & data.keys():
            segment.audio_asset_id = None
            segment.duration_ms = None
        await session.flush()
        return segment

    # ---------- speakers ----------

    async def get_speaker(
        self, session: AsyncSession, speaker_id: uuid.UUID
    ) -> Speaker:
        speaker = await session.get(Speaker, speaker_id)
        if speaker is None:
            raise NotFound("The speaker does not exist.")
        return speaker

    def _check_length(self, source_text: str) -> None:
        limit = get_settings().max_script_chars
        if len(source_text) > limit:
            raise InvalidScript(f"The script exceeds the {limit} character limit.")
