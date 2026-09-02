from __future__ import annotations

from enum import StrEnum

from tabletop_companion.domain.errors import StateConflictError


class ReplayMode(StrEnum):
    INCREMENTAL = "incremental"
    SNAPSHOT = "snapshot"


def choose_replay_mode(
    *, last_cursor: int, minimum_cursor: int | None, maximum_cursor: int, replay_limit: int
) -> ReplayMode:
    if last_cursor < 0:
        raise StateConflictError("Event cursor cannot be negative.", code="invalid_cursor")
    if last_cursor > maximum_cursor:
        raise StateConflictError(
            "Client event cursor is ahead of the host.",
            code="cursor_ahead",
            details={"last_cursor": last_cursor, "host_cursor": maximum_cursor},
        )
    if last_cursor == 0 or minimum_cursor is None:
        return ReplayMode.SNAPSHOT
    if last_cursor < minimum_cursor - 1 or maximum_cursor - last_cursor > replay_limit:
        return ReplayMode.SNAPSHOT
    return ReplayMode.INCREMENTAL
