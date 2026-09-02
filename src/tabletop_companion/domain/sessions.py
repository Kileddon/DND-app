from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from enum import StrEnum

from tabletop_companion.domain.errors import StateConflictError


class SessionStatus(StrEnum):
    PREPARATION = "PREPARATION"
    LOBBY = "LOBBY"
    ACTIVE = "ACTIVE"
    PAUSED = "PAUSED"
    COMPLETED = "COMPLETED"


@dataclass(slots=True)
class GameSession:
    id: str
    room_id: str
    status: SessionStatus
    version: int
    created_at: datetime
    updated_at: datetime
    started_at: datetime | None = None
    paused_at: datetime | None = None
    completed_at: datetime | None = None

    def transition(
        self,
        target: SessionStatus,
        *,
        expected_version: int,
        now: datetime,
    ) -> None:
        if expected_version != self.version:
            raise StateConflictError(
                "Session version is stale.",
                details={"expected_version": expected_version, "current_version": self.version},
            )
        allowed = {
            SessionStatus.PREPARATION: {SessionStatus.LOBBY},
            SessionStatus.LOBBY: {SessionStatus.ACTIVE},
            SessionStatus.ACTIVE: {SessionStatus.PAUSED, SessionStatus.COMPLETED},
            SessionStatus.PAUSED: {SessionStatus.ACTIVE, SessionStatus.COMPLETED},
            SessionStatus.COMPLETED: set(),
        }
        if target not in allowed[self.status]:
            raise StateConflictError(
                f"Session cannot transition from {self.status.value} to {target.value}.",
                code="invalid_session_transition",
                details={"current_status": self.status.value, "target_status": target.value},
            )
        self.status = target
        self.version += 1
        self.updated_at = now
        if target is SessionStatus.ACTIVE:
            if self.started_at is None:
                self.started_at = now
            self.paused_at = None
        elif target is SessionStatus.PAUSED:
            self.paused_at = now
        elif target is SessionStatus.COMPLETED:
            self.completed_at = now
