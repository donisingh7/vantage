from fastapi import FastAPI, Request
from fastapi.exceptions import RequestValidationError
from fastapi.responses import JSONResponse
from starlette.exceptions import HTTPException as StarletteHTTPException

from app.core.exceptions import AppError


def error_response(request: Request, status_code: int, code: str, message: str) -> JSONResponse:
    request_id = getattr(request.state, "request_id", "unknown")
    return JSONResponse(
        status_code=status_code,
        content={"error": {"code": code, "message": message, "request_id": request_id}},
    )


def register_exception_handlers(app: FastAPI) -> None:
    @app.exception_handler(AppError)
    async def domain_error(request: Request, exc: AppError) -> JSONResponse:
        return error_response(request, exc.status_code, exc.code, exc.message)

    @app.exception_handler(RequestValidationError)
    async def validation_error(request: Request, exc: RequestValidationError) -> JSONResponse:
        return error_response(request, 422, "validation_error", _first_validation_message(exc))

    @app.exception_handler(StarletteHTTPException)
    async def http_error(request: Request, exc: StarletteHTTPException) -> JSONResponse:
        if exc.status_code == 404:
            code, message = "not_found", str(exc.detail)
        elif exc.status_code == 503:
            code, message = "service_unavailable", "Service is not ready"
        else:
            code = "http_error"
            message = str(exc.detail) if exc.status_code < 500 else "Request could not be completed"
        return error_response(request, exc.status_code, code, message)

    @app.exception_handler(Exception)
    async def unexpected_error(request: Request, exc: Exception) -> JSONResponse:
        return error_response(request, 500, "internal_error", "An internal error occurred")


def _first_validation_message(exc: RequestValidationError) -> str:
    for error in exc.errors():
        field = ".".join(str(part) for part in error.get("loc", ()) if part not in ("body", "query"))
        message = error.get("msg", "Invalid value")
        return f"{field}: {message}" if field else message
    return "Request validation failed"
