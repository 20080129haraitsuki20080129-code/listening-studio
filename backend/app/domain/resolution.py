"""Effective voice and speed resolution (SPEC section 13).

Both resolve segment override -> speaker -> project default. Kept free of ORM
and provider types so it can be tested directly.
"""

from __future__ import annotations

import hashlib
import re
import uuid
from dataclasses import dataclass

_WHITESPACE = re.compile(r"\s+")

# SPEC section 10.1: the MVP slider range. Adapters clamp again to whatever the
# provider actually supports.
MIN_GENERATION_SPEED = 0.70
MAX_GENERATION_SPEED = 1.40


@dataclass(frozen=True)
class ResolutionInput:
    segment_voice_id: uuid.UUID | None
    segment_speed: float | None
    speaker_voice_id: uuid.UUID | None
    speaker_speed: float | None
    project_voice_id: uuid.UUID | None
    project_speed: float


def resolve_voice_id(source: ResolutionInput) -> uuid.UUID | None:
    return source.segment_voice_id or source.speaker_voice_id or source.project_voice_id


def resolve_speed(source: ResolutionInput) -> float:
    for candidate in (source.segment_speed, source.speaker_speed):
        if candidate is not None:
            return float(candidate)
    return float(source.project_speed)


def normalize_text(text: str) -> str:
    """Collapse whitespace so trivially different scripts share cache entries."""
    return _WHITESPACE.sub(" ", text).strip()


def cache_key(
    *,
    provider: str,
    model: str | None,
    provider_voice_id: str,
    text: str,
    speed: float,
    instructions: str | None,
    output_format: str,
) -> str:
    """SPEC section 14 cache key.

    Every input that changes the audio is part of the key, so a hit is always
    byte-identical to what a fresh synthesis would return.
    """
    parts = [
        provider,
        model or "",
        provider_voice_id,
        normalize_text(text),
        f"{float(speed):.3f}",
        instructions or "",
        output_format,
    ]
    joined = "\x1f".join(parts)
    return hashlib.sha256(joined.encode("utf-8")).hexdigest()


def text_hash(text: str) -> str:
    return hashlib.sha256(normalize_text(text).encode("utf-8")).hexdigest()


def optional_hash(value: str | None) -> str | None:
    if value is None:
        return None
    return hashlib.sha256(value.encode("utf-8")).hexdigest()
