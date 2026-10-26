"""Error responses in the RFC 9457 "Problem Details" format (application/problem+json).

Every error the API returns has the same shape, so clients need one error handler.
"""

from http import HTTPStatus
from typing import Any

from fastapi import FastAPI, Request
from fastapi.exceptions import RequestValidationError
from fastapi.responses import JSONResponse
from pydantic import BaseModel
from starlette.exceptions import HTTPException

PROBLEM_JSON = "application/problem+json"


class FieldError(BaseModel):
    location: str
    message: str


class Problem(BaseModel):
    type: str = "about:blank"
    title: str
    status: int
    detail: str | None = None
    instance: str | None = None
    errors: list[FieldError] | None = None


def problem_response(
    request: Request, status: int, detail: str | None = None, **extra: Any
) -> JSONResponse:
    body = Problem(
        title=HTTPStatus(status).phrase,
        status=status,
        detail=detail,
        instance=request.url.path,
        **extra,
    )
    return JSONResponse(
        body.model_dump(exclude_none=True), status_code=status, media_type=PROBLEM_JSON
    )


async def _http_exception(request: Request, exc: Exception) -> JSONResponse:
    assert isinstance(exc, HTTPException)
    detail = exc.detail if exc.detail != HTTPStatus(exc.status_code).phrase else None
    response = problem_response(request, exc.status_code, detail)
    if exc.headers:
        response.headers.update(exc.headers)
    return response


async def _validation_error(request: Request, exc: Exception) -> JSONResponse:
    assert isinstance(exc, RequestValidationError)
    errors = [
        FieldError(location=".".join(str(part) for part in error["loc"]), message=error["msg"])
        for error in exc.errors()
    ]
    return problem_response(request, 422, "The request is invalid.", errors=errors)


def install_problem_handlers(app: FastAPI) -> None:
    app.add_exception_handler(HTTPException, _http_exception)
    app.add_exception_handler(RequestValidationError, _validation_error)


def problem_responses(*statuses: int) -> dict[int | str, dict[str, Any]]:
    """OpenAPI documentation for error responses, for use in route decorators."""
    return {
        status: {
            "model": Problem,
            "description": HTTPStatus(status).phrase,
            "content": {PROBLEM_JSON: {}},
        }
        for status in statuses
    }
