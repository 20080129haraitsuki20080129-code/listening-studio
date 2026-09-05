"""Integration tests over the real app, real PostgreSQL, stubbed TTS."""

from __future__ import annotations

import pytest

DIALOGUE = "[A]\nHello there.\n\n[B]\nHi. How are you?"


async def _sync_voices(client):
    await client.post("/voices/sync")
    voices = (await client.get("/voices")).json()["items"]
    return {v["accent"]: v for v in voices}


class TestHealth:
    async def test_health(self, client):
        r = await client.get("/health")
        assert r.status_code == 200
        assert r.json() == {"status": "ok"}


class TestVoices:
    async def test_sync_then_filter(self, client):
        r = await client.post("/voices/sync")
        assert r.status_code == 200
        assert r.json()["created"] == 2

        r = await client.get("/voices?accent=british")
        items = r.json()["items"]
        assert len(items) == 1
        assert items[0]["gender"] == "male"

    async def test_sync_is_idempotent(self, client):
        await client.post("/voices/sync")
        second = (await client.post("/voices/sync")).json()
        assert second["created"] == 0
        assert second["updated"] == 2

    async def test_gender_filter(self, client):
        await _sync_voices(client)
        items = (await client.get("/voices?gender=female")).json()["items"]
        assert [v["accent"] for v in items] == ["american"]


class TestProjectCrud:
    async def test_create_get_update_delete(self, client):
        created = (
            await client.post("/projects", json={"title": "T", "mode": "monologue"})
        ).json()
        pid = created["id"]

        assert (await client.get(f"/projects/{pid}")).status_code == 200

        patched = (await client.patch(f"/projects/{pid}", json={"title": "New"})).json()
        assert patched["title"] == "New"

        assert (await client.delete(f"/projects/{pid}")).status_code == 204
        # Soft delete: the row survives but is no longer reachable.
        assert (await client.get(f"/projects/{pid}")).status_code == 404

    async def test_settings_persist_across_reads(self, client):
        pid = (
            await client.post("/projects", json={"title": "T", "mode": "monologue"})
        ).json()["id"]
        await client.patch(
            f"/projects/{pid}",
            json={
                "default_generation_speed": 1.25,
                "transcript_visible_default": False,
            },
        )
        again = (await client.get(f"/projects/{pid}")).json()
        assert again["default_generation_speed"] == pytest.approx(1.25)
        assert again["transcript_visible_default"] is False

    async def test_unknown_project_is_a_normalized_error(self, client):
        r = await client.get("/projects/00000000-0000-0000-0000-000000000000")
        assert r.status_code == 404
        assert r.json()["error"]["code"] == "NOT_FOUND"
        assert r.json()["error"]["retryable"] is False


class TestParsing:
    async def test_dialogue_creates_speakers_and_segments(self, client):
        pid = (
            await client.post(
                "/projects",
                json={"title": "D", "mode": "dialogue", "source_text": DIALOGUE},
            )
        ).json()["id"]

        parsed = (await client.post(f"/projects/{pid}/parse", json={})).json()
        assert [s["label"] for s in parsed["speakers"]] == ["A", "B"]
        assert len(parsed["segments"]) == 3

        project = (await client.get(f"/projects/{pid}")).json()
        assert len(project["speakers"]) == 2
        assert len(project["segments"]) == 3

    async def test_reparse_keeps_speaker_voice_assignments(self, client):
        voices = await _sync_voices(client)
        pid = (
            await client.post(
                "/projects",
                json={"title": "D", "mode": "dialogue", "source_text": DIALOGUE},
            )
        ).json()["id"]
        await client.post(f"/projects/{pid}/parse", json={})

        project = (await client.get(f"/projects/{pid}")).json()
        speaker_a = next(s for s in project["speakers"] if s["label"] == "A")
        await client.patch(
            f"/speakers/{speaker_a['id']}", json={"voice_id": voices["british"]["id"]}
        )

        await client.post(
            f"/projects/{pid}/parse",
            json={"source_text": DIALOGUE + "\n\n[A]\nOne more."},
        )
        project = (await client.get(f"/projects/{pid}")).json()
        speaker_a = next(s for s in project["speakers"] if s["label"] == "A")
        assert speaker_a["voice_id"] == voices["british"]["id"]

    async def test_empty_script_is_rejected(self, client):
        pid = (
            await client.post("/projects", json={"title": "E", "mode": "monologue"})
        ).json()["id"]
        r = await client.post(f"/projects/{pid}/parse", json={"source_text": "   "})
        assert r.status_code == 422
        assert r.json()["error"]["code"] == "INVALID_SCRIPT"


class TestRendering:
    async def _prepared_project(self, client):
        voices = await _sync_voices(client)
        pid = (
            await client.post(
                "/projects",
                json={"title": "D", "mode": "dialogue", "source_text": DIALOGUE},
            )
        ).json()["id"]
        await client.post(f"/projects/{pid}/parse", json={})
        project = (await client.get(f"/projects/{pid}")).json()
        for speaker in project["speakers"]:
            accent = "british" if speaker["label"] == "A" else "american"
            await client.patch(
                f"/speakers/{speaker['id']}", json={"voice_id": voices[accent]["id"]}
            )
        return pid, voices

    async def test_segment_render(self, client):
        pid, _ = await self._prepared_project(client)
        segment = (await client.get(f"/projects/{pid}")).json()["segments"][0]
        r = await client.post(f"/segments/{segment['id']}/render")
        assert r.status_code == 200
        body = r.json()
        assert body["duration_ms"] > 0
        assert body["audio_url"].endswith(".mp3")

    async def test_render_without_a_voice_is_a_normalized_error(self, client):
        pid = (
            await client.post(
                "/projects",
                json={"title": "M", "mode": "monologue", "source_text": "Hello."},
            )
        ).json()["id"]
        await client.post(f"/projects/{pid}/parse", json={})
        segment = (await client.get(f"/projects/{pid}")).json()["segments"][0]
        r = await client.post(f"/segments/{segment['id']}/render")
        assert r.status_code == 422
        assert r.json()["error"]["code"] == "INVALID_SCRIPT"

    async def test_speakers_use_their_own_configured_voice(self, client):
        """SPEC section 26: A and B must render with different voice ids."""
        from app.api import deps

        pid, _ = await self._prepared_project(client)
        stub = deps.get_container().registry.get("kokoro")
        stub.calls.clear()

        for segment in (await client.get(f"/projects/{pid}")).json()["segments"]:
            await client.post(f"/segments/{segment['id']}/render")

        used = [c.provider_voice_id for c in stub.calls]
        assert "stub_bm" in used
        assert "stub_af" in used

    async def test_editing_text_invalidates_the_rendered_audio(self, client):
        pid, _ = await self._prepared_project(client)
        segment = (await client.get(f"/projects/{pid}")).json()["segments"][0]
        await client.post(f"/segments/{segment['id']}/render")

        assert (await client.get(f"/projects/{pid}")).json()["segments"][0][
            "audio_asset_id"
        ] is not None

        updated = (
            await client.patch(f"/segments/{segment['id']}", json={"text": "Changed."})
        ).json()
        assert updated["audio_asset_id"] is None

    async def test_cache_avoids_a_second_provider_call(self, client):
        from app.api import deps

        pid, _ = await self._prepared_project(client)
        segment = (await client.get(f"/projects/{pid}")).json()["segments"][0]
        stub = deps.get_container().registry.get("kokoro")

        stub.calls.clear()
        await client.post(f"/segments/{segment['id']}/render")
        assert len(stub.calls) == 1

        await client.post(f"/segments/{segment['id']}/render")
        assert len(stub.calls) == 1, "identical request should hit the cache"

    async def test_project_render_completes(self, client):
        import asyncio

        pid, _ = await self._prepared_project(client)
        job = (
            await client.post(f"/projects/{pid}/renders", json={"format": "mp3"})
        ).json()

        for _ in range(100):
            job = (await client.get(f"/renders/{job['id']}")).json()
            if job["status"] in ("completed", "failed"):
                break
            await asyncio.sleep(0.1)

        assert job["status"] == "completed", job.get("error")
        assert job["progress"] == 100
        assert job["duration_ms"] > 0

    async def test_idempotency_key_reuses_the_job(self, client):
        pid, _ = await self._prepared_project(client)
        headers = {"Idempotency-Key": "same"}
        first = (
            await client.post(f"/projects/{pid}/renders", json={}, headers=headers)
        ).json()
        second = (
            await client.post(f"/projects/{pid}/renders", json={}, headers=headers)
        ).json()
        assert first["id"] == second["id"]

    async def test_different_keys_create_different_jobs(self, client):
        pid, _ = await self._prepared_project(client)
        first = (
            await client.post(
                f"/projects/{pid}/renders", json={}, headers={"Idempotency-Key": "a"}
            )
        ).json()
        second = (
            await client.post(
                f"/projects/{pid}/renders", json={}, headers={"Idempotency-Key": "b"}
            )
        ).json()
        assert first["id"] != second["id"]


class TestErrorEnvelope:
    async def test_every_error_carries_a_request_id(self, client):
        r = await client.get("/projects/00000000-0000-0000-0000-000000000000")
        body = r.json()["error"]
        assert set(body) >= {"code", "message", "retryable", "request_id"}
        assert body["request_id"]

    async def test_unknown_voice_reference_is_rejected(self, client):
        pid = (
            await client.post("/projects", json={"title": "T", "mode": "monologue"})
        ).json()["id"]
        r = await client.post(
            f"/projects/{pid}/speakers",
            json={"label": "A", "voice_id": "00000000-0000-0000-0000-000000000000"},
        )
        assert r.status_code == 404
        assert r.json()["error"]["code"] == "VOICE_NOT_FOUND"


class TestConcurrentRenders:
    """Two renders of the same sentence must share the cache, not collide.

    The TTS cache and audio assets are content-addressed, so concurrent renders
    of identical text race for the same primary key. Before the inserts were
    made conflict-tolerant this surfaced as a UniqueViolation that failed the
    whole render.
    """

    async def _project_with_text(self, client, voices, text: str) -> str:
        pid = (
            await client.post(
                "/projects",
                json={"title": "concurrent", "mode": "monologue", "source_text": text},
            )
        ).json()["id"]
        await client.patch(
            f"/projects/{pid}", json={"default_voice_id": voices["british"]["id"]}
        )
        await client.post(f"/projects/{pid}/parse", json={})
        return pid

    async def test_identical_text_in_two_projects_both_render(self, client):
        import asyncio

        voices = await _sync_voices(client)
        shared = "A shared sentence that both projects contain."
        first = await self._project_with_text(client, voices, shared)
        second = await self._project_with_text(client, voices, shared)

        jobs = [
            (await client.post(f"/projects/{pid}/renders", json={})).json()
            for pid in (first, second)
        ]

        finished = []
        for job in jobs:
            for _ in range(150):
                current = (await client.get(f"/renders/{job['id']}")).json()
                if current["status"] in ("completed", "failed"):
                    break
                await asyncio.sleep(0.1)
            finished.append(current)

        assert [j["status"] for j in finished] == ["completed", "completed"], [
            j.get("error") for j in finished
        ]

    async def test_second_render_of_identical_text_reuses_the_audio(self, client):
        import asyncio

        voices = await _sync_voices(client)
        shared = "Another shared sentence for the cache."
        first = await self._project_with_text(client, voices, shared)
        second = await self._project_with_text(client, voices, shared)

        async def render(pid):
            job = (await client.post(f"/projects/{pid}/renders", json={})).json()
            for _ in range(150):
                current = (await client.get(f"/renders/{job['id']}")).json()
                if current["status"] in ("completed", "failed"):
                    return current
                await asyncio.sleep(0.1)
            return current

        await render(first)
        await render(second)

        segments = [
            (await client.get(f"/projects/{pid}")).json()["segments"][0]
            for pid in (first, second)
        ]
        # Same text, same voice, same speed -> the identical cached asset.
        assert segments[0]["audio_asset_id"] == segments[1]["audio_asset_id"]


class TestSpeakerRoster:
    async def _dialogue(self, client) -> str:
        pid = (
            await client.post(
                "/projects",
                json={
                    "title": "roster",
                    "mode": "dialogue",
                    "source_text": "[A]\nOne.\n\n[B]\nTwo.\n\n[C]\nThree.",
                },
            )
        ).json()["id"]
        await client.post(f"/projects/{pid}/parse", json={})
        return pid

    async def test_sets_an_exact_number_of_speakers(self, client):
        pid = await self._dialogue(client)
        speakers = (
            await client.put(f"/projects/{pid}/speakers", json={"count": 4})
        ).json()
        assert [s["label"] for s in speakers] == ["A", "B", "C", "D"]
        assert [s["display_name"] for s in speakers] == [
            "Voice 1", "Voice 2", "Voice 3", "Voice 4",
        ]

    async def test_shrinking_keeps_every_segment_attached_to_a_speaker(self, client):
        pid = await self._dialogue(client)
        await client.put(f"/projects/{pid}/speakers", json={"count": 2})

        project = (await client.get(f"/projects/{pid}")).json()
        assert len(project["speakers"]) == 2
        # Segments from the removed speaker move to the first one rather than
        # losing their voice.
        assert all(s["speaker_id"] for s in project["segments"])
        live = {s["id"] for s in project["speakers"]}
        assert {s["speaker_id"] for s in project["segments"]} <= live

    async def test_growing_preserves_existing_voice_assignments(self, client):
        voices = await _sync_voices(client)
        pid = await self._dialogue(client)
        project = (await client.get(f"/projects/{pid}")).json()
        first = project["speakers"][0]
        await client.patch(
            f"/speakers/{first['id']}", json={"voice_id": voices["british"]["id"]}
        )

        await client.put(f"/projects/{pid}/speakers", json={"count": 5})
        project = (await client.get(f"/projects/{pid}")).json()
        kept = next(s for s in project["speakers"] if s["label"] == "A")
        assert kept["voice_id"] == voices["british"]["id"]

    async def test_rejects_an_unreasonable_count(self, client):
        pid = await self._dialogue(client)
        r = await client.put(f"/projects/{pid}/speakers", json={"count": 99})
        assert r.status_code == 422

    async def test_speaker_with_segments_cannot_be_deleted_directly(self, client):
        pid = await self._dialogue(client)
        project = (await client.get(f"/projects/{pid}")).json()
        used = project["speakers"][0]
        r = await client.delete(f"/speakers/{used['id']}")
        assert r.status_code == 422
        assert r.json()["error"]["code"] == "INVALID_SCRIPT"


class TestDownloads:
    async def test_transcript_pdf_has_pdf_headers_and_content(self, client):
        pid = (
            await client.post(
                "/projects",
                json={
                    "title": "Download me",
                    "mode": "monologue",
                    "source_text": "One sentence. Two sentences.",
                },
            )
        ).json()["id"]
        await client.post(f"/projects/{pid}/parse", json={})

        r = await client.get(f"/projects/{pid}/transcript.pdf")
        assert r.status_code == 200
        assert r.headers["content-type"] == "application/pdf"
        assert "attachment" in r.headers["content-disposition"]
        assert "Download_me.pdf" in r.headers["content-disposition"]
        assert r.content.startswith(b"%PDF")

    async def test_japanese_title_keeps_an_ascii_fallback_filename(self, client):
        pid = (
            await client.post(
                "/projects",
                json={
                    "title": "三人会話",
                    "mode": "monologue",
                    "source_text": "One sentence.",
                },
            )
        ).json()["id"]
        await client.post(f"/projects/{pid}/parse", json={})

        r = await client.get(f"/projects/{pid}/transcript.pdf")
        disposition = r.headers["content-disposition"]
        # Stripping a fully Japanese title must not yield a file called ".pdf".
        assert 'filename="listening.pdf"' in disposition
        assert "filename*=UTF-8''" in disposition

    async def test_transcript_before_parsing_is_rejected(self, client):
        pid = (
            await client.post("/projects", json={"title": "Empty", "mode": "monologue"})
        ).json()["id"]
        r = await client.get(f"/projects/{pid}/transcript.pdf")
        assert r.status_code == 422
        assert r.json()["error"]["code"] == "INVALID_SCRIPT"

    async def test_audio_download_requires_a_finished_render(self, client):
        voices = await _sync_voices(client)
        pid = (
            await client.post(
                "/projects",
                json={"title": "Audio", "mode": "monologue", "source_text": "Hello."},
            )
        ).json()["id"]
        await client.patch(
            f"/projects/{pid}", json={"default_voice_id": voices["british"]["id"]}
        )
        await client.post(f"/projects/{pid}/parse", json={})

        job = (await client.post(f"/projects/{pid}/renders", json={})).json()
        early = await client.get(f"/renders/{job['id']}/download")
        assert early.status_code == 422

        import asyncio

        for _ in range(150):
            current = (await client.get(f"/renders/{job['id']}")).json()
            if current["status"] in ("completed", "failed"):
                break
            await asyncio.sleep(0.1)
        assert current["status"] == "completed", current.get("error")

        r = await client.get(f"/renders/{job['id']}/download")
        assert r.status_code == 200
        assert r.headers["content-type"] == "audio/mpeg"
        assert "Audio.mp3" in r.headers["content-disposition"]
        assert len(r.content) > 0


class TestSpeakerOrdering:
    """Voice slots are numbered by position, so the order must be stable.

    Without an explicit order the database chooses, and the UI's "Voice 1"
    could point at [B] one reload and [A] the next.
    """

    async def test_speakers_come_back_in_label_order(self, client):
        pid = (
            await client.post(
                "/projects",
                json={
                    "title": "order",
                    "mode": "dialogue",
                    # Deliberately introduce B before A.
                    "source_text": "[B]\nSecond.\n\n[A]\nFirst.\n\n[C]\nThird.",
                },
            )
        ).json()["id"]
        await client.post(f"/projects/{pid}/parse", json={})

        project = (await client.get(f"/projects/{pid}")).json()
        assert [s["label"] for s in project["speakers"]] == ["A", "B", "C"]

    async def test_order_is_stable_across_reloads_and_roster_changes(self, client):
        pid = (
            await client.post(
                "/projects",
                json={
                    "title": "order",
                    "mode": "dialogue",
                    "source_text": "[C]\nThird.\n\n[A]\nFirst.\n\n[B]\nSecond.",
                },
            )
        ).json()["id"]
        await client.post(f"/projects/{pid}/parse", json={})

        seen = []
        for _ in range(3):
            project = (await client.get(f"/projects/{pid}")).json()
            seen.append([s["label"] for s in project["speakers"]])
        assert seen == [["A", "B", "C"]] * 3

        roster = (
            await client.put(f"/projects/{pid}/speakers", json={"count": 4})
        ).json()
        assert [s["label"] for s in roster] == ["A", "B", "C", "D"]
        project = (await client.get(f"/projects/{pid}")).json()
        assert [s["label"] for s in project["speakers"]] == ["A", "B", "C", "D"]


class TestStyledDialogueApi:
    """Speakers marked by bold / italic / underline rather than [A] / [B]."""

    STYLED = (
        "<div>Plain turn.</div>"
        "<div><b>Bold turn.</b></div>"
        "<div><u>Underline turn.</u></div>"
    )

    async def test_styles_become_speakers_with_a_style_key(self, client):
        pid = (
            await client.post(
                "/projects",
                json={"title": "styled", "mode": "dialogue", "source_text": self.STYLED},
            )
        ).json()["id"]
        await client.post(f"/projects/{pid}/parse", json={})

        project = (await client.get(f"/projects/{pid}")).json()
        assert project["styled_dialogue"] is True
        assert [(s["label"], s["style_key"]) for s in project["speakers"]] == [
            ("A", "plain"),
            ("B", "bold"),
            ("D", "underline"),
        ]

    async def test_marker_dialogue_is_not_flagged_as_styled(self, client):
        pid = (
            await client.post(
                "/projects",
                json={
                    "title": "markers",
                    "mode": "dialogue",
                    "source_text": "[A]\nHello.\n\n[B]\nHi.",
                },
            )
        ).json()["id"]
        await client.post(f"/projects/{pid}/parse", json={})
        assert (await client.get(f"/projects/{pid}")).json()["styled_dialogue"] is False

    async def test_restyling_removes_the_slot_that_is_no_longer_used(self, client):
        pid = (
            await client.post(
                "/projects",
                json={"title": "styled", "mode": "dialogue", "source_text": self.STYLED},
            )
        ).json()["id"]
        await client.post(f"/projects/{pid}/parse", json={})
        assert len((await client.get(f"/projects/{pid}")).json()["speakers"]) == 3

        # Drop the plain and underline turns; only bold remains.
        await client.post(
            f"/projects/{pid}/parse",
            json={"source_text": "<div><b>Only bold now.</b></div>"},
        )
        project = (await client.get(f"/projects/{pid}")).json()
        assert [(s["label"], s["style_key"]) for s in project["speakers"]] == [
            ("B", "bold")
        ]

    async def test_restyling_keeps_the_voice_of_a_slot_that_survives(self, client):
        voices = await _sync_voices(client)
        pid = (
            await client.post(
                "/projects",
                json={"title": "styled", "mode": "dialogue", "source_text": self.STYLED},
            )
        ).json()["id"]
        await client.post(f"/projects/{pid}/parse", json={})

        project = (await client.get(f"/projects/{pid}")).json()
        bold = next(s for s in project["speakers"] if s["label"] == "B")
        await client.patch(
            f"/speakers/{bold['id']}", json={"voice_id": voices["british"]["id"]}
        )

        await client.post(
            f"/projects/{pid}/parse",
            json={
                "source_text": "<div><b>Bold stays.</b></div><div><i>Italic joins.</i></div>"
            },
        )
        project = (await client.get(f"/projects/{pid}")).json()
        bold = next(s for s in project["speakers"] if s["label"] == "B")
        assert bold["voice_id"] == voices["british"]["id"]
        assert {s["label"] for s in project["speakers"]} == {"B", "C"}

    async def test_all_eight_styles_are_usable_at_once(self, client):
        combos = [
            ("", ""), ("<b>", "</b>"), ("<i>", "</i>"), ("<u>", "</u>"),
            ("<b><i>", "</i></b>"), ("<b><u>", "</u></b>"),
            ("<i><u>", "</u></i>"), ("<b><i><u>", "</u></i></b>"),
        ]
        html = "".join(
            f"<div>{o}Turn {i}.{c}</div>" for i, (o, c) in enumerate(combos)
        )
        pid = (
            await client.post(
                "/projects",
                json={"title": "eight", "mode": "dialogue", "source_text": html},
            )
        ).json()["id"]
        await client.post(f"/projects/{pid}/parse", json={})

        project = (await client.get(f"/projects/{pid}")).json()
        assert [s["label"] for s in project["speakers"]] == list("ABCDEFGH")
        assert [s["style_key"] for s in project["speakers"]] == [
            "plain", "bold", "italic", "underline",
            "bold_italic", "bold_underline", "italic_underline",
            "bold_italic_underline",
        ]
