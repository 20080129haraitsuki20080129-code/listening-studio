"""SQLAlchemy models mirroring docs/SCHEMA.sql.

Differences from the handed-over schema, all required to implement the SPEC as
written (see docs/PLAN.md section 3):

* `provider` accepts the local providers, otherwise no voice can be stored.
* `projects` gains default voice/speed/pause columns. SPEC section 13 resolves
  voice and speed as segment -> speaker -> project, and the third level had
  nowhere to live.
* `render_jobs` gains `idempotency_key`, which API.md requires but the schema
  had no column for.
"""

from __future__ import annotations

import uuid
from datetime import datetime

from sqlalchemy import (
    BigInteger,
    Boolean,
    CheckConstraint,
    DateTime,
    ForeignKey,
    Index,
    Integer,
    Numeric,
    String,
    Text,
    UniqueConstraint,
    func,
    text,
)
from sqlalchemy.dialects.postgresql import JSONB, UUID
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column, relationship

from app.domain.styled_parsing import (
    STYLE_NAMES,
    looks_styled,
    mask_for_label,
)

PROVIDERS = ("openai", "azure", "elevenlabs", "kokoro")
MODES = ("monologue", "dialogue", "listening_test", "shadowing")
GENDERS = ("female", "male", "neutral", "unknown")
AGE_GROUPS = ("young", "adult", "mature", "unknown")
FORMATS = ("mp3", "wav", "opus", "aac", "flac", "pcm")
RENDER_STATUSES = ("queued", "running", "completed", "failed", "cancelled")


def _in(column: str, values: tuple[str, ...]) -> str:
    joined = ", ".join(f"'{v}'" for v in values)
    return f"{column} IN ({joined})"


class Base(DeclarativeBase):
    pass


def _pk() -> Mapped[uuid.UUID]:
    return mapped_column(
        UUID(as_uuid=True), primary_key=True, server_default=func.gen_random_uuid()
    )


def _created() -> Mapped[datetime]:
    return mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now()
    )


def _updated() -> Mapped[datetime]:
    return mapped_column(
        DateTime(timezone=True),
        nullable=False,
        server_default=func.now(),
        onupdate=func.now(),
    )


class Project(Base):
    __tablename__ = "projects"
    __table_args__ = (CheckConstraint(_in("mode", MODES), name="ck_projects_mode"),)

    id: Mapped[uuid.UUID] = _pk()
    title: Mapped[str] = mapped_column(Text, nullable=False)
    mode: Mapped[str] = mapped_column(Text, nullable=False)
    source_text: Mapped[str] = mapped_column(Text, nullable=False, server_default="")
    transcript_visible_default: Mapped[bool] = mapped_column(
        Boolean, nullable=False, server_default="true"
    )

    default_voice_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True), ForeignKey("voices.id"), nullable=True
    )
    default_generation_speed: Mapped[float] = mapped_column(
        Numeric(6, 3), nullable=False, server_default="1.0"
    )
    sentence_pause_ms: Mapped[int] = mapped_column(
        Integer, nullable=False, server_default="250"
    )
    paragraph_pause_ms: Mapped[int] = mapped_column(
        Integer, nullable=False, server_default="600"
    )

    created_at: Mapped[datetime] = _created()
    updated_at: Mapped[datetime] = _updated()
    deleted_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True
    )

    @property
    def styled_dialogue(self) -> bool:
        """Whether speakers come from text styling rather than [A] markers."""
        return looks_styled(self.source_text or "")

    speakers: Mapped[list[Speaker]] = relationship(
        back_populates="project",
        cascade="all, delete-orphan",
        lazy="selectin",
        # Without an explicit order the database decides, so the UI's "Voice 1"
        # could point at [B] and shuffle between reloads. Label order is the
        # order the speakers appear in the script.
        order_by="Speaker.label",
    )
    segments: Mapped[list[Segment]] = relationship(
        back_populates="project",
        cascade="all, delete-orphan",
        lazy="selectin",
        order_by="Segment.order_index",
    )


class Voice(Base):
    __tablename__ = "voices"
    __table_args__ = (
        UniqueConstraint("provider", "provider_voice_id", name="uq_voices_provider_id"),
        CheckConstraint(_in("provider", PROVIDERS), name="ck_voices_provider"),
        CheckConstraint(_in("gender", GENDERS), name="ck_voices_gender"),
        CheckConstraint(_in("age_group", AGE_GROUPS), name="ck_voices_age_group"),
        Index("idx_voices_provider", "provider"),
        Index("idx_voices_language", "language"),
        Index("idx_voices_accent", "accent"),
        Index("idx_voices_gender", "gender"),
        Index("idx_voices_enabled", "enabled"),
    )

    id: Mapped[uuid.UUID] = _pk()
    provider: Mapped[str] = mapped_column(Text, nullable=False)
    provider_voice_id: Mapped[str] = mapped_column(Text, nullable=False)
    provider_model_hint: Mapped[str | None] = mapped_column(Text, nullable=True)

    name: Mapped[str] = mapped_column(Text, nullable=False)
    language: Mapped[str] = mapped_column(Text, nullable=False, server_default="en")
    locale: Mapped[str | None] = mapped_column(Text, nullable=True)
    accent: Mapped[str | None] = mapped_column(Text, nullable=True)
    gender: Mapped[str] = mapped_column(Text, nullable=False, server_default="unknown")
    age_group: Mapped[str] = mapped_column(
        Text, nullable=False, server_default="unknown"
    )

    style_tags: Mapped[list] = mapped_column(JSONB, nullable=False, server_default="[]")
    preview_url: Mapped[str | None] = mapped_column(Text, nullable=True)
    enabled: Mapped[bool] = mapped_column(
        Boolean, nullable=False, server_default="true"
    )
    voice_metadata: Mapped[dict] = mapped_column(
        "metadata", JSONB, nullable=False, server_default="{}"
    )

    created_at: Mapped[datetime] = _created()
    updated_at: Mapped[datetime] = _updated()


class Speaker(Base):
    __tablename__ = "speakers"
    __table_args__ = (
        UniqueConstraint("project_id", "label", name="uq_speakers_project_label"),
        CheckConstraint(
            "default_pause_before_ms >= 0", name="ck_speakers_pause_before"
        ),
        CheckConstraint("default_pause_after_ms >= 0", name="ck_speakers_pause_after"),
    )

    id: Mapped[uuid.UUID] = _pk()
    project_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("projects.id", ondelete="CASCADE"),
        nullable=False,
    )
    label: Mapped[str] = mapped_column(Text, nullable=False)
    display_name: Mapped[str] = mapped_column(Text, nullable=False)
    voice_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True), ForeignKey("voices.id"), nullable=True
    )
    generation_speed: Mapped[float] = mapped_column(
        Numeric(6, 3), nullable=False, server_default="1.0"
    )
    default_pause_before_ms: Mapped[int] = mapped_column(
        Integer, nullable=False, server_default="0"
    )
    default_pause_after_ms: Mapped[int] = mapped_column(
        Integer, nullable=False, server_default="250"
    )
    created_at: Mapped[datetime] = _created()
    updated_at: Mapped[datetime] = _updated()

    @property
    def style_key(self) -> str | None:
        """The style combination this slot corresponds to, e.g. "bold_italic".

        Meaningful only for a styled dialogue; the UI decides whether to show
        it, since the same labels are used for [A] / [B] markers.
        """
        mask = mask_for_label(self.label)
        return STYLE_NAMES.get(mask) if mask is not None else None

    project: Mapped[Project] = relationship(back_populates="speakers")


class AudioAsset(Base):
    __tablename__ = "audio_assets"
    __table_args__ = (
        CheckConstraint(_in("format", FORMATS), name="ck_audio_assets_format"),
        CheckConstraint("duration_ms >= 0", name="ck_audio_assets_duration"),
        CheckConstraint("size_bytes >= 0", name="ck_audio_assets_size"),
        Index("idx_audio_assets_sha256", "sha256"),
    )

    id: Mapped[uuid.UUID] = _pk()
    storage_key: Mapped[str] = mapped_column(Text, nullable=False, unique=True)
    mime_type: Mapped[str] = mapped_column(Text, nullable=False)
    format: Mapped[str] = mapped_column(Text, nullable=False)
    duration_ms: Mapped[int] = mapped_column(Integer, nullable=False)
    size_bytes: Mapped[int] = mapped_column(BigInteger, nullable=False)
    sha256: Mapped[str] = mapped_column(Text, nullable=False)
    created_at: Mapped[datetime] = _created()


class Segment(Base):
    __tablename__ = "segments"
    __table_args__ = (
        UniqueConstraint("project_id", "order_index", name="uq_segments_project_order"),
        CheckConstraint("order_index >= 0", name="ck_segments_order_index"),
        CheckConstraint("pause_before_ms >= 0", name="ck_segments_pause_before"),
        CheckConstraint("pause_after_ms >= 0", name="ck_segments_pause_after"),
        Index("idx_segments_project_order", "project_id", "order_index"),
        Index("idx_segments_speaker", "speaker_id"),
    )

    id: Mapped[uuid.UUID] = _pk()
    project_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("projects.id", ondelete="CASCADE"),
        nullable=False,
    )
    order_index: Mapped[int] = mapped_column(Integer, nullable=False)
    speaker_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("speakers.id", ondelete="SET NULL"),
        nullable=True,
    )
    text: Mapped[str] = mapped_column(Text, nullable=False)

    voice_id_override: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True), ForeignKey("voices.id"), nullable=True
    )
    generation_speed_override: Mapped[float | None] = mapped_column(
        Numeric(6, 3), nullable=True
    )
    pause_before_ms: Mapped[int] = mapped_column(
        Integer, nullable=False, server_default="0"
    )
    pause_after_ms: Mapped[int] = mapped_column(
        Integer, nullable=False, server_default="250"
    )
    audio_asset_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("audio_assets.id", ondelete="SET NULL"),
        nullable=True,
    )
    duration_ms: Mapped[int | None] = mapped_column(Integer, nullable=True)
    created_at: Mapped[datetime] = _created()
    updated_at: Mapped[datetime] = _updated()

    project: Mapped[Project] = relationship(back_populates="segments")


class RenderJob(Base):
    __tablename__ = "render_jobs"
    __table_args__ = (
        CheckConstraint(_in("status", RENDER_STATUSES), name="ck_render_jobs_status"),
        CheckConstraint(
            "progress >= 0 AND progress <= 100", name="ck_render_jobs_progress"
        ),
        Index("idx_render_jobs_project", "project_id"),
        Index("idx_render_jobs_status", "status"),
        Index(
            "idx_render_jobs_idem",
            "project_id",
            "idempotency_key",
            unique=True,
            postgresql_where=text("idempotency_key IS NOT NULL"),
        ),
    )

    id: Mapped[uuid.UUID] = _pk()
    project_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("projects.id", ondelete="CASCADE"),
        nullable=False,
    )
    status: Mapped[str] = mapped_column(Text, nullable=False, server_default="queued")
    progress: Mapped[int] = mapped_column(Integer, nullable=False, server_default="0")
    output_format: Mapped[str] = mapped_column(
        Text, nullable=False, server_default="mp3"
    )
    idempotency_key: Mapped[str | None] = mapped_column(Text, nullable=True)
    final_audio_asset_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("audio_assets.id", ondelete="SET NULL"),
        nullable=True,
    )
    error_code: Mapped[str | None] = mapped_column(Text, nullable=True)
    error_message: Mapped[str | None] = mapped_column(Text, nullable=True)
    created_at: Mapped[datetime] = _created()
    started_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True
    )
    finished_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True
    )


class TTSCache(Base):
    """Content-addressed cache of provider synthesis results (SPEC section 14)."""

    __tablename__ = "tts_cache"

    cache_key: Mapped[str] = mapped_column(String, primary_key=True)
    provider: Mapped[str] = mapped_column(Text, nullable=False)
    model: Mapped[str | None] = mapped_column(Text, nullable=True)
    provider_voice_id: Mapped[str] = mapped_column(Text, nullable=False)
    normalized_text_hash: Mapped[str] = mapped_column(Text, nullable=False)
    instructions_hash: Mapped[str | None] = mapped_column(Text, nullable=True)
    speed: Mapped[float] = mapped_column(Numeric(6, 3), nullable=False)
    output_format: Mapped[str] = mapped_column(Text, nullable=False)
    audio_asset_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("audio_assets.id", ondelete="CASCADE"),
        nullable=False,
    )
    created_at: Mapped[datetime] = _created()
    last_used_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now()
    )
