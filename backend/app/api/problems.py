"""How a refusal reaches the wire — and how every error body stays readable.

Three things live here, all of them about the shape of a failed response and
none of them about why it failed:

- **`ProblemHTTPException`** carries a `ReadProblem` out of a route. Its body
  is FastAPI's usual `{"detail": ...}` — the problem's message, so every
  existing caller reads it as before — with the whole problem beside it under
  `problem`, which is what the upload screen lays out as a guide.
- **The validation handler** rewrites FastAPI's list-of-locations `422` into a
  sentence. A person who posts the upload form without a ledger should read
  "The ledger is missing", not `[{"loc": ["body", "ledger"], ...}]`.
- **The last-resort handler** answers an unhandled exception with a JSON body
  a screen can show, instead of a bare `Internal Server Error` text. The
  traceback goes to the log, where it belongs; the person gets a sentence.

Registered from `main.py`, which is wiring and nothing else.
"""

from __future__ import annotations

import logging
from typing import Any

from fastapi import HTTPException, Request, status
from fastapi.exceptions import RequestValidationError
from fastapi.responses import JSONResponse

from app.shared.problems import ReadProblemError, http_status_for
from app.shared.schemas import ReadProblem

__all__ = [
    "ProblemHTTPException",
    "handle_problem",
    "handle_unexpected",
    "handle_validation",
    "problem_response",
    "raise_for",
]

logger = logging.getLogger(__name__)

#: What the person reads when the server itself broke. The reason is in the
#: log; repeating a traceback to the browser would help nobody and could leak.
UNEXPECTED_MESSAGE = (
    "Something went wrong on the server and the action was not completed. "
    "Nothing half-done was saved. Try again; if it keeps happening, tell your "
    "administrator what you were doing and when, so they can find it in the log."
)


class ProblemHTTPException(HTTPException):
    """An `HTTPException` whose body also carries the structured problem."""

    def __init__(self, problem: ReadProblem, status_code: int | None = None) -> None:
        super().__init__(
            status_code=status_code or http_status_for(problem), detail=problem.message
        )
        self.problem = problem


def raise_for(error: ReadProblemError, status_code: int | None = None) -> ProblemHTTPException:
    """The HTTP exception for a reader's refusal, ready to `raise ... from`."""
    return ProblemHTTPException(error.problem, status_code)


def problem_response(problem: ReadProblem, status_code: int | None = None) -> JSONResponse:
    return JSONResponse(
        status_code=status_code or http_status_for(problem),
        content={"detail": problem.message, "problem": problem.model_dump(mode="json")},
    )


async def handle_problem(_request: Request, exc: ProblemHTTPException) -> JSONResponse:
    response = problem_response(exc.problem, exc.status_code)
    if exc.headers:
        response.headers.update(exc.headers)
    return response


#: Where a request field lives, in words.
_LOCATIONS = {
    "body": "in the request body",
    "query": "in the query string",
    "path": "in the path",
    "header": "in the headers",
}

#: Plain words for the pydantic error types a client is likely to trip.
_MESSAGES = {
    "missing": "is missing",
    "string_too_short": "is too short",
    "string_too_long": "is too long",
    "too_short": "has too few entries",
    "too_long": "has too many entries",
    "json_invalid": "is not valid JSON",
    "enum": "is not one of the allowed values",
    "literal_error": "is not one of the allowed values",
    "int_parsing": "must be a whole number",
    "float_parsing": "must be a number",
    "bool_parsing": "must be true or false",
    "date_from_datetime_parsing": "must be a date",
    "date_parsing": "must be a date (YYYY-MM-DD)",
    "datetime_parsing": "must be a date and time",
    "extra_forbidden": "is not a field this request accepts",
    "value_error": "is not valid",
}


def _describe(error: dict[str, Any]) -> str:
    location = [str(part) for part in error.get("loc", ())]
    where = _LOCATIONS.get(location[0], "") if location else ""
    field = ".".join(part for part in location[1:] if part != "__root__") or (
        location[0] if location else "the request"
    )
    kind = str(error.get("type", ""))
    # A validator's own sentence is the best description there is; the table
    # above is for pydantic's generic types only.
    said = None if kind == "value_error" else _MESSAGES.get(kind)
    if said is None:
        # Pydantic's own message, trimmed of its "Value error, " prefix.
        said = str(error.get("msg", "is not valid")).removeprefix("Value error, ")
        said = said[:1].lower() + said[1:] if said else "is not valid"
    return f"{field} {said}{f' ({where})' if where else ''}"


async def handle_validation(_request: Request, exc: RequestValidationError) -> JSONResponse:
    """A `422` a person can act on, with FastAPI's list kept for developers."""
    errors = [dict(error) for error in exc.errors()]
    for error in errors:
        error.pop("ctx", None)  # may hold an exception object, which is not JSON
        error.pop("url", None)
    described = [_describe(error) for error in errors]
    if len(described) == 1:
        detail = f"The request could not be accepted: {described[0]}."
    else:
        detail = (
            "The request could not be accepted: "
            + "; ".join(described[:-1])
            + f"; and {described[-1]}."
        )
    return JSONResponse(
        status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
        content={"detail": detail, "errors": errors},
    )


async def handle_unexpected(request: Request, exc: Exception) -> JSONResponse:
    """The last resort: a readable body, and the traceback in the log."""
    logger.exception(
        "Unhandled error on %s %s: %s", request.method, request.url.path, exc
    )
    return JSONResponse(
        status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
        content={"detail": UNEXPECTED_MESSAGE},
    )
