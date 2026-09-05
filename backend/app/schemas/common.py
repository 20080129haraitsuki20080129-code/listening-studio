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
