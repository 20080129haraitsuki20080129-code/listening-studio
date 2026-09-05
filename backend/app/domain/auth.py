"""Session tokens.

Sign-in is delegated to an identity provider, so nothing secret about the
person is stored here. A session is a short signed statement that a given user
id was authenticated, carried in an httpOnly cookie the browser cannot read.
"""

from __future__ import annotations

import uuid
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta

import jwt

from app.domain.errors import AppError

_ALGORITHM = "HS256"


class NotAuthenticated(AppError):
    code = "NOT_AUTHENTICATED"
    http_status = 401
    default_message = "Sign in to continue."


class Forbidden(AppError):
    code = "FORBIDDEN"
    http_status = 403
    default_message = "This does not belong to you."


@dataclass(frozen=True)
class SessionToken:
    user_id: uuid.UUID
    expires_at: datetime


def issue_session(user_id: uuid.UUID, secret: str, max_age_seconds: int) -> str:
    expires_at = datetime.now(UTC) + timedelta(seconds=max_age_seconds)
    return jwt.encode(
        {"sub": str(user_id), "exp": expires_at},
        secret,
        algorithm=_ALGORITHM,
    )


def read_session(token: str, secret: str) -> SessionToken:
    """Decode a session cookie, rejecting anything tampered with or expired."""
    try:
        payload = jwt.decode(token, secret, algorithms=[_ALGORITHM])
        user_id = uuid.UUID(payload["sub"])
        expires_at = datetime.fromtimestamp(payload["exp"], tz=UTC)
    except (jwt.PyJWTError, KeyError, ValueError) as exc:
        raise NotAuthenticated("Your session is no longer valid.") from exc
    return SessionToken(user_id=user_id, expires_at=expires_at)
