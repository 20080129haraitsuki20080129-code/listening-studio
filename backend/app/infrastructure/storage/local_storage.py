from __future__ import annotations

from pathlib import Path

import anyio

from app.domain.errors import StorageFailed

from .base import StorageBackend


class LocalStorage(StorageBackend):
    """Filesystem storage for development.

    Production swaps in an S3/R2 backend behind the same interface.
    """

    def __init__(self, root: Path, url_prefix: str = "/api/v1/audio-files") -> None:
        self._root = Path(root).resolve()
        self._url_prefix = url_prefix.rstrip("/")
        self._root.mkdir(parents=True, exist_ok=True)

    def _path(self, key: str) -> Path:
        # Keys are built server-side, but a traversal here would write outside
        # the storage root, so verify rather than trust.
        path = (self._root / key).resolve()
        if not path.is_relative_to(self._root):
            raise StorageFailed("Invalid storage key.")
        return path

    async def put(self, key: str, data: bytes, content_type: str) -> None:
        path = self._path(key)
        try:
            path.parent.mkdir(parents=True, exist_ok=True)
            await anyio.Path(path).write_bytes(data)
        except OSError as exc:
            raise StorageFailed(f"Could not write audio: {exc}") from exc

    async def get(self, key: str) -> bytes:
        try:
            return await anyio.Path(self._path(key)).read_bytes()
        except OSError as exc:
            raise StorageFailed(f"Could not read audio: {exc}") from exc

    async def exists(self, key: str) -> bool:
        return await anyio.Path(self._path(key)).exists()

    async def delete(self, key: str) -> None:
        try:
            await anyio.Path(self._path(key)).unlink(missing_ok=True)
        except OSError as exc:
            raise StorageFailed(f"Could not delete audio: {exc}") from exc

    def public_url(self, key: str) -> str:
        return f"{self._url_prefix}/{key}"

    @property
    def root(self) -> Path:
        return self._root
