"""Turning an identity-provider profile into a user of this app."""

from __future__ import annotations

import uuid
from datetime import UTC, datetime

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.domain.auth import NotAuthenticated
from app.infrastructure.auth.oauth import OAuthProfile
from app.infrastructure.db.models import User


class AuthService:
    async def upsert_from_profile(
        self, session: AsyncSession, profile: OAuthProfile
    ) -> User:
        """Find or create the account behind a provider profile.

        Accounts are keyed on (provider, account id), never on email. Emails
        change hands and X does not supply one, so matching on it would let
        two different people end up sharing an account.
        """
        user = (
            await session.execute(
                select(User).where(
                    User.auth_provider == profile.provider,
                    User.provider_account_id == profile.account_id,
                )
            )
        ).scalar_one_or_none()

        if user is None:
            user = User(
                auth_provider=profile.provider,
                provider_account_id=profile.account_id,
                email=profile.email,
                display_name=profile.display_name,
                avatar_url=profile.avatar_url,
            )
            session.add(user)
        else:
            # Keep the profile fresh; people rename themselves.
            user.display_name = profile.display_name
            user.avatar_url = profile.avatar_url
            if profile.email:
                user.email = profile.email
            user.last_seen_at = datetime.now(UTC)

        await session.flush()
        return user

    async def require_user(self, session: AsyncSession, user_id: uuid.UUID) -> User:
        user = await session.get(User, user_id)
        if user is None:
            # The session was signed for an account that no longer exists.
            raise NotAuthenticated("Your account is no longer available.")
        return user
