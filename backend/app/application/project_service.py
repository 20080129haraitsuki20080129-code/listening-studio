from __future__ import annotations

import uuid

from sqlalchemy import select, update
from sqlalchemy.ext.asyncio import AsyncSession

from app.config import get_settings
from app.domain.errors import InvalidScript, NotFound
from app.domain.parsing import ParsedSegment, parse_script, speaker_labels
from app.domain.styled_parsing import MAX_STYLE_SPEAKERS
from app.infrastructure.db.models import Project, Segment, Speaker
from app.schemas.project import ProjectCreate, ProjectUpdate

# Speakers can be marked either with [A] / [B] letters or with bold / italic /
# underline. Three independent marks give exactly eight combinations, which is
# what sets the ceiling.
MAX_SPEAKERS = MAX_STYLE_SPEAKERS


def speaker_label(index: int) -> str:
    return chr(ord("A") + index)


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

        wanted = speaker_labels(parsed)
        for index, label in enumerate(wanted):
            if label not in existing_speakers:
                speaker = Speaker(
                    project_id=project.id,
                    label=label,
                    display_name=f"Voice {index + 1}",
                )
                session.add(speaker)
                existing_speakers[label] = speaker

        # Drop speakers the script no longer mentions. Without this a styled
        # dialogue accumulates dead voice slots -- restyle every line and the
        # old style still shows up asking to be given a voice.
        for label, speaker in list(existing_speakers.items()):
            if label not in wanted:
                await session.delete(speaker)
                del existing_speakers[label]
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

    async def set_speaker_roster(
        self, session: AsyncSession, project: Project, count: int
    ) -> list[Speaker]:
        """Make the project have exactly `count` speakers, labelled A, B, C...

        Existing speakers are matched by label so their voice and speed survive
        a change in count. Segments belonging to a removed speaker move to the
        first remaining one rather than losing their voice entirely.
        """
        if not 1 <= count <= MAX_SPEAKERS:
            raise InvalidScript(
                f"A dialogue supports between 1 and {MAX_SPEAKERS} speakers."
            )

        existing = {
            speaker.label: speaker
            for speaker in (
                await session.execute(
                    select(Speaker)
                    .where(Speaker.project_id == project.id)
                    .order_by(Speaker.label)
                )
            ).scalars()
        }

        wanted = [speaker_label(i) for i in range(count)]
        for index, label in enumerate(wanted):
            display_name = f"Voice {index + 1}"
            if label not in existing:
                speaker = Speaker(
                    project_id=project.id, label=label, display_name=display_name
                )
                session.add(speaker)
                existing[label] = speaker
            else:
                # Keep names consistent across speakers the parser created and
                # ones this roster added; the transcript PDF prints them.
                existing[label].display_name = display_name
        await session.flush()

        keeper = existing[wanted[0]]
        for label, speaker in list(existing.items()):
            if label in wanted:
                continue
            await session.execute(
                update(Segment)
                .where(Segment.speaker_id == speaker.id)
                .values(speaker_id=keeper.id)
            )
            await session.delete(speaker)
            del existing[label]
        await session.flush()

        return [existing[label] for label in wanted]

    async def delete_speaker(
        self, session: AsyncSession, speaker_id: uuid.UUID
    ) -> None:
        """Remove a speaker.

        API.md requires rejecting a delete that would leave segments invalid,
        so a speaker still referenced by segments cannot be removed on its own;
        change the roster size instead, which reassigns them explicitly.
        """
        speaker = await self.get_speaker(session, speaker_id)
        referenced = (
            await session.execute(
                select(Segment.id).where(Segment.speaker_id == speaker.id).limit(1)
            )
        ).scalar_one_or_none()
        if referenced is not None:
            raise InvalidScript(
                "This speaker still has segments. Change the number of speakers "
                "instead, which reassigns them."
            )
        await session.delete(speaker)
        await session.flush()

    async def transcript_lines(
        self, session: AsyncSession, project: Project
    ) -> list[tuple[int, str | None, str, int | None]]:
        """Ordered (index, speaker display name, text, duration) rows."""
        speakers = {
            speaker.id: speaker
            for speaker in (
                await session.execute(
                    select(Speaker).where(Speaker.project_id == project.id)
                )
            ).scalars()
        }
        segments = (
            await session.execute(
                select(Segment)
                .where(Segment.project_id == project.id)
                .order_by(Segment.order_index)
            )
        ).scalars()
        rows = []
        for position, segment in enumerate(segments, start=1):
            speaker = speakers.get(segment.speaker_id) if segment.speaker_id else None
            rows.append(
                (
                    position,
                    speaker.display_name if speaker else None,
                    segment.text,
                    segment.duration_ms,
                )
            )
        return rows

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
