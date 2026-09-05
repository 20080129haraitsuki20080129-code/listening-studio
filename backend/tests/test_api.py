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
