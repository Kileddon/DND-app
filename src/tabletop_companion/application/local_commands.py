from __future__ import annotations

from dataclasses import dataclass

from tabletop_companion.domain.access import DeviceRole
from tabletop_companion.domain.models import AccessMode
from tabletop_companion.domain.sessions import SessionStatus


@dataclass(frozen=True, slots=True)
class BootstrapRoomCommand:
    command_id: str
    device_id: str
    client_time: str | None
    gm_id: str
    name: str
    access_mode: AccessMode
    password: str | None
    device_label: str


@dataclass(frozen=True, slots=True)
class CreatePairingCommand:
    command_id: str
    device_id: str
    client_time: str | None
    room_id: str
    actor_id: str
    role: DeviceRole = DeviceRole.PLAYER
    ttl_seconds: int = 300


@dataclass(frozen=True, slots=True)
class RevokePairingCommand:
    command_id: str
    device_id: str
    client_time: str | None
    room_id: str
    actor_id: str
    invitation_id: str | None = None


@dataclass(frozen=True, slots=True)
class ExchangePairingCommand:
    command_id: str
    device_id: str
    client_time: str | None
    token: str | None
    short_code: str | None
    device_label: str


@dataclass(frozen=True, slots=True)
class CreateProfileCommand:
    command_id: str
    device_id: str
    client_time: str | None
    display_name: str
    password: str | None = None
    invitation_token: str | None = None


@dataclass(frozen=True, slots=True)
class RecoverProfileCommand:
    command_id: str
    device_id: str
    client_time: str | None
    player_id: str
    recovery_code: str


@dataclass(frozen=True, slots=True)
class SelectCharacterCommand:
    command_id: str
    device_id: str
    client_time: str | None
    player_id: str
    character_id: str
    expected_version: int


@dataclass(frozen=True, slots=True)
class CreateRoomInvitationCommand:
    command_id: str
    device_id: str
    client_time: str | None
    room_id: str
    actor_id: str
    ttl_seconds: int = 3600
    max_uses: int = 1


@dataclass(frozen=True, slots=True)
class RevokeRoomInvitationCommand:
    command_id: str
    device_id: str
    client_time: str | None
    room_id: str
    actor_id: str
    invitation_id: str


@dataclass(frozen=True, slots=True)
class CreateSessionCommand:
    command_id: str
    device_id: str
    client_time: str | None
    room_id: str
    actor_id: str


@dataclass(frozen=True, slots=True)
class TransitionSessionCommand:
    command_id: str
    device_id: str
    client_time: str | None
    room_id: str
    actor_id: str
    session_id: str
    target_status: SessionStatus
    expected_version: int


@dataclass(frozen=True, slots=True)
class RevokeDeviceCommand:
    command_id: str
    device_id: str
    client_time: str | None
    room_id: str
    actor_id: str
    target_device_id: str


@dataclass(frozen=True, slots=True)
class RefreshDeviceCredentialCommand:
    command_id: str
    device_id: str
    client_time: str | None
