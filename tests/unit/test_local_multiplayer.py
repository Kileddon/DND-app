from __future__ import annotations

from dataclasses import dataclass
from datetime import UTC, datetime, timedelta

import pytest

from tabletop_companion.application.event_contracts import (
    deserialize_event,
    serialize_event,
)
from tabletop_companion.application.fingerprints import command_fingerprint
from tabletop_companion.application.replay import ReplayMode, choose_replay_mode
from tabletop_companion.domain.access import (
    DeviceRole,
    PairingInvitation,
    PasswordPolicy,
    RoomInvitation,
)
from tabletop_companion.domain.errors import (
    AuthenticationError,
    DomainValidationError,
    PermissionDeniedError,
    StateConflictError,
    UnsupportedEventVersionError,
)
from tabletop_companion.domain.events import DomainEvent
from tabletop_companion.domain.sessions import GameSession, SessionStatus

NOW = datetime(2026, 9, 2, 10, tzinfo=UTC)


def pairing(**changes: object) -> PairingInvitation:
    values: dict[str, object] = {
        "id": "pairing-id",
        "room_id": "room-id",
        "role": DeviceRole.PLAYER,
        "token_digest": "token",
        "short_code_digest": "short",
        "expires_at": NOW + timedelta(minutes=5),
        "created_by": "gm-device",
        "created_at": NOW,
    }
    values.update(changes)
    return PairingInvitation(**values)  # type: ignore[arg-type]


def test_pairing_token_is_single_use_expires_and_can_be_revoked() -> None:
    invitation = pairing()
    invitation.consume(NOW + timedelta(seconds=1))
    with pytest.raises(AuthenticationError, match="already used"):
        invitation.consume(NOW + timedelta(seconds=2))

    with pytest.raises(AuthenticationError, match="expired"):
        pairing(expires_at=NOW).consume(NOW)

    revoked = pairing()
    revoked.revoke(NOW)
    with pytest.raises(AuthenticationError, match="revoked"):
        revoked.consume(NOW)


def test_password_and_room_invitation_policies() -> None:
    policy = PasswordPolicy()
    with pytest.raises(DomainValidationError, match="at least"):
        policy.validate("short")
    policy.validate("correct horse battery staple")

    invitation = RoomInvitation(
        id="invite",
        room_id="room",
        token_digest="digest",
        expires_at=NOW + timedelta(minutes=2),
        max_uses=1,
        use_count=0,
        created_at=NOW,
    )
    invitation.consume(NOW)
    with pytest.raises(PermissionDeniedError, match="remaining"):
        invitation.consume(NOW)


def test_session_lifecycle_and_stale_version() -> None:
    session = GameSession(
        id="session",
        room_id="room",
        status=SessionStatus.PREPARATION,
        version=1,
        created_at=NOW,
        updated_at=NOW,
    )
    session.transition(SessionStatus.LOBBY, expected_version=1, now=NOW)
    session.transition(SessionStatus.ACTIVE, expected_version=2, now=NOW)
    session.transition(SessionStatus.PAUSED, expected_version=3, now=NOW)
    session.transition(SessionStatus.ACTIVE, expected_version=4, now=NOW)
    session.transition(SessionStatus.COMPLETED, expected_version=5, now=NOW)
    assert session.status is SessionStatus.COMPLETED
    assert session.version == 6
    with pytest.raises(StateConflictError, match="cannot transition"):
        session.transition(SessionStatus.ACTIVE, expected_version=6, now=NOW)

    stale = GameSession(
        id="stale",
        room_id="room",
        status=SessionStatus.LOBBY,
        version=2,
        created_at=NOW,
        updated_at=NOW,
    )
    with pytest.raises(StateConflictError, match="stale"):
        stale.transition(SessionStatus.ACTIVE, expected_version=1, now=NOW)


@dataclass(frozen=True)
class FingerprintCommand:
    command_id: str
    actor: str
    payload: dict[str, object]


def test_command_fingerprint_is_stable_and_content_sensitive() -> None:
    left = FingerprintCommand("command", "actor", {"b": [2, 3], "a": 1})
    reordered = FingerprintCommand("command", "actor", {"a": 1, "b": [2, 3]})
    changed_actor = FingerprintCommand("command", "other", {"a": 1, "b": [2, 3]})
    assert command_fingerprint(left) == command_fingerprint(reordered)
    assert command_fingerprint(left) != command_fingerprint(changed_actor)


def event(schema_version: int = 1, cursor: int | None = 7) -> DomainEvent:
    return DomainEvent(
        id="event",
        event_type="ThingChanged",
        aggregate_type="thing",
        aggregate_id="thing",
        room_id="room",
        actor_id="actor",
        source_id=None,
        target_ids=("thing",),
        payload={"nested": {"value": 1}},
        visibility="room",
        schema_version=schema_version,
        command_id="command",
        occurred_at=NOW,
        cursor=cursor,
        session_id="session",
    )


def test_event_contract_round_trip_and_unknown_version_rejected() -> None:
    envelope = serialize_event(event())
    restored = deserialize_event(envelope)
    assert serialize_event(restored) == envelope
    with pytest.raises(UnsupportedEventVersionError):
        deserialize_event({**envelope, "schema_version": 999})


@pytest.mark.parametrize(
    ("last", "minimum", "maximum", "expected"),
    [
        (0, 1, 5, ReplayMode.SNAPSHOT),
        (2, 1, 5, ReplayMode.INCREMENTAL),
        (1, 3, 5, ReplayMode.SNAPSHOT),
        (1, 1, 1000, ReplayMode.SNAPSHOT),
    ],
)
def test_cursor_replay_choice(last: int, minimum: int, maximum: int, expected: ReplayMode) -> None:
    assert (
        choose_replay_mode(
            last_cursor=last,
            minimum_cursor=minimum,
            maximum_cursor=maximum,
            replay_limit=100,
        )
        is expected
    )
