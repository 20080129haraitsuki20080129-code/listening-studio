"""Sign-in and project ownership.

The point of these is the negative cases: before this existed, an unauthenticated
GET /projects returned every project in the database and anyone could delete any
of them.
"""

from __future__ import annotations

import uuid

import pytest

from app.domain.auth import (
    Forbidden,
    NotAuthenticated,
    issue_session,
    read_session,
)
from app.infrastructure.auth.oauth import OAuthProfile
from app.infrastructure.db.models import User

SECRET = "a" * 40


class TestSessionToken:
    def test_round_trip(self):
        user_id = uuid.uuid4()
        token = issue_session(user_id, SECRET, 3600)
        assert read_session(token, SECRET).user_id == user_id

    def test_a_token_signed_with_another_key_is_rejected(self):
        token = issue_session(uuid.uuid4(), SECRET, 3600)
        with pytest.raises(NotAuthenticated):
            read_session(token, "b" * 40)

    def test_an_expired_token_is_rejected(self):
        token = issue_session(uuid.uuid4(), SECRET, -1)
        with pytest.raises(NotAuthenticated):
            read_session(token, SECRET)

    @pytest.mark.parametrize("value", ["", "garbage", "a.b.c"])
    def test_nonsense_is_rejected(self, value):
        with pytest.raises(NotAuthenticated):
            read_session(value, SECRET)


class TestUpsertFromProfile:
    async def _service(self):
        from app.application.auth_service import AuthService

        return AuthService()

    def _profile(self, **overrides) -> OAuthProfile:
        base = dict(
            provider="google",
            account_id="12345",
            display_name="Itsuki",
            email="itsuki@example.com",
            avatar_url=None,
        )
        base.update(overrides)
        return OAuthProfile(**base)

    async def test_creates_an_account_on_first_sign_in(self, session):
        service = await self._service()
        user = await service.upsert_from_profile(session, self._profile())
        assert user.id is not None
        assert user.auth_provider == "google"

    async def test_signing_in_again_reuses_the_account(self, session):
        service = await self._service()
        first = await service.upsert_from_profile(session, self._profile())
        second = await service.upsert_from_profile(
            session, self._profile(display_name="Itsuki H.")
        )
        assert first.id == second.id
        # A rename should follow through.
        assert second.display_name == "Itsuki H."

    async def test_the_same_email_on_a_different_provider_is_a_different_person(
        self, session
    ):
        """Matching on email would let an X account inherit a Google account."""
        service = await self._service()
        google = await service.upsert_from_profile(session, self._profile())
        x_user = await service.upsert_from_profile(
            session,
            self._profile(provider="x", account_id="999", email=None),
        )
        assert google.id != x_user.id

    async def test_an_unverified_google_email_is_not_stored(self, session):
        service = await self._service()
        user = await service.upsert_from_profile(
            session, self._profile(email=None)
        )
        assert user.email is None


async def _make_user(session, suffix: str = "1") -> User:
    user = User(
        auth_provider="google",
        provider_account_id=f"acct-{suffix}",
        email=f"user{suffix}@example.com",
        display_name=f"User {suffix}",
    )
    session.add(user)
    await session.flush()
    return user


class TestOwnership:
    """Ownership is enforced in the service, so every route inherits it."""

    async def _service(self):
        from app.application.project_service import ProjectService

        return ProjectService()

    async def _project(self, session, owner, title="theirs"):
        from app.schemas.project import ProjectCreate

        service = await self._service()
        return await service.create(
            session,
            ProjectCreate(title=title, mode="monologue", source_text="Hello."),
            owner.id,
        )

    async def test_a_project_is_stamped_with_its_owner(self, session):
        owner = await _make_user(session, "a")
        project = await self._project(session, owner)
        assert project.user_id == owner.id

    async def test_listing_shows_only_your_own(self, session):
        alice = await _make_user(session, "alice")
        bob = await _make_user(session, "bob")
        await self._project(session, alice, "alice's")
        await self._project(session, bob, "bob's")

        service = await self._service()
        titles = [p.title for p in await service.list_all(session, alice.id)]
        assert titles == ["alice's"]

    async def test_opening_someone_elses_project_is_refused(self, session):
        alice = await _make_user(session, "alice2")
        bob = await _make_user(session, "bob2")
        theirs = await self._project(session, alice)

        service = await self._service()
        with pytest.raises(Forbidden):
            await service.get(session, theirs.id, bob.id)

    async def test_deleting_someone_elses_project_is_refused(self, session):
        alice = await _make_user(session, "alice3")
        bob = await _make_user(session, "bob3")
        theirs = await self._project(session, alice)

        service = await self._service()
        with pytest.raises(Forbidden):
            await service.soft_delete(session, theirs.id, bob.id)

    async def test_a_segment_id_is_not_a_way_round_ownership(self, session):
        from app.domain.parsing import parse_script

        alice = await _make_user(session, "alice4")
        bob = await _make_user(session, "bob4")
        project = await self._project(session, alice)

        service = await self._service()
        parsed = parse_script("One sentence. Two sentences.", "monologue")
        await service.apply_parse(session, project, parsed)
        segment = project.segments[0]

        with pytest.raises(Forbidden):
            await service.get_segment(session, segment.id, bob.id)

    async def test_legacy_projects_without_an_owner_are_unreachable(self, session):
        """Projects made before sign-in existed must not fall to whoever asks."""
        from app.schemas.project import ProjectCreate

        service = await self._service()
        orphan = await service.create(
            session,
            ProjectCreate(title="legacy", mode="monologue", source_text="Hi."),
            None,
        )
        somebody = await _make_user(session, "later")
        with pytest.raises(Forbidden):
            await service.get(session, orphan.id, somebody.id)
        assert orphan.title not in [
            p.title for p in await service.list_all(session, somebody.id)
        ]

    async def test_without_sign_in_configured_everything_is_reachable(self, session):
        """A local checkout with no provider configured must still work."""
        alice = await _make_user(session, "alice5")
        theirs = await self._project(session, alice)

        service = await self._service()
        found = await service.get(session, theirs.id, None)
        assert found.id == theirs.id


class TestApiEnforcement:
    """The same rules seen through HTTP, including the unauthenticated case."""

    async def test_auth_status_reports_no_providers_when_unconfigured(self, client):
        body = (await client.get("/auth/status")).json()
        # A checkout with no provider configured cannot require sign-in --
        # there would be no way in.
        assert body["auth_required"] is False
        assert body["providers"] == []
        assert body["authenticated"] is False

    async def test_login_with_an_unconfigured_provider_is_refused(self, client):
        response = await client.get("/auth/google/login")
        assert response.status_code == 503
        assert response.json()["error"]["code"] == "PROVIDER_UNAVAILABLE"

    async def test_logout_clears_the_cookie(self, client):
        response = await client.post("/auth/logout")
        assert response.status_code == 204
        assert "listening_session" in response.headers.get("set-cookie", "")

    async def test_projects_are_scoped_once_sign_in_is_on(self, client, session):
        """With auth on, one person's list must not include another's."""
        from app.api import deps
        from app.domain.auth import issue_session

        alice = await _make_user(session, "http-alice")
        bob = await _make_user(session, "http-bob")
        await session.commit()

        container = deps.get_container()
        original = container.settings
        # A configured provider is what switches enforcement on.
        container.settings = original.model_copy(
            update={
                "google_client_id": "id",
                "google_client_secret": "secret",
                "session_secret": SECRET,
            }
        )
        try:
            cookie_name = container.settings.session_cookie_name
            alice_cookie = {
                cookie_name: issue_session(alice.id, SECRET, 3600)
            }
            bob_cookie = {cookie_name: issue_session(bob.id, SECRET, 3600)}

            # Anonymous access is refused outright.
            assert (await client.get("/projects")).status_code == 401

            created = await client.post(
                "/projects",
                json={"title": "alice's", "mode": "monologue"},
                cookies=alice_cookie,
            )
            assert created.status_code == 201
            project_id = created.json()["id"]

            mine = (await client.get("/projects", cookies=alice_cookie)).json()
            assert [p["title"] for p in mine] == ["alice's"]

            # Bob sees nothing, cannot open it, and cannot delete it.
            assert (await client.get("/projects", cookies=bob_cookie)).json() == []
            assert (
                await client.get(f"/projects/{project_id}", cookies=bob_cookie)
            ).status_code == 403
            assert (
                await client.delete(f"/projects/{project_id}", cookies=bob_cookie)
            ).status_code == 403

            # And it is still there afterwards.
            assert (
                await client.get(f"/projects/{project_id}", cookies=alice_cookie)
            ).status_code == 200
        finally:
            container.settings = original

    async def test_a_forged_cookie_is_rejected(self, client, session):
        from app.api import deps
        from app.domain.auth import issue_session

        alice = await _make_user(session, "forge")
        await session.commit()

        container = deps.get_container()
        original = container.settings
        container.settings = original.model_copy(
            update={
                "google_client_id": "id",
                "google_client_secret": "secret",
                "session_secret": SECRET,
            }
        )
        try:
            forged = issue_session(alice.id, "some-other-signing-key-entirely", 3600)
            response = await client.get(
                "/projects",
                cookies={container.settings.session_cookie_name: forged},
            )
            assert response.status_code == 401
        finally:
            container.settings = original
