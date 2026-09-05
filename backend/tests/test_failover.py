"""Failover must be opt-in and must not swap in an audibly different voice.

TASKS Phase 2: "Automatic failover must not silently switch to an obviously
different voice. If failover is implemented, it should be opt-in or voice-group
aware." This is both.
"""

from __future__ import annotations

import pytest
from sqlalchemy import select

from app.application.render_service import RenderService
from app.domain.errors import ProviderUnavailable
from app.infrastructure.db.models import Project, Segment, Voice


async def _voice(session, **overrides) -> Voice:
    defaults = dict(
        provider="kokoro",
        provider_voice_id="bm_george",
        name="George",
        language="en",
        locale="en-GB",
        accent="british",
        gender="male",
        age_group="unknown",
        style_tags=[],
        enabled=True,
    )
    defaults.update(overrides)
    voice = Voice(**defaults)
    session.add(voice)
    await session.flush()
    return voice


def _service(**kwargs) -> RenderService:
    return RenderService(None, None, None, None, **kwargs)  # type: ignore[arg-type]


class TestEquivalentVoice:
    async def test_matches_same_accent_and_gender_on_another_provider(self, session):
        original = await _voice(session)
        await _voice(
            session,
            provider="azure",
            provider_voice_id="en-GB-RyanNeural",
            name="Ryan",
            accent="british",
            gender="male",
        )
        service = _service(available_providers=("kokoro", "azure"))
        found = await service._equivalent_voice(session, original)
        assert found is not None
        assert found.provider == "azure"

    async def test_will_not_substitute_a_different_accent(self, session):
        original = await _voice(session)
        await _voice(
            session,
            provider="azure",
            provider_voice_id="en-US-GuyNeural",
            name="Guy",
            accent="american",
            gender="male",
        )
        service = _service(available_providers=("kokoro", "azure"))
        assert await service._equivalent_voice(session, original) is None

    async def test_will_not_substitute_a_different_gender(self, session):
        original = await _voice(session)
        await _voice(
            session,
            provider="azure",
            provider_voice_id="en-GB-SoniaNeural",
            name="Sonia",
            accent="british",
            gender="female",
        )
        service = _service(available_providers=("kokoro", "azure"))
        assert await service._equivalent_voice(session, original) is None

    async def test_unknown_metadata_is_never_treated_as_a_match(self, session):
        original = await _voice(session, accent="unknown", gender="unknown")
        await _voice(
            session,
            provider="azure",
            provider_voice_id="other",
            name="Other",
            accent="unknown",
            gender="unknown",
        )
        service = _service(available_providers=("kokoro", "azure"))
        # Two unknowns say nothing about whether the voices sound alike.
        assert await service._equivalent_voice(session, original) is None

    async def test_ignores_providers_that_are_not_registered(self, session):
        original = await _voice(session)
        await _voice(
            session,
            provider="azure",
            provider_voice_id="en-GB-RyanNeural",
            name="Ryan",
            accent="british",
            gender="male",
        )
        service = _service(available_providers=("kokoro",))
        assert await service._equivalent_voice(session, original) is None

    async def test_ignores_disabled_voices(self, session):
        original = await _voice(session)
        await _voice(
            session,
            provider="azure",
            provider_voice_id="en-GB-RyanNeural",
            name="Ryan",
            accent="british",
            gender="male",
            enabled=False,
        )
        service = _service(available_providers=("kokoro", "azure"))
        assert await service._equivalent_voice(session, original) is None


class TestFailoverIsOptIn:
    async def test_disabled_by_default(self):
        service = _service()
        assert service._failover_enabled is False

    async def test_provider_error_propagates_when_failover_is_off(
        self, session, monkeypatch
    ):
        """With failover off, an unavailable provider must surface, not silently
        render in some other voice."""
        voice = await _voice(session)
        project = Project(
            title="t", mode="monologue", default_voice_id=voice.id,
            default_generation_speed=1.0,
        )
        session.add(project)
        await session.flush()
        segment = Segment(project_id=project.id, order_index=0, text="Hello.")
        session.add(segment)
        await session.flush()

        class Boom:
            async def synthesize(self, *args, **kwargs):
                raise ProviderUnavailable

        service = _service()
        service._tts = Boom()  # type: ignore[assignment]

        with pytest.raises(ProviderUnavailable):
            await service.render_segment(session, project, segment)

        refreshed = (
            await session.execute(select(Segment).where(Segment.id == segment.id))
        ).scalar_one()
        assert refreshed.audio_asset_id is None
