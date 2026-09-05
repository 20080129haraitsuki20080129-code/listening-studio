"""Repeat playback, word counting, and the WPM-labelled speed levels."""

from __future__ import annotations

from itertools import pairwise

import pytest

from app.domain.speed_levels import (
    DEFAULT_LEVEL,
    SPEED_LEVELS,
    level_for_speed,
    speed_for_level,
)
from app.domain.word_count import count_words


class TestWordCount:
    @pytest.mark.parametrize(
        "text,expected",
        [
            ("One two three.", 3),
            ("Don't stop believing.", 3),
            ("A well-known rule.", 3),
            ("The U.S. economy grew.", 4),
            ("It rose by 3.30 percent.", 5),
            ("", 0),
            ("   ", 0),
            ("...", 0),
            ("Hello,   world!", 2),
        ],
    )
    def test_counts(self, text, expected):
        assert count_words(text) == expected

    def test_contractions_and_hyphens_count_once(self):
        # "don't" and "well-known" are single words, not two each.
        assert count_words("don't") == 1
        assert count_words("well-known") == 1


class TestSpeedLevels:
    def test_there_are_seven(self):
        assert len(SPEED_LEVELS) == 7
        assert [level.level for level in SPEED_LEVELS] == [1, 2, 3, 4, 5, 6, 7]

    def test_speed_and_pace_both_increase(self):
        speeds = [level.speed for level in SPEED_LEVELS]
        assert speeds == sorted(speeds)
        typical = [level.wpm_typical for level in SPEED_LEVELS]
        assert typical == sorted(typical)
        assert len(set(typical)) == len(typical)

    def test_each_level_reports_the_spread_across_voices(self):
        # Voices differ by around 20 wpm at the same multiplier, which is more
        # than the gap between neighbouring levels, so a level advertises a
        # typical pace and the observed spread rather than a tidy band.
        for level in SPEED_LEVELS:
            assert level.wpm_min < level.wpm_typical < level.wpm_max

    def test_the_anchors_are_where_the_scale_is_calibrated(self):
        by_reference = {
            level.reference: level for level in SPEED_LEVELS if level.reference
        }
        assert set(by_reference) == {"exam", "news", "argument"}
        # The centre is exam pace, the top is a heated argument.
        assert by_reference["exam"].level == DEFAULT_LEVEL == 4
        assert by_reference["news"].level == 6
        assert by_reference["argument"].level == max(
            level.level for level in SPEED_LEVELS
        )
        assert by_reference["exam"].wpm_typical == pytest.approx(150, abs=6)
        assert 160 <= by_reference["news"].wpm_typical <= 185
        assert by_reference["argument"].wpm_typical >= 200

    def test_only_the_two_end_levels_sit_outside_the_smooth_stretch(self):
        # Kokoro's pace steps up sharply between 0.80/0.84 and again between
        # 1.33/1.34. The middle levels sit inside that stretch; the two ends
        # sit outside it deliberately, because neither a slow practice pace
        # nor argument pace is reachable within it.
        middle = [level for level in SPEED_LEVELS if 2 <= level.level <= 6]
        assert all(0.84 <= level.speed <= 1.33 for level in middle)
        assert speed_for_level(1) < 0.84
        assert speed_for_level(7) > 1.33

    def test_the_jump_to_the_top_level_is_the_largest(self):
        steps = [
            upper.wpm_typical - lower.wpm_typical
            for lower, upper in pairwise(SPEED_LEVELS)
        ]
        # No multiplier produces the ~195 wpm between level 6 and 7.
        assert steps[-1] == max(steps)

    def test_default_is_the_middle_level_and_the_exam_anchor(self):
        levels = [level.level for level in SPEED_LEVELS]
        assert DEFAULT_LEVEL == levels[len(levels) // 2] == 4
        default = next(entry for entry in SPEED_LEVELS if entry.level == DEFAULT_LEVEL)
        assert default.reference == "exam"

    @pytest.mark.parametrize(
        "speed,expected",
        [(0.76, 1), (0.70, 1), (0.90, 3), (1.08, 4), (1.30, 6), (1.34, 7), (2.0, 7)],
    )
    def test_stored_speed_maps_to_the_nearest_level(self, speed, expected):
        # Projects store a multiplier, including values saved under an older
        # scale, so every one must land on a level.
        assert level_for_speed(speed).level == expected

    def test_a_multiplier_between_two_levels_resolves_to_the_slower_one(self):
        # 1.00 is equidistant from level 3 (0.92) and level 4 (1.08). Erring
        # towards the easier pace is the kinder default for a listener.
        assert level_for_speed(1.00).level == 3

    def test_unknown_level_is_rejected(self):
        with pytest.raises(ValueError):
            speed_for_level(9)


class TestSpeedLevelsApi:
    async def test_endpoint_lists_all_seven(self, client):
        body = (await client.get("/speed-levels")).json()
        assert len(body["items"]) == 7
        assert body["default_level"] == 4
        first = body["items"][0]
        assert first["wpm_min"] < first["wpm_max"]


class TestWordCountApi:
    async def test_project_and_segment_word_counts(self, client):
        pid = (
            await client.post(
                "/projects",
                json={
                    "title": "counting",
                    "mode": "monologue",
                    "source_text": "One two three. Four five.",
                },
            )
        ).json()["id"]
        await client.post(f"/projects/{pid}/parse", json={})

        project = (await client.get(f"/projects/{pid}")).json()
        assert [s["word_count"] for s in project["segments"]] == [3, 2]
        assert project["word_count"] == 5

    async def test_word_count_appears_on_the_transcript(self, client):
        import io

        from pypdf import PdfReader

        pid = (
            await client.post(
                "/projects",
                json={
                    "title": "counting",
                    "mode": "monologue",
                    "source_text": "One two three. Four five.",
                },
            )
        ).json()["id"]
        await client.post(f"/projects/{pid}/parse", json={})

        response = await client.get(f"/projects/{pid}/transcript.pdf")
        text = "\n".join(
            page.extract_text()
            for page in PdfReader(io.BytesIO(response.content)).pages
        )
        assert "5 words" in text


class TestRepeat:
    async def _rendered(self, client, repeat_count: int, gap_ms: int) -> dict:
        import asyncio

        voices = (await client.post("/voices/sync")) and (
            await client.get("/voices")
        ).json()["items"]
        pid = (
            await client.post(
                "/projects",
                json={
                    "title": "repeat",
                    "mode": "monologue",
                    "source_text": "One sentence only.",
                },
            )
        ).json()["id"]
        await client.patch(
            f"/projects/{pid}",
            json={
                "default_voice_id": voices[0]["id"],
                "repeat_count": repeat_count,
                "pause_between_repeats_ms": gap_ms,
            },
        )
        await client.post(f"/projects/{pid}/parse", json={})

        job = (await client.post(f"/projects/{pid}/renders", json={})).json()
        for _ in range(200):
            job = (await client.get(f"/renders/{job['id']}")).json()
            if job["status"] in ("completed", "failed"):
                break
            await asyncio.sleep(0.1)
        assert job["status"] == "completed", job.get("error")
        return job

    async def test_defaults_to_a_single_pass(self, client):
        project = (
            await client.post("/projects", json={"title": "d", "mode": "monologue"})
        ).json()
        assert project["repeat_count"] == 1
        assert project["pause_between_repeats_ms"] == 3000

    async def test_repeating_lengthens_the_render_by_roughly_the_passage(self, client):
        once = await self._rendered(client, 1, 1000)
        twice = await self._rendered(client, 2, 1000)

        # Two passes plus one gap, so longer than double the gap alone and
        # close to twice the single-pass duration.
        assert twice["duration_ms"] > once["duration_ms"] + 1000
        assert twice["duration_ms"] == pytest.approx(
            once["duration_ms"] * 2 + 1000, rel=0.15
        )

    async def test_the_gap_between_repeats_is_honoured(self, client):
        short = await self._rendered(client, 2, 500)
        long = await self._rendered(client, 2, 4000)
        assert long["duration_ms"] - short["duration_ms"] == pytest.approx(
            3500, abs=400
        )

    async def test_repeat_count_is_bounded(self, client):
        pid = (
            await client.post("/projects", json={"title": "b", "mode": "monologue"})
        ).json()["id"]
        assert (
            await client.patch(f"/projects/{pid}", json={"repeat_count": 0})
        ).status_code == 422
        assert (
            await client.patch(f"/projects/{pid}", json={"repeat_count": 99})
        ).status_code == 422


class TestActualWpm:
    """The advertised band is an estimate; the rendered result is the fact."""

    async def _rendered_project(self, client) -> dict:
        import asyncio

        await client.post("/voices/sync")
        voices = (await client.get("/voices")).json()["items"]
        pid = (
            await client.post(
                "/projects",
                json={
                    "title": "pace",
                    "mode": "monologue",
                    "source_text": "One two three four five. Six seven eight nine ten.",
                },
            )
        ).json()["id"]
        await client.patch(
            f"/projects/{pid}", json={"default_voice_id": voices[0]["id"]}
        )
        await client.post(f"/projects/{pid}/parse", json={})

        job = (await client.post(f"/projects/{pid}/renders", json={})).json()
        for _ in range(200):
            job = (await client.get(f"/renders/{job['id']}")).json()
            if job["status"] in ("completed", "failed"):
                break
            await asyncio.sleep(0.1)
        assert job["status"] == "completed", job.get("error")
        return (await client.get(f"/projects/{pid}")).json()

    async def test_absent_until_the_project_is_rendered(self, client):
        pid = (
            await client.post(
                "/projects",
                json={"title": "p", "mode": "monologue", "source_text": "One two."},
            )
        ).json()["id"]
        await client.post(f"/projects/{pid}/parse", json={})
        # Nothing has been spoken yet, so there is no rate to report.
        assert (await client.get(f"/projects/{pid}")).json()["actual_wpm"] is None

    async def test_reported_once_rendered(self, client):
        project = await self._rendered_project(client)
        assert project["actual_wpm"] is not None
        assert project["actual_wpm"] > 0

    async def test_matches_words_over_speech_time(self, client):
        project = await self._rendered_project(client)
        speech_ms = sum(s["duration_ms"] for s in project["segments"])
        expected = project["word_count"] / (speech_ms / 60_000)
        assert project["actual_wpm"] == pytest.approx(expected, rel=1e-6)

    async def test_pauses_and_repeats_do_not_drag_the_rate_down(self, client):
        """Silence is not speech, so it must not count against the pace."""
        project = await self._rendered_project(client)
        baseline = project["actual_wpm"]

        # Add long pauses and a second hearing; the speaking rate is unchanged.
        await client.patch(
            f"/projects/{project['id']}",
            json={"repeat_count": 2, "pause_between_repeats_ms": 10_000},
        )
        for segment in project["segments"]:
            await client.patch(
                f"/segments/{segment['id']}", json={"pause_after_ms": 5000}
            )
        # Editing pause_after does not invalidate audio, so durations survive.
        again = (await client.get(f"/projects/{project['id']}")).json()
        assert again["actual_wpm"] == pytest.approx(baseline, rel=1e-6)
