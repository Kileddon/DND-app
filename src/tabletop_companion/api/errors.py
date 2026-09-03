from __future__ import annotations

import logging
from typing import cast

from fastapi import FastAPI, Request
from fastapi.exceptions import RequestValidationError
from fastapi.responses import JSONResponse

from tabletop_companion.api.runtime import SafeErrorLog
from tabletop_companion.domain.errors import ApplicationError

logger = logging.getLogger(__name__)

STATUS_BY_CODE = {
    "validation_error": 422,
    "card_not_offered": 422,
    "incompatible_card": 422,
    "content_configuration_error": 422,
    "entity_not_found": 404,
    "permission_denied": 403,
    "state_conflict": 409,
    "draft_incomplete": 409,
    "item_equipped": 409,
    "idempotency_conflict": 409,
    "event_already_compensated": 409,
    "authentication_required": 401,
    "rate_limit_exceeded": 429,
    "unsupported_event_version": 422,
    "infrastructure_failure": 500,
}


def register_error_handlers(app: FastAPI, safe_errors: SafeErrorLog) -> None:
    async def handle_application_error(request: Request, error: Exception) -> JSONResponse:
        del request
        application_error = cast(ApplicationError, error)
        status = STATUS_BY_CODE.get(application_error.code, 500)
        if status >= 500:
            safe_errors.record(application_error.code)
            logger.error(
                "application_failure",
                extra={"error_code": application_error.code},
                exc_info=application_error,
            )
        return JSONResponse(
            status_code=status,
            content={
                "error": {
                    "code": application_error.code,
                    "message": application_error.message,
                    "details": application_error.details,
                }
            },
        )

    async def handle_request_validation(request: Request, error: Exception) -> JSONResponse:
        del request
        validation_error = cast(RequestValidationError, error)
        details = {
            "issues": [
                {
                    "location": [str(part) for part in issue["loc"]],
                    "message": issue["msg"],
                    "type": issue["type"],
                }
                for issue in validation_error.errors()
            ]
        }
        return JSONResponse(
            status_code=422,
            content={
                "error": {
                    "code": "validation_error",
                    "message": "Request validation failed.",
                    "details": details,
                }
            },
        )

    async def handle_unexpected_error(request: Request, error: Exception) -> JSONResponse:
        del request
        safe_errors.record("infrastructure_failure")
        logger.error(
            "unexpected_application_failure",
            exc_info=(type(error), error, error.__traceback__),
        )
        return JSONResponse(
            status_code=500,
            content={
                "error": {
                    "code": "infrastructure_failure",
                    "message": "The local host could not complete the request.",
                    "details": {},
                }
            },
        )

    app.add_exception_handler(ApplicationError, handle_application_error)
    app.add_exception_handler(RequestValidationError, handle_request_validation)
    app.add_exception_handler(Exception, handle_unexpected_error)
