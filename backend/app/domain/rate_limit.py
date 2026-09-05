"""Per-caller rate limiting.

SPEC section 22 lists request rate limits as required. On a free hosting tier
they matter more than that: rendering burns CPU, and every stored render eats
into a 500MB storage allowance and a 5GB monthly egress allowance that no card
backs. One signed-in person looping a long script could exhaust the month.

A sliding window kept in memory. That is exact for a single process, which is
what this runs as -- the model is held in memory, so there is one worker by
design. A second process would need a shared store.
"""

from __future__ import annotations

import time
from collections import defaultdict, deque
from dataclasses import dataclass

from app.domain.errors import AppError


class RateLimited(AppError):
    code = "RATE_LIMITED"
    http_status = 429
    retryable = True
    default_message = "Too many requests. Please wait a moment."

    def __init__(self, retry_after_seconds: int) -> None:
        self.retry_after_seconds = retry_after_seconds
        super().__init__(f"Too many requests. Try again in {retry_after_seconds}s.")


@dataclass(frozen=True)
class Rule:
    limit: int
    window_seconds: int


class SlidingWindowLimiter:
    def __init__(self) -> None:
        self._hits: dict[str, deque[float]] = defaultdict(deque)

    def check(self, key: str, rule: Rule, now: float | None = None) -> None:
        """Record a request, or raise if the caller is over their allowance."""
        moment = time.monotonic() if now is None else now
        hits = self._hits[key]

        cutoff = moment - rule.window_seconds
        while hits and hits[0] <= cutoff:
            hits.popleft()

        if len(hits) >= rule.limit:
            retry_after = max(1, int(hits[0] + rule.window_seconds - moment) + 1)
            raise RateLimited(retry_after)

        hits.append(moment)

    def reset(self, key: str | None = None) -> None:
        if key is None:
            self._hits.clear()
        else:
            self._hits.pop(key, None)
