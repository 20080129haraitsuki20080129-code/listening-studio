"""Helpers for file downloads."""

from __future__ import annotations

import re
from urllib.parse import quote

_UNSAFE = re.compile(r"[^\w\-. ]+", re.UNICODE)


def safe_filename(title: str, extension: str, fallback: str = "listening") -> str:
    """A filename derived from a user-supplied title."""
    cleaned = _UNSAFE.sub("", title).strip().replace(" ", "_")
    return f"{cleaned or fallback}.{extension}"


def content_disposition(filename: str, fallback: str = "listening") -> str:
    """RFC 6266 disposition that survives non-ASCII names.

    `filename*` carries the real name; the plain `filename` is the ASCII-only
    fallback older clients use. Stripping a fully Japanese title leaves nothing
    but the extension, so the fallback stem is substituted rather than handing
    out a file called ".pdf".
    """
    stem, _, extension = filename.rpartition(".")
    if not stem:
        stem, extension = filename, ""
    ascii_stem = stem.encode("ascii", "ignore").decode().strip(" ._-") or fallback
    ascii_name = f"{ascii_stem}.{extension}" if extension else ascii_stem
    return f"attachment; filename=\"{ascii_name}\"; filename*=UTF-8''{quote(filename)}"
