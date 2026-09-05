"""Conflict-tolerant inserts.

Both the TTS cache and the audio asset table are content-addressed, so two
concurrent renders of the same sentence legitimately produce the same key. The
loser of that race must reuse the winner's row, not fail the render.

The dialect-specific `ON CONFLICT` lives here rather than in the application
layer.
"""

from __future__ import annotations

import uuid
from typing import Any

from sqlalchemy import select
from sqlalchemy.dialects.postgresql import insert as pg_insert
from sqlalchemy.ext.asyncio import AsyncSession

from .models import Base


async def insert_ignoring_conflict[Model: Base](
    session: AsyncSession,
    model: type[Model],
    values: dict[str, Any],
    *,
    conflict_on: list[str],
) -> None:
    """Insert a row, or leave the existing one alone."""
    await session.execute(
        pg_insert(model)
        .values(**values)
        .on_conflict_do_nothing(index_elements=conflict_on)
    )


async def insert_or_get[Model: Base](
    session: AsyncSession,
    model: type[Model],
    values: dict[str, Any],
    *,
    conflict_on: str,
) -> Model:
    """Insert a row and return it, or return the row that already holds the key.

    If a concurrent transaction is mid-insert, `ON CONFLICT DO NOTHING` waits
    for it to finish, then the follow-up select sees the committed row.
    """
    stmt = (
        pg_insert(model)
        .values(**values)
        .on_conflict_do_nothing(index_elements=[conflict_on])
        .returning(model.id)  # type: ignore[attr-defined]
    )
    inserted: uuid.UUID | None = (await session.execute(stmt)).scalar_one_or_none()
    if inserted is not None:
        row = await session.get(model, inserted)
        if row is not None:
            return row

    column = getattr(model, conflict_on)
    existing = (
        await session.execute(select(model).where(column == values[conflict_on]))
    ).scalar_one()
    return existing
