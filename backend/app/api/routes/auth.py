from __future__ import annotations

from fastapi import APIRouter, Depends, Request, Response
from fastapi.responses import RedirectResponse
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.deps import Container, get_container, get_current_user
from app.domain.auth import issue_session
from app.domain.errors import ProviderUnavailable
from app.infrastructure.auth.oauth import fetch_profile
from app.infrastructure.db.models import User
from app.infrastructure.db.session import get_session
from app.schemas.common import AuthStatusOut, CurrentUserOut

router = APIRouter(tags=["auth"])


def _to_out(user: User) -> CurrentUserOut:
    return CurrentUserOut(
        id=str(user.id),
        display_name=user.display_name,
        email=user.email,
        avatar_url=user.avatar_url,
        auth_provider=user.auth_provider,
    )


@router.get("/auth/status", response_model=AuthStatusOut)
async def auth_status(
    user: User | None = Depends(get_current_user),
    container: Container = Depends(get_container),
) -> AuthStatusOut:
    """Everything the UI needs to choose between sign-in and the studio."""
    return AuthStatusOut(
        authenticated=user is not None,
        auth_required=container.settings.auth_required,
        providers=container.settings.enabled_oauth_providers,
        user=_to_out(user) if user else None,
    )


@router.get("/auth/{provider}/login")
async def begin_login(
    provider: str,
    request: Request,
    container: Container = Depends(get_container),
):
    """Hand the browser off to the identity provider."""
    if provider not in container.settings.enabled_oauth_providers:
        raise ProviderUnavailable(f"{provider} sign-in is not configured.")
    client = getattr(container.oauth, provider)
    redirect_uri = str(request.url_for("finish_login", provider=provider))
    return await client.authorize_redirect(request, redirect_uri)


@router.get("/auth/{provider}/callback", name="finish_login")
async def finish_login(
    provider: str,
    request: Request,
    session: AsyncSession = Depends(get_session),
    container: Container = Depends(get_container),
):
    """Complete the handshake, then send the browser back to the app."""
    settings = container.settings
    if provider not in settings.enabled_oauth_providers:
        raise ProviderUnavailable(f"{provider} sign-in is not configured.")

    profile = await fetch_profile(container.oauth, provider, request)
    user = await container.auth.upsert_from_profile(session, profile)
    await session.commit()

    token = issue_session(
        user.id, settings.session_secret, settings.session_max_age_seconds
    )
    response = RedirectResponse(url=settings.frontend_base_url, status_code=303)
    response.set_cookie(
        settings.session_cookie_name,
        token,
        max_age=settings.session_max_age_seconds,
        # The browser must never expose this to page scripts.
        httponly=True,
        secure=settings.cookie_secure,
        samesite=settings.cookie_samesite,
        path="/",
    )
    return response


@router.post("/auth/logout", status_code=204)
async def logout(container: Container = Depends(get_container)) -> Response:
    settings = container.settings
    response = Response(status_code=204)
    response.delete_cookie(
        settings.session_cookie_name,
        path="/",
        httponly=True,
        secure=settings.cookie_secure,
        samesite=settings.cookie_samesite,
    )
    return response
