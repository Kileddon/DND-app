from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from enum import StrEnum

from tabletop_companion.domain.errors import (
    AuthenticationError,
    DomainValidationError,
    PermissionDeniedError,
    StateConflictError,
)


class DeviceRole(StrEnum):
    PLAYER = "player"
    GM = "gm"


class DeviceStatus(StrEnum):
    ACTIVE = "active"
    REVOKED = "revoked"


@dataclass(frozen=True, slots=True)
class PasswordPolicy:
    minimum_length: int = 10
    maximum_length: int = 128

    def validate(self, password: str) -> None:
        if len(password) < self.minimum_length:
            raise DomainValidationError(
                f"Room password must contain at least {self.minimum_length} characters.",
                code="weak_room_password",
            )
        if len(password) > self.maximum_length:
            raise DomainValidationError(
                f"Room password must contain no more than {self.maximum_length} characters.",
                code="weak_room_password",
            )
        if password.isspace():
            raise DomainValidationError(
                "Room password cannot contain only whitespace.", code="weak_room_password"
            )


@dataclass(slots=True)
class PairingInvitation:
    id: str
    room_id: str
    role: DeviceRole
    token_digest: str
    short_code_digest: str
    expires_at: datetime
    created_by: str
    created_at: datetime
    used_at: datetime | None = None
    revoked_at: datetime | None = None

    def consume(self, now: datetime) -> None:
        if self.revoked_at is not None:
            raise AuthenticationError("Pairing invitation was revoked.")
        if self.used_at is not None:
            raise AuthenticationError("Pairing invitation was already used.")
        if now >= self.expires_at:
            raise AuthenticationError("Pairing invitation has expired.")
        self.used_at = now

    def revoke(self, now: datetime) -> None:
        if self.revoked_at is None:
            self.revoked_at = now


@dataclass(slots=True)
class RoomInvitation:
    id: str
    room_id: str
    token_digest: str
    expires_at: datetime
    max_uses: int
    use_count: int
    created_at: datetime
    revoked_at: datetime | None = None

    def consume(self, now: datetime) -> None:
        if self.revoked_at is not None:
            raise PermissionDeniedError("Room invitation was revoked.")
        if now >= self.expires_at:
            raise PermissionDeniedError("Room invitation has expired.")
        if self.use_count >= self.max_uses:
            raise PermissionDeniedError("Room invitation has no remaining uses.")
        self.use_count += 1

    def revoke(self, now: datetime) -> None:
        if self.revoked_at is None:
            self.revoked_at = now


@dataclass(slots=True)
class LocalDevice:
    id: str
    room_id: str
    label: str
    role: DeviceRole
    credential_digest: str
    status: DeviceStatus
    created_at: datetime
    last_seen_at: datetime
    expires_at: datetime
    player_id: str | None = None
    revoked_at: datetime | None = None
    account_id: str | None = None

    def authenticate(self, now: datetime) -> None:
        if self.status is DeviceStatus.REVOKED:
            raise AuthenticationError("Device credential was revoked.")
        if now >= self.expires_at:
            raise AuthenticationError("Device credential has expired.")

    def attach_player(self, player_id: str, now: datetime) -> None:
        self.authenticate(now)
        if self.player_id is not None and self.player_id != player_id:
            raise StateConflictError("Device is already attached to another local profile.")
        self.player_id = player_id
        self.last_seen_at = now

    def attach_account(self, account_id: str) -> None:
        if self.account_id is not None and self.account_id != account_id:
            raise StateConflictError("Device is already attached to another account.")
        self.account_id = account_id

    def touch(self, now: datetime) -> None:
        self.authenticate(now)
        self.last_seen_at = now

    def revoke(self, now: datetime) -> None:
        self.status = DeviceStatus.REVOKED
        self.revoked_at = now

    def rotate_credential(self, digest: str, *, now: datetime, expires_at: datetime) -> None:
        self.authenticate(now)
        self.credential_digest = digest
        self.expires_at = expires_at
        self.last_seen_at = now
