from __future__ import annotations

from abc import ABC, abstractmethod


class StorageBackend(ABC):
    """Object storage for rendered audio.

    Audio never goes into PostgreSQL (SPEC section 17); the database keeps only
    metadata and the storage key.
    """

    @abstractmethod
    async def put(self, key: str, data: bytes, content_type: str) -> None: ...

    @abstractmethod
    async def get(self, key: str) -> bytes: ...

    @abstractmethod
    async def exists(self, key: str) -> bool: ...

    @abstractmethod
    async def delete(self, key: str) -> None: ...

    @abstractmethod
    def public_url(self, key: str) -> str: ...
