"""Identity providers.

Sign-in is delegated so no password is ever handled here. Both providers use
the OAuth 2.0 authorization-code flow; Google additionally returns an OpenID
Connect id_token, which Authlib verifies against Google's published keys.

Provider-specific knowledge stops at this module. Everything above it sees a
plain `OAuthProfile`.
"""

from __future__ import annotations

from dataclasses import dataclass

from authlib.integrations.starlette_client import OAuth, OAuthError
from starlette.requests import Request

from app.config import Settings
from app.domain.errors import AppError, ProviderUnavailable

GOOGLE = "google"
X = "x"


class AuthFailed(AppError):
    code = "AUTH_FAILED"
    http_status = 400
    default_message = "Sign-in did not complete."


@dataclass(frozen=True)
class OAuthProfile:
    """A person as an identity provider describes them."""

    provider: str
    account_id: str
    display_name: str
    email: str | None
    avatar_url: str | None


def build_oauth(settings: Settings) -> OAuth:
    oauth = OAuth()

    if settings.google_client_id and settings.google_client_secret:
        oauth.register(
            name=GOOGLE,
            client_id=settings.google_client_id,
            client_secret=settings.google_client_secret,
            server_metadata_url=(
                "https://accounts.google.com/.well-known/openid-configuration"
            ),
            client_kwargs={"scope": "openid email profile"},
        )

    if settings.x_client_id and settings.x_client_secret:
        oauth.register(
            name=X,
            client_id=settings.x_client_id,
            client_secret=settings.x_client_secret,
            authorize_url="https://x.com/i/oauth2/authorize",
            access_token_url="https://api.x.com/2/oauth2/token",
            api_base_url="https://api.x.com/2/",
            client_kwargs={
                # X requires PKCE, and does not release email at this tier.
                "scope": "tweet.read users.read offline.access",
                "code_challenge_method": "S256",
                "token_endpoint_auth_method": "client_secret_basic",
            },
        )

    return oauth


async def fetch_profile(oauth: OAuth, provider: str, request: Request) -> OAuthProfile:
    """Complete the handshake and normalize whatever the provider returned."""
    client = getattr(oauth, provider, None)
    if client is None:
        raise ProviderUnavailable(f"{provider} sign-in is not configured.")

    try:
        token = await client.authorize_access_token(request)
    except OAuthError as exc:
        # The provider's description can name the client id; keep it out.
        raise AuthFailed("The identity provider rejected the sign-in.") from exc

    if provider == GOOGLE:
        return _google_profile(token)
    if provider == X:
        return await _x_profile(client, token)
    raise ProviderUnavailable(f"Unsupported provider: {provider}")


def _google_profile(token: dict) -> OAuthProfile:
    # Authlib has already verified the id_token signature and claims.
    claims = token.get("userinfo") or {}
    account_id = claims.get("sub")
    if not account_id:
        raise AuthFailed("Google did not identify the account.")
    email = claims.get("email")
    return OAuthProfile(
        provider=GOOGLE,
        account_id=str(account_id),
        display_name=claims.get("name") or (email or "").split("@")[0] or "User",
        # An unverified address should not be treated as proof of anything.
        email=email if claims.get("email_verified") else None,
        avatar_url=claims.get("picture"),
    )


async def _x_profile(client, token: dict) -> OAuthProfile:
    response = await client.get(
        "users/me", params={"user.fields": "profile_image_url"}, token=token
    )
    if response.status_code >= 400:
        raise AuthFailed("X did not return the account.")
    data = (response.json() or {}).get("data") or {}
    account_id = data.get("id")
    if not account_id:
        raise AuthFailed("X did not identify the account.")
    return OAuthProfile(
        provider=X,
        account_id=str(account_id),
        display_name=data.get("name") or data.get("username") or "User",
        # X does not release email at this scope, so accounts have none.
        email=None,
        avatar_url=data.get("profile_image_url"),
    )
