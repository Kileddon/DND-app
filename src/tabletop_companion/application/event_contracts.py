from __future__ import annotations

from datetime import datetime
from typing import Any

from tabletop_companion.domain.errors import (
    DomainValidationError,
    UnsupportedEventVersionError,
)
from tabletop_companion.domain.events import DomainEvent

EVENT_SCHEMA_VERSION = 1


def serialize_event(event: DomainEvent) -> dict[str, Any]:
    if event.schema_version != EVENT_SCHEMA_VERSION:
        raise UnsupportedEventVersionError(
            "Event schema version is not supported.",
            details={"schema_version": event.schema_version},
        )
    if event.cursor is None:
        raise DomainValidationError("Persisted event cursor is required for serialization.")
    return {
        "schema_version": event.schema_version,
        "event_id": event.id,
        "cursor": event.cursor,
        "room_id": event.room_id,
        "session_id": event.session_id,
        "event_type": event.event_type,
        "occurred_at": event.occurred_at.isoformat(),
        "payload": dict(event.payload),
    }


def deserialize_event(payload: dict[str, Any]) -> DomainEvent:
    version = payload.get("schema_version")
    if version != EVENT_SCHEMA_VERSION:
        raise UnsupportedEventVersionError(
            "Event schema version is not supported.", details={"schema_version": version}
        )
    required = {"event_id", "cursor", "room_id", "event_type", "occurred_at", "payload"}
    missing = sorted(required - payload.keys())
    if missing:
        raise DomainValidationError(
            "Event envelope is incomplete.", details={"missing_fields": missing}
        )
    try:
        cursor = int(payload["cursor"])
        occurred_at = datetime.fromisoformat(str(payload["occurred_at"]))
        event_payload = dict(payload["payload"])
    except (TypeError, ValueError) as error:
        raise DomainValidationError("Event envelope contains invalid values.") from error
    return DomainEvent(
        id=str(payload["event_id"]),
        event_type=str(payload["event_type"]),
        aggregate_type="realtime",
        aggregate_id=str(payload["event_id"]),
        room_id=str(payload["room_id"]),
        actor_id="realtime",
        source_id=None,
        target_ids=(),
        payload=event_payload,
        visibility="room",
        schema_version=EVENT_SCHEMA_VERSION,
        command_id=str(payload.get("command_id", payload["event_id"])),
        occurred_at=occurred_at,
        cursor=cursor,
        session_id=str(payload["session_id"]) if payload.get("session_id") else None,
    )
