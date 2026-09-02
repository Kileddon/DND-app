from __future__ import annotations

from collections.abc import Mapping
from typing import Any


class ApplicationError(Exception):
    """Base for errors that can be safely mapped at the transport boundary."""

    code = "application_error"

    def __init__(
        self,
        message: str,
        *,
        details: Mapping[str, Any] | None = None,
        code: str | None = None,
    ) -> None:
        super().__init__(message)
        self.message = message
        self.details = dict(details or {})
        if code is not None:
            self.code = code


class DomainValidationError(ApplicationError):
    code = "validation_error"


class EntityNotFoundError(ApplicationError):
    code = "entity_not_found"


class PermissionDeniedError(ApplicationError):
    code = "permission_denied"


class StateConflictError(ApplicationError):
    code = "state_conflict"


class IdempotencyConflictError(ApplicationError):
    code = "idempotency_conflict"


class ContentConfigurationError(ApplicationError):
    code = "content_configuration_error"


class InfrastructureError(ApplicationError):
    code = "infrastructure_failure"


class AuthenticationError(ApplicationError):
    code = "authentication_required"


class RateLimitError(ApplicationError):
    code = "rate_limit_exceeded"


class UnsupportedEventVersionError(ApplicationError):
    code = "unsupported_event_version"
