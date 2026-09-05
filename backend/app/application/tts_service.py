"""Synthesis with a content-addressed cache in front of the providers."""

from __future__ import annotations

import hashlib
import uuid
from dataclasses import dataclass

from sqlalchemy.ext.asyncio import AsyncSession

from app.domain.resolution import cache_key, optional_hash, text_hash
from app.infrastructure.audio.ffmpeg import MIME_BY_FORMAT, FFmpeg
from app.infrastructure.db.models import AudioAsset, TTSCache
from app.infrastructure.db.upsert import insert_ignoring_conflict, insert_or_get
from app.infrastructure.storage.base import StorageBackend
from app.infrastructure.tts.base import TTSRequest
from app.infrastructure.tts.registry import TTSProviderRegistry


@dataclass(frozen=True)
class SynthesisResult:
    audio_asset: AudioAsset
    cache_hit: bool


class TTSService:
    def __init__(
        self,
        registry: TTSProviderRegistry,
        storage: StorageBackend,
        ffmpeg: FFmpeg,
    ) -> None:
        self._registry = registry
        self._storage = storage
        self._ffmpeg = ffmpeg

    async def synthesize(
        self,
        session: AsyncSession,
        *,
        provider: str,
        provider_voice_id: str,
        text: str,
        speed: float,
        output_format: str = "mp3",
        model: str | None = None,
        instructions: str | None = None,
    ) -> SynthesisResult:
        key = cache_key(
            provider=provider,
            model=model,
            provider_voice_id=provider_voice_id,
            text=text,
            speed=speed,
            instructions=instructions,
            output_format=output_format,
        )

        cached = await session.get(TTSCache, key)
        if cached is not None:
            asset = await session.get(AudioAsset, cached.audio_asset_id)
            if asset is not None and await self._storage.exists(asset.storage_key):
                cached.last_used_at = _now()
                await session.flush()
                return SynthesisResult(audio_asset=asset, cache_hit=True)
            # The asset row or blob went missing; fall through and re-render.
            await session.delete(cached)
            await session.flush()

        adapter = self._registry.get(provider)
        result = await adapter.synthesize(
            TTSRequest(
                text=text,
                provider_voice_id=provider_voice_id,
                model=model,
                speed=speed,
                output_format=output_format,
                instructions=instructions
                if adapter.capabilities.supports_instructions
                else None,
            )
        )

        src_suffix = _suffix_for_mime(result.mime_type)
        # When the provider cannot vary speed itself, time-stretch here so
        # generation_speed means the same thing whichever provider rendered it.
        atempo = None if adapter.capabilities.supports_speed else speed
        audio_bytes = await self._ffmpeg.convert(
            result.audio_bytes,
            src_suffix=src_suffix,
            out_format=output_format,
            atempo=atempo,
        )
        duration_ms = await self._ffmpeg.duration_ms(audio_bytes, output_format)

        asset = await self._store_asset(
            session, audio_bytes, output_format, duration_ms, prefix="segments"
        )
        # Another render may have cached the identical request while this one
        # was synthesizing. Both produce the same audio, so keep whichever row
        # landed first instead of failing.
        await insert_ignoring_conflict(
            session,
            TTSCache,
            {
                "cache_key": key,
                "provider": provider,
                "model": model,
                "provider_voice_id": provider_voice_id,
                "normalized_text_hash": text_hash(text),
                "instructions_hash": optional_hash(instructions),
                "speed": speed,
                "output_format": output_format,
                "audio_asset_id": asset.id,
            },
            conflict_on=["cache_key"],
        )
        await session.flush()
        return SynthesisResult(audio_asset=asset, cache_hit=False)

    async def _store_asset(
        self,
        session: AsyncSession,
        audio_bytes: bytes,
        output_format: str,
        duration_ms: int,
        *,
        prefix: str,
    ) -> AudioAsset:
        digest = hashlib.sha256(audio_bytes).hexdigest()
        storage_key = f"audio/{prefix}/{digest[:2]}/{digest}.{output_format}"

        # The key is the content hash, so re-writing the same bytes is harmless
        # and makes the write idempotent after a partial failure.
        if not await self._storage.exists(storage_key):
            await self._storage.put(
                storage_key, audio_bytes, MIME_BY_FORMAT[output_format]
            )

        # Two concurrent renders of the same sentence produce the same key.
        # The loser reuses the winner's row rather than failing the render.
        asset = await insert_or_get(
            session,
            AudioAsset,
            {
                "id": uuid.uuid4(),
                "storage_key": storage_key,
                "mime_type": MIME_BY_FORMAT[output_format],
                "format": output_format,
                "duration_ms": duration_ms,
                "size_bytes": len(audio_bytes),
                "sha256": digest,
            },
            conflict_on="storage_key",
        )
        await session.flush()
        return asset

    async def store_render(
        self,
        session: AsyncSession,
        audio_bytes: bytes,
        output_format: str,
        duration_ms: int,
    ) -> AudioAsset:
        return await self._store_asset(
            session, audio_bytes, output_format, duration_ms, prefix="renders"
        )


def _suffix_for_mime(mime_type: str) -> str:
    return {
        "audio/wav": "wav",
        "audio/x-wav": "wav",
        "audio/aiff": "aiff",
        "audio/x-aiff": "aiff",
        "audio/mpeg": "mp3",
        "audio/opus": "opus",
        "audio/aac": "aac",
        "audio/flac": "flac",
    }.get(mime_type, "wav")


def _now():
    from datetime import UTC, datetime

    return datetime.now(UTC)
