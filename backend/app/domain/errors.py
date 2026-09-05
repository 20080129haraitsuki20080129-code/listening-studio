"""Normalized application errors (SPEC section 21).

Provider failures are mapped into these before leaving the adapter layer, so
neither the API nor the UI ever sees a provider-specific exception -- and
provider secrets never reach a response body.
"""

from __future__ import annotations

from http import HTTPStatus


class AppError(Exception):
    code: str = "INTERNAL_ERROR"
    http_status: int = HTTPStatus.INTERNAL_SERVER_ERROR
    retryable: bool = False
    default_message: str = "An unexpected error occurred."

    def __init__(self, message: str | None = None) -> None:
        self.message = message or self.default_message
        super().__init__(self.message)


class InvalidScript(AppError):
    code = "INVALID_SCRIPT"
    http_status = HTTPStatus.UNPROCESSABLE_ENTITY
    default_message = "The script could not be parsed."


class NotFound(AppError):
    """Generic 404 for project/segment/speaker/render lookups."""

    code = "NOT_FOUND"
    http_status = HTTPStatus.NOT_FOUND
    default_message = "The requested resource does not exist."


class VoiceNotFound(AppError):
    code = "VOICE_NOT_FOUND"
    http_status = HTTPStatus.NOT_FOUND
    default_message = "The selected voice does not exist."


class VoiceDisabled(AppError):
    code = "VOICE_DISABLED"
    http_status = HTTPStatus.CONFLICT
    default_message = "The selected voice is disabled."


class UnsupportedProvider(AppError):
    code = "PROVIDER_UNAVAILABLE"
    http_status = HTTPStatus.SERVICE_UNAVAILABLE
    default_message = "The requested speech provider is not available."

    def __init__(self, provider: str | None = None) -> None:
        super().__init__(
            f"Speech provider '{provider}' is not configured." if provider else None
        )


class ProviderUnavailable(AppError):
    code = "PROVIDER_UNAVAILABLE"
    http_status = HTTPStatus.SERVICE_UNAVAILABLE
    retryable = True
    default_message = "The speech provider is temporarily unavailable."


class ProviderRateLimited(AppError):
    code = "PROVIDER_RATE_LIMITED"
    http_status = HTTPStatus.TOO_MANY_REQUESTS
    retryable = True
    default_message = "Speech generation is temporarily rate limited."


class ProviderAuthFailed(AppError):
    code = "PROVIDER_AUTH_FAILED"
    http_status = HTTPStatus.BAD_GATEWAY
    default_message = "The speech provider rejected the credentials."


class ProviderRequestFailed(AppError):
    code = "PROVIDER_REQUEST_FAILED"
    http_status = HTTPStatus.BAD_GATEWAY
    retryable = True
    default_message = "The speech provider failed to process the request."


class AudioProcessingFailed(AppError):
    code = "AUDIO_PROCESSING_FAILED"
    http_status = HTTPStatus.INTERNAL_SERVER_ERROR
    default_message = "Audio processing failed."


class StorageFailed(AppError):
    code = "STORAGE_FAILED"
    http_status = HTTPStatus.INTERNAL_SERVER_ERROR
    default_message = "Storing the generated audio failed."


class RenderCancelled(AppError):
    code = "RENDER_CANCELLED"
    http_status = HTTPStatus.CONFLICT
    default_message = "The render was cancelled."
