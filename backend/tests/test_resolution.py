from __future__ import annotations

import uuid

import pytest

from app.domain.resolution import (
    ResolutionInput,
    cache_key,
    normalize_text,
    resolve_speed,
    resolve_voice_id,
)

SEG = uuid.uuid4()
SPK = uuid.uuid4()
PRJ = uuid.uuid4()


def make(**kwargs) -> ResolutionInput:
    base = dict(
        segment_voice_id=None,
        segment_speed=None,
        speaker_voice_id=None,
        speaker_speed=None,
        project_voice_id=None,
        project_speed=1.0,
    )
    base.update(kwargs)
    return ResolutionInput(**base)


class TestResolveVoice:
    def test_segment_override_wins(self):
        got = resolve_voice_id(
            make(segment_voice_id=SEG, speaker_voice_id=SPK, project_voice_id=PRJ)
        )
        assert got == SEG

    def test_speaker_beats_project(self):
        got = resolve_voice_id(make(speaker_voice_id=SPK, project_voice_id=PRJ))
        assert got == SPK

    def test_falls_back_to_project(self):
        assert resolve_voice_id(make(project_voice_id=PRJ)) == PRJ

    def test_none_when_nothing_configured(self):
        assert resolve_voice_id(make()) is None


class TestResolveSpeed:
    def test_segment_override_wins(self):
        got = resolve_speed(
            make(segment_speed=1.3, speaker_speed=1.1, project_speed=1.0)
        )
        assert got == pytest.approx(1.3)

    def test_speaker_beats_project(self):
        assert resolve_speed(
            make(speaker_speed=1.1, project_speed=1.0)
        ) == pytest.approx(1.1)

    def test_falls_back_to_project(self):
        assert resolve_speed(make(project_speed=0.9)) == pytest.approx(0.9)

    def test_zero_override_is_honored_not_treated_as_missing(self):
        # 0.0 is falsy; resolution must check for None, not truthiness.
        assert resolve_speed(make(segment_speed=0.0, project_speed=1.0)) == 0.0


class TestCacheKey:
    def base(self, **kwargs):
        args = dict(
            provider="kokoro",
            model=None,
            provider_voice_id="bm_george",
            text="Hello there.",
            speed=1.0,
            instructions=None,
            output_format="mp3",
        )
        args.update(kwargs)
        return cache_key(**args)

    def test_is_deterministic(self):
        assert self.base() == self.base()

    @pytest.mark.parametrize(
        "field,value",
        [
            ("provider", "macos_say"),
            ("model", "tts-1"),
            ("provider_voice_id", "bf_emma"),
            ("text", "Different."),
            ("speed", 1.25),
            ("instructions", "Speak slowly."),
            ("output_format", "wav"),
        ],
    )
    def test_every_audio_affecting_input_changes_the_key(self, field, value):
        assert self.base(**{field: value}) != self.base()

    def test_whitespace_only_differences_share_a_key(self):
        assert self.base(text="Hello   there.") == self.base(text="Hello there.")
        assert self.base(text="  Hello there.  ") == self.base()

    def test_speed_compared_at_three_decimals(self):
        assert self.base(speed=1.0) == self.base(speed=1.0004)
        assert self.base(speed=1.0) != self.base(speed=1.002)


def test_normalize_text_collapses_newlines_and_tabs():
    assert normalize_text("a\n\tb  c ") == "a b c"
