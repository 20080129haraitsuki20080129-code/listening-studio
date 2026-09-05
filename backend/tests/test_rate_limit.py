"""Rate limiting protects free-tier CPU, storage and egress allowances."""

from __future__ import annotations

import pytest

from app.domain.rate_limit import RateLimited, Rule, SlidingWindowLimiter

RULE = Rule(limit=3, window_seconds=60)


class TestSlidingWindow:
    def test_allows_up_to_the_limit(self):
        limiter = SlidingWindowLimiter()
        for i in range(3):
            limiter.check("user", RULE, now=float(i))

    def test_refuses_the_one_after(self):
        limiter = SlidingWindowLimiter()
        for i in range(3):
            limiter.check("user", RULE, now=float(i))
        with pytest.raises(RateLimited):
            limiter.check("user", RULE, now=3.0)

    def test_the_window_slides(self):
        limiter = SlidingWindowLimiter()
        for i in range(3):
            limiter.check("user", RULE, now=float(i))
        # Once the earliest hit ages out, another is allowed.
        limiter.check("user", RULE, now=61.0)

    def test_callers_are_counted_separately(self):
        limiter = SlidingWindowLimiter()
        for i in range(3):
            limiter.check("alice", RULE, now=float(i))
        # One person exhausting their allowance must not block anyone else.
        limiter.check("bob", RULE, now=3.0)

    def test_reports_when_to_retry(self):
        limiter = SlidingWindowLimiter()
        for i in range(3):
            limiter.check("user", RULE, now=float(i))
        with pytest.raises(RateLimited) as caught:
            limiter.check("user", RULE, now=10.0)
        # The first hit was at t=0 and ages out at t=60.
        assert 50 <= caught.value.retry_after_seconds <= 52
        assert caught.value.http_status == 429
        assert caught.value.retryable is True

    def test_old_hits_do_not_accumulate(self):
        limiter = SlidingWindowLimiter()
        for i in range(200):
            limiter.check("user", RULE, now=float(i * 60))
        # Expired entries are dropped rather than growing without bound.
        assert len(limiter._hits["user"]) == 1

    def test_reset_clears_a_caller(self):
        limiter = SlidingWindowLimiter()
        for i in range(3):
            limiter.check("user", RULE, now=float(i))
        limiter.reset("user")
        limiter.check("user", RULE, now=3.0)


class TestApiRateLimiting:
    """The limits as they apply over HTTP."""

    async def test_render_requests_are_capped(self, client):
        from app.api import deps

        container = deps.get_container()
        original = container.settings
        container.settings = original.model_copy(
            update={"rate_limit_renders_per_hour": 2}
        )
        container.limiter.reset()
        try:
            voices = (await client.post("/voices/sync")) and (
                await client.get("/voices")
            ).json()["items"]
            pid = (
                await client.post(
                    "/projects",
                    json={
                        "title": "capped",
                        "mode": "monologue",
                        "source_text": "One sentence.",
                    },
                )
            ).json()["id"]
            await client.patch(
                f"/projects/{pid}", json={"default_voice_id": voices[0]["id"]}
            )
            await client.post(f"/projects/{pid}/parse", json={})

            for _ in range(2):
                assert (
                    await client.post(f"/projects/{pid}/renders", json={})
                ).status_code == 202

            # Rendering is what burns CPU, storage and egress, so the third is
            # refused rather than served.
            refused = await client.post(f"/projects/{pid}/renders", json={})
            assert refused.status_code == 429
            body = refused.json()["error"]
            assert body["code"] == "RATE_LIMITED"
            assert body["retryable"] is True
        finally:
            container.settings = original
            container.limiter.reset()

    async def test_a_limit_of_zero_disables_the_rule(self, client):
        from app.api import deps

        container = deps.get_container()
        original = container.settings
        container.settings = original.model_copy(
            update={"rate_limit_writes_per_minute": 0}
        )
        container.limiter.reset()
        try:
            for _ in range(5):
                assert (
                    await client.post(
                        "/projects", json={"title": "t", "mode": "monologue"}
                    )
                ).status_code == 201
        finally:
            container.settings = original
            container.limiter.reset()

    async def test_reading_is_not_rate_limited(self, client):
        """Only the paths that cost something are capped."""
        from app.api import deps

        container = deps.get_container()
        original = container.settings
        container.settings = original.model_copy(
            update={"rate_limit_writes_per_minute": 1}
        )
        container.limiter.reset()
        try:
            for _ in range(10):
                assert (await client.get("/projects")).status_code == 200
        finally:
            container.settings = original
            container.limiter.reset()
