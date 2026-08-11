"""Error model shared by every route.

Handlers produce `{"detail": {"code": ..., "message": ...}}` so frontends can
map codes to translated messages instead of parsing prose.
"""

from fastapi import FastAPI, Request
from fastapi.responses import JSONResponse

CODES = {
    "VALIDATION": 422,
    "UNAUTHORIZED": 401,
    "FORBIDDEN": 403,
    "NOT_FOUND": 404,
    "CONFLICT": 409,
    "RATE_LIMITED": 429,
}


class AppError(Exception):
    def __init__(self, code: str, message: str, status: int | None = None):
        self.code = code
        self.message = message
        self.status = status or CODES.get(code, 500)


def install_error_handlers(app: FastAPI) -> None:
    @app.exception_handler(AppError)
    async def app_error_handler(_: Request, exc: AppError) -> JSONResponse:
        return JSONResponse(status_code=exc.status, content={"detail": {"code": exc.code,
    "message": exc.message}})

    @app.exception_handler(ValueError)
    async def value_error_handler(_: Request, exc: ValueError) -> JSONResponse:
        return JSONResponse(status_code=400, content={"detail": {"code": "VALIDATION",
    "message": str(exc)}})
