"""Drop the macOS say provider

Its voices are noticeably lower quality than Kokoro's, so the app now offers
Kokoro only. References are cleared before the rows go, and the accent list
narrows to american and british as a consequence.

Revision ID: b1c4e77a90d2
Revises: 5a0c7910ada6
Create Date: 2026-09-05
"""

from __future__ import annotations

from collections.abc import Sequence

from alembic import op

revision: str = "b1c4e77a90d2"
down_revision: str | None = "5a0c7910ada6"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

_PROVIDERS_AFTER = "('openai', 'azure', 'elevenlabs', 'kokoro')"
_PROVIDERS_BEFORE = "('openai', 'azure', 'elevenlabs', 'kokoro', 'macos_say')"


def upgrade() -> None:
    # Clear every reference first; the foreign keys would otherwise block the
    # delete, and a project pointing at a removed voice cannot render.
    op.execute(
        "UPDATE projects SET default_voice_id = NULL WHERE default_voice_id IN "
        "(SELECT id FROM voices WHERE provider = 'macos_say')"
    )
    op.execute(
        "UPDATE speakers SET voice_id = NULL WHERE voice_id IN "
        "(SELECT id FROM voices WHERE provider = 'macos_say')"
    )
    op.execute(
        "UPDATE segments SET voice_id_override = NULL WHERE voice_id_override IN "
        "(SELECT id FROM voices WHERE provider = 'macos_say')"
    )
    # Cached audio for those voices can never be reused again.
    op.execute("DELETE FROM tts_cache WHERE provider = 'macos_say'")
    op.execute("DELETE FROM voices WHERE provider = 'macos_say'")

    op.drop_constraint("ck_voices_provider", "voices", type_="check")
    op.create_check_constraint(
        "ck_voices_provider", "voices", f"provider IN {_PROVIDERS_AFTER}"
    )


def downgrade() -> None:
    op.drop_constraint("ck_voices_provider", "voices", type_="check")
    op.create_check_constraint(
        "ck_voices_provider", "voices", f"provider IN {_PROVIDERS_BEFORE}"
    )
