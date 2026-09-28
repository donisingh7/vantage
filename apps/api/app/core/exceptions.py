"""Domain errors that map to stable API error codes."""


class AppError(Exception):
    status_code = 400
    code = "bad_request"

    def __init__(self, message: str) -> None:
        super().__init__(message)
        self.message = message


class NotFoundError(AppError):
    status_code = 404
    code = "not_found"


class ConflictError(AppError):
    status_code = 409
    code = "conflict"


class ProviderError(AppError):
    """A configured real provider (LLM/embedding) failed. Message must never include credentials."""

    status_code = 502
    code = "provider_error"
