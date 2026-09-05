"""FFmpeg/ffprobe wrapper.

All audio processing goes through here; nothing above this module shells out
to FFmpeg directly (SPEC section 18).
"""

from __future__ import annotations

import json
import subprocess
import tempfile
from pathlib import Path

import anyio

from app.domain.errors import AudioProcessingFailed

MIME_BY_FORMAT = {
    "mp3": "audio/mpeg",
    "wav": "audio/wav",
    "opus": "audio/opus",
    "aac": "audio/aac",
    "flac": "audio/flac",
}

_ENCODER_ARGS = {
    "mp3": ["-codec:a", "libmp3lame", "-b:a", "128k"],
    "wav": ["-codec:a", "pcm_s16le"],
    "opus": ["-codec:a", "libopus", "-b:a", "96k"],
    "aac": ["-codec:a", "aac", "-b:a", "128k"],
    "flac": ["-codec:a", "flac"],
}

# EBU R128, the normalization SPEC section 15 recommends.
_LOUDNORM = "loudnorm=I=-16:TP=-1.5:LRA=11"


class FFmpeg:
    def __init__(
        self, ffmpeg_bin: str = "ffmpeg", ffprobe_bin: str = "ffprobe"
    ) -> None:
        self._ffmpeg = ffmpeg_bin
        self._ffprobe = ffprobe_bin

    def _run(self, args: list[str], *, timeout: int = 300) -> bytes:
        proc = subprocess.run(args, capture_output=True, timeout=timeout, check=False)
        if proc.returncode != 0:
            detail = proc.stderr.decode("utf-8", "replace").strip().splitlines()
            tail = detail[-1] if detail else "unknown error"
            raise AudioProcessingFailed(f"FFmpeg failed: {tail}")
        return proc.stdout

    # ---------- probing ----------

    def _duration_ms_blocking(self, data: bytes, suffix: str) -> int:
        with tempfile.TemporaryDirectory() as tmp:
            src = Path(tmp) / f"probe.{suffix}"
            src.write_bytes(data)
            out = self._run(
                [
                    self._ffprobe,
                    "-v",
                    "error",
                    "-show_entries",
                    "format=duration",
                    "-of",
                    "json",
                    str(src),
                ],
                timeout=60,
            )
        try:
            seconds = float(json.loads(out)["format"]["duration"])
        except (KeyError, ValueError, json.JSONDecodeError) as exc:
            raise AudioProcessingFailed("Could not determine audio duration.") from exc
        return round(seconds * 1000)

    async def duration_ms(self, data: bytes, suffix: str = "wav") -> int:
        return await anyio.to_thread.run_sync(self._duration_ms_blocking, data, suffix)

    # ---------- conversion ----------

    def _convert_blocking(
        self, data: bytes, src_suffix: str, out_format: str, atempo: float | None
    ) -> bytes:
        if out_format not in _ENCODER_ARGS:
            raise AudioProcessingFailed(f"Unsupported output format: {out_format}")
        with tempfile.TemporaryDirectory() as tmp:
            src = Path(tmp) / f"in.{src_suffix}"
            dst = Path(tmp) / f"out.{out_format}"
            src.write_bytes(data)
            args = [self._ffmpeg, "-y", "-loglevel", "error", "-i", str(src)]
            if atempo is not None and abs(atempo - 1.0) > 1e-3:
                args += ["-filter:a", _atempo_chain(atempo)]
            args += [*_ENCODER_ARGS[out_format], str(dst)]
            self._run(args)
            return dst.read_bytes()

    async def convert(
        self,
        data: bytes,
        *,
        src_suffix: str,
        out_format: str,
        atempo: float | None = None,
    ) -> bytes:
        """Transcode, optionally time-stretching.

        `atempo` is the fallback path for providers that cannot change speed
        themselves, so `generation_speed` means the same thing to the user
        regardless of which provider rendered the segment.
        """
        return await anyio.to_thread.run_sync(
            self._convert_blocking, data, src_suffix, out_format, atempo
        )

    # ---------- assembly ----------

    def _concat_blocking(
        self,
        parts: list[tuple[bytes, str]],
        gaps_ms: list[int],
        out_format: str,
        normalize: bool,
    ) -> bytes:
        with tempfile.TemporaryDirectory() as tmp:
            tmpdir = Path(tmp)
            pieces: list[Path] = []

            for i, (data, suffix) in enumerate(parts):
                gap_before = gaps_ms[i]
                if gap_before > 0:
                    silence = tmpdir / f"sil_{i}.wav"
                    self._run(
                        [
                            self._ffmpeg,
                            "-y",
                            "-loglevel",
                            "error",
                            "-f",
                            "lavfi",
                            "-i",
                            "anullsrc=channel_layout=mono:sample_rate=24000",
                            "-t",
                            f"{gap_before / 1000:.3f}",
                            "-codec:a",
                            "pcm_s16le",
                            str(silence),
                        ]
                    )
                    pieces.append(silence)

                # Normalize every part to one PCM format first: the concat
                # demuxer requires identical streams.
                piece = tmpdir / f"part_{i}.wav"
                raw = tmpdir / f"raw_{i}.{suffix}"
                raw.write_bytes(data)
                self._run(
                    [
                        self._ffmpeg,
                        "-y",
                        "-loglevel",
                        "error",
                        "-i",
                        str(raw),
                        "-ac",
                        "1",
                        "-ar",
                        "24000",
                        "-codec:a",
                        "pcm_s16le",
                        str(piece),
                    ]
                )
                pieces.append(piece)

            if not pieces:
                raise AudioProcessingFailed("Nothing to concatenate.")

            listing = tmpdir / "concat.txt"
            listing.write_text(
                "".join(f"file '{p.name}'\n" for p in pieces), encoding="utf-8"
            )

            dst = tmpdir / f"final.{out_format}"
            args = [
                self._ffmpeg,
                "-y",
                "-loglevel",
                "error",
                "-f",
                "concat",
                "-safe",
                "0",
                "-i",
                str(listing),
            ]
            if normalize:
                args += ["-filter:a", _LOUDNORM]
            args += [*_ENCODER_ARGS[out_format], str(dst)]
            self._run(args, timeout=900)
            return dst.read_bytes()

    async def concat(
        self,
        parts: list[tuple[bytes, str]],
        gaps_ms: list[int],
        *,
        out_format: str = "mp3",
        normalize: bool = True,
    ) -> bytes:
        """Join parts with leading silences, then loudness-normalize once.

        `gaps_ms[i]` is the silence inserted before `parts[i]`. Normalization
        runs on the assembled track rather than per segment, so segments keep
        their relative levels.
        """
        if len(parts) != len(gaps_ms):
            raise AudioProcessingFailed("parts and gaps_ms must be the same length.")
        return await anyio.to_thread.run_sync(
            self._concat_blocking, parts, gaps_ms, out_format, normalize
        )


def _atempo_chain(rate: float) -> str:
    """Build an atempo chain. A single atempo only accepts 0.5-2.0."""
    if rate <= 0:
        raise AudioProcessingFailed("Playback rate must be positive.")
    factors: list[float] = []
    remaining = rate
    while remaining > 2.0:
        factors.append(2.0)
        remaining /= 2.0
    while remaining < 0.5:
        factors.append(0.5)
        remaining /= 0.5
    factors.append(remaining)
    return ",".join(f"atempo={f:.6f}" for f in factors)
