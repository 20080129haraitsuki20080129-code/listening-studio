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

    def test_speed_and_wpm_both_increase(self):
        speeds = [level.speed for level in SPEED_LEVELS]
        assert speeds == sorted(speeds)
        mins = [level.wpm_min for level in SPEED_LEVELS]
        assert mins == sorted(mins)

    def test_bands_are_contiguous(self):
        # A gap between bands would leave a pace the scale cannot express.
        for lower, upper in pairwise(SPEED_LEVELS):
            assert lower.wpm_max >= upper.wpm_min

    def test_stops_before_the_discontinuity(self):
        # Kokoro jumps from ~176 wpm at 1.30 to ~213 at 1.40, so a level above
        # 1.30 would not sit evenly between its neighbours.
        assert max(level.speed for level in SPEED_LEVELS) == pytest.approx(1.30)

    def test_default_is_the_middle_level(self):
        assert DEFAULT_LEVEL == 4
        assert speed_for_level(DEFAULT_LEVEL) == pytest.approx(1.0)

    @pytest.mark.parametrize(
        "speed,expected",
        [(0.70, 1), (0.95, 3), (1.0, 4), (1.24, 6), (1.30, 7), (1.4, 7), (0.1, 1)],
    )
    def test_stored_speed_maps_to_the_nearest_level(self, speed, expected):
        # Projects store a multiplier, including values saved before these
        # presets existed, so every one must land on a level.
        assert level_for_speed(speed).level == expected

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
