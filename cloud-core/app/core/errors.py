"""
Consistent API error envelope.

Every error response (validation, HTTP exceptions, unhandled) is shaped
the same way, per the API design principles in section 51 ("consistent
errors"). Registered on the FastAPI app in `app.main`.

Shape:
{
  "error": {"code": "NOT_FOUND", "message": "..."},
  "request_id": "..."
}
"""

import logging

from fastapi import FastAPI, HTTPException, Request, status
from fastapi.encoders import jsonable_encoder
from fastapi.exceptions import RequestValidationError
from fastapi.responses import JSONResponse

logger = logging.getLogger("app.errors")

_STATUS_CODE_TO_ERROR_CODE = {
    status.HTTP_400_BAD_REQUEST: "BAD_REQUEST",
    status.HTTP_401_UNAUTHORIZED: "UNAUTHORIZED",
    status.HTTP_403_FORBIDDEN: "FORBIDDEN",
    status.HTTP_404_NOT_FOUND: "NOT_FOUND",
    status.HTTP_409_CONFLICT: "CONFLICT",
    status.HTTP_422_UNPROCESSABLE_ENTITY: "VALIDATION_ERROR",
    status.HTTP_429_TOO_MANY_REQUESTS: "RATE_LIMITED",
}


def _request_id(request: Request) -> str:
    return getattr(request.state, "request_id", "-")


def _envelope(code: str, message: str, request: Request) -> dict:
    return {"error": {"code": code, "message": message}, "request_id": _request_id(request)}


def register_exception_handlers(app: FastAPI) -> None:
    @app.exception_handler(HTTPException)
    async def http_exception_handler(request: Request, exc: HTTPException) -> JSONResponse:
        code = _STATUS_CODE_TO_ERROR_CODE.get(exc.status_code, "HTTP_ERROR")
        detail = exc.detail
        # A structured detail {"code", "message"} (ADR-137) keeps the envelope's shape and adds a stable,
        # machine-readable `reason` the clients branch on. A plain string detail is unchanged.
        if isinstance(detail, dict) and isinstance(detail.get("code"), str) and "message" in detail:
            content = _envelope(code, str(detail["message"]), request)
            content["error"]["reason"] = detail["code"]
        else:
            content = _envelope(code, str(detail), request)
        return JSONResponse(status_code=exc.status_code, content=content, headers=exc.headers)

    @app.exception_handler(RequestValidationError)
    async def validation_exception_handler(
        request: Request, exc: RequestValidationError
    ) -> JSONResponse:
        # exc.errors() can contain non-JSON-serializable objects (e.g. the
        # raw ValueError instance Pydantic puts in error["ctx"]["error"]
        # when a @model_validator raises ValueError) — jsonable_encoder
        # converts those to strings instead of crashing json.dumps.
        return JSONResponse(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            content=_envelope("VALIDATION_ERROR", "Request validation failed", request)
            | {"details": jsonable_encoder(exc.errors())},
        )

    @app.exception_handler(Exception)
    async def unhandled_exception_handler(request: Request, exc: Exception) -> JSONResponse:
        logger.exception(
            "Unhandled exception on %s %s", request.method, request.url.path,
            extra={"request_id": _request_id(request)},
        )
        return JSONResponse(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            content=_envelope("INTERNAL_ERROR", "An unexpected error occurred", request),
        )
