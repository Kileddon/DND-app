from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from typing import Any


@dataclass(frozen=True, slots=True)
class DomainEvent:
    id: str
    event_type: str
    aggregate_type: str
    aggregate_id: str
    room_id: str
    actor_id: str
    source_id: str | None
    target_ids: tuple[str, ...]
    payload: dict[str, Any]
    visibility: str
    schema_version: int
    command_id: str
    occurred_at: datetime
    cursor: int | None = None
    session_id: str | None = None
