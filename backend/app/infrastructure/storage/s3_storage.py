"""Object storage over the S3 API.

Written against the S3 protocol rather than any one vendor, so the same class
serves Supabase Storage, Cloudflare R2, Backblaze B2 or S3 itself -- only the
endpoint changes. That matters because the free tiers people can actually sign
up for keep moving.

boto3 is synchronous, so every call goes through a worker thread, the same way
FFmpeg and Kokoro do.
"""

from __future__ import annotations

from typing import Any

import anyio

from app.domain.errors import StorageFailed

from .base import StorageBackend


class S3Storage(StorageBackend):
    def __init__(
        self,
        *,
        bucket: str,
        endpoint_url: str,
        access_key: str,
        secret_key: str,
        region: str = "auto",
        public_base_url: str = "",
    ) -> None:
        self._bucket = bucket
        self._public_base_url = public_base_url.rstrip("/")
        self._client_kwargs: dict[str, Any] = {
            "endpoint_url": endpoint_url,
            "aws_access_key_id": access_key,
            "aws_secret_access_key": secret_key,
            "region_name": region,
        }
        self._client: Any | None = None

    def _get_client(self) -> Any:
        # Built lazily and reused: boto3 clients are expensive to construct and
        # safe to share across threads.
        if self._client is None:
            import boto3
            from botocore.config import Config

            self._client = boto3.client(
                "s3",
                config=Config(signature_version="s3v4", retries={"max_attempts": 3}),
                **self._client_kwargs,
            )
        return self._client

    # ---------- blocking bodies ----------

    def _put(self, key: str, data: bytes, content_type: str) -> None:
        self._get_client().put_object(
            Bucket=self._bucket, Key=key, Body=data, ContentType=content_type
        )

    def _get(self, key: str) -> bytes:
        response = self._get_client().get_object(Bucket=self._bucket, Key=key)
        return response["Body"].read()

    def _exists(self, key: str) -> bool:
        from botocore.exceptions import ClientError

        try:
            self._get_client().head_object(Bucket=self._bucket, Key=key)
        except ClientError as exc:
            status = exc.response.get("ResponseMetadata", {}).get("HTTPStatusCode")
            if status in (403, 404):
                return False
            raise
        return True

    def _delete(self, key: str) -> None:
        self._get_client().delete_object(Bucket=self._bucket, Key=key)

    # ---------- interface ----------

    async def put(self, key: str, data: bytes, content_type: str) -> None:
        try:
            await anyio.to_thread.run_sync(self._put, key, data, content_type)
        except Exception as exc:
            raise StorageFailed(f"Could not store audio: {type(exc).__name__}") from exc

    async def get(self, key: str) -> bytes:
        try:
            return await anyio.to_thread.run_sync(self._get, key)
        except Exception as exc:
            raise StorageFailed(f"Could not read audio: {type(exc).__name__}") from exc

    async def exists(self, key: str) -> bool:
        try:
            return await anyio.to_thread.run_sync(self._exists, key)
        except Exception:  # noqa: BLE001 - an unreachable store counts as a miss
            # The caller then re-renders, which is slower but still correct.
            return False

    async def delete(self, key: str) -> None:
        try:
            await anyio.to_thread.run_sync(self._delete, key)
        except Exception as exc:
            raise StorageFailed(
                f"Could not delete audio: {type(exc).__name__}"
            ) from exc

    def public_url(self, key: str) -> str:
        """Where a browser can fetch the object.

        With no public base configured the API serves the bytes itself, which
        keeps a private bucket private at the cost of proxying.
        """
        if self._public_base_url:
            return f"{self._public_base_url}/{key}"
        return f"/api/v1/audio-files/{key}"
