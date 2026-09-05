"""Storage backend selection and the S3 adapter's behaviour."""

from __future__ import annotations

import pytest

from app.api.deps import build_storage
from app.config import Settings
from app.domain.errors import StorageFailed
from app.infrastructure.storage.local_storage import LocalStorage
from app.infrastructure.storage.s3_storage import S3Storage


def _s3_settings(**overrides) -> Settings:
    base = dict(
        storage_backend="s3",
        s3_bucket="bucket",
        s3_endpoint_url="https://example.storage",
        s3_access_key_id="key",
        s3_secret_access_key="secret",
    )
    base.update(overrides)
    return Settings(**base)


class TestSelection:
    def test_local_is_the_default(self, tmp_path):
        storage = build_storage(Settings(local_storage_path=tmp_path))
        assert isinstance(storage, LocalStorage)

    def test_s3_is_selected_when_asked_for(self):
        assert isinstance(build_storage(_s3_settings()), S3Storage)

    @pytest.mark.parametrize(
        "missing",
        ["s3_bucket", "s3_endpoint_url", "s3_access_key_id", "s3_secret_access_key"],
    )
    def test_incomplete_s3_configuration_fails_loudly(self, missing):
        # Quietly falling back to disk would look like it worked and then lose
        # every render when the container restarts.
        with pytest.raises(RuntimeError) as caught:
            build_storage(_s3_settings(**{missing: ""}))
        assert missing.upper() in str(caught.value)


class TestPublicUrl:
    def test_proxies_through_the_api_when_the_bucket_is_private(self):
        storage = build_storage(_s3_settings())
        assert storage.public_url("audio/x.mp3") == "/api/v1/audio-files/audio/x.mp3"

    def test_points_straight_at_the_bucket_when_it_is_public(self):
        storage = build_storage(_s3_settings(s3_public_base_url="https://cdn.test/"))
        assert storage.public_url("audio/x.mp3") == "https://cdn.test/audio/x.mp3"


class _FakeClient:
    """Stands in for boto3 so the adapter can be exercised without a network."""

    def __init__(self) -> None:
        self.objects: dict[str, bytes] = {}
        self.content_types: dict[str, str] = {}

    def put_object(self, Bucket, Key, Body, ContentType):
        self.objects[Key] = Body
        self.content_types[Key] = ContentType

    def get_object(self, Bucket, Key):
        if Key not in self.objects:
            raise KeyError(Key)

        class _Body:
            def __init__(self, data):
                self._data = data

            def read(self):
                return self._data

        return {"Body": _Body(self.objects[Key])}

    def head_object(self, Bucket, Key):
        from botocore.exceptions import ClientError

        if Key not in self.objects:
            raise ClientError(
                {"ResponseMetadata": {"HTTPStatusCode": 404}}, "HeadObject"
            )

    def delete_object(self, Bucket, Key):
        self.objects.pop(Key, None)


@pytest.fixture
def s3(monkeypatch) -> S3Storage:
    storage = S3Storage(
        bucket="bucket",
        endpoint_url="https://example.storage",
        access_key="key",
        secret_key="secret",
    )
    client = _FakeClient()
    monkeypatch.setattr(storage, "_get_client", lambda: client)
    return storage


class TestS3Adapter:
    async def test_round_trip(self, s3):
        await s3.put("audio/a.mp3", b"AUDIO", "audio/mpeg")
        assert await s3.get("audio/a.mp3") == b"AUDIO"
        assert await s3.exists("audio/a.mp3") is True

    async def test_missing_object_is_not_present(self, s3):
        assert await s3.exists("audio/nope.mp3") is False

    async def test_reading_a_missing_object_is_a_normalized_error(self, s3):
        with pytest.raises(StorageFailed):
            await s3.get("audio/nope.mp3")

    async def test_delete_is_idempotent(self, s3):
        await s3.put("audio/a.mp3", b"AUDIO", "audio/mpeg")
        await s3.delete("audio/a.mp3")
        await s3.delete("audio/a.mp3")
        assert await s3.exists("audio/a.mp3") is False

    async def test_an_unreachable_store_reads_as_a_miss(self, monkeypatch, s3):
        def boom():
            raise ConnectionError("network down")

        monkeypatch.setattr(s3, "_get_client", boom)
        # The caller then re-renders rather than serving a broken URL.
        assert await s3.exists("audio/a.mp3") is False

    async def test_errors_do_not_leak_credentials(self, monkeypatch, s3):
        def boom():
            raise RuntimeError("failed using secret_key=SUPERSECRET")

        monkeypatch.setattr(s3, "_get_client", boom)
        with pytest.raises(StorageFailed) as caught:
            await s3.put("audio/a.mp3", b"x", "audio/mpeg")
        assert "SUPERSECRET" not in str(caught.value)
