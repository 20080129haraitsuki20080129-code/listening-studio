from __future__ import annotations

from pydantic import BaseModel, ConfigDict


class ApiModel(BaseModel):
    model_config = ConfigDict(from_attributes=True)


class ErrorBody(BaseModel):
    code: str
    message: str
    retryable: bool
    request_id: str | None = None


class ErrorResponse(BaseModel):
    error: ErrorBody


class CurrentUserOut(ApiModel):
    id: str
    display_name: str
    email: str | None = None
    avatar_url: str | None = None
    auth_provider: str


class AuthStatusOut(ApiModel):
    """What the UI needs to decide between a sign-in screen and the studio."""

    authenticated: bool
    auth_required: bool
    providers: list[str]
    user: CurrentUserOut | None = None
