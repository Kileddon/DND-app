from __future__ import annotations

from dataclasses import dataclass

from tabletop_companion.domain.access import DeviceRole
from tabletop_companion.domain.combat import RollMode, RollSelection, RollVisibility
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
class SelectCharacterCommand:
    command_id: str
    device_id: str
    client_time: str | None
    player_id: str
    character_id: str
    expected_version: int


@dataclass(frozen=True, slots=True)
class ClearCharacterSelectionCommand:
    command_id: str
    device_id: str
    client_time: str | None
    player_id: str
    expected_version: int


@dataclass(frozen=True, slots=True)
class UpdateOwnCharacterHealthCommand:
    command_id: str
    device_id: str
    client_time: str | None
    player_id: str
    character_id: str
    current_hp: int
    temporary_hp: int
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
class KickPlayerCommand:
    command_id: str
    device_id: str
    client_time: str | None
    room_id: str
    actor_id: str
    player_id: str


@dataclass(frozen=True, slots=True)
class RollRoomDiceCommand:
    command_id: str
    device_id: str
    client_time: str | None
    room_id: str
    actor_id: str
    expression: str
    selection: RollSelection
    visibility: RollVisibility = RollVisibility.PUBLIC
    mode: RollMode = RollMode.DIGITAL
    recipient_player_id: str | None = None
    physical_result: int | None = None


@dataclass(frozen=True, slots=True)
class UpdateCharacterCommand:
    command_id: str
    device_id: str
    client_time: str | None
    room_id: str
    actor_id: str
    character_id: str
    name: str
    race_id: str
    class_id: str
    stats: dict[str, int]
    ability_ids: tuple[str, ...]
    max_hp: int
    current_hp: int
    armor_class: int
    expected_version: int
    temporary_hp: int = 0
    level: int = 1
    experience: int = 0
    initiative: int = 0
    proficiency_bonus: int = 2
    size: str = "medium"
    speed: int = 30
    darkvision: int = 0
    species_choices: dict[str, str] | None = None
    persistent_conditions: list[dict[str, object]] | None = None


@dataclass(frozen=True, slots=True)
class GmAddInventoryItemCommand:
    command_id: str
    device_id: str
    client_time: str | None
    room_id: str
    actor_id: str
    character_id: str
    name: str
    expected_version: int


@dataclass(frozen=True, slots=True)
class GmDiscardInventoryItemCommand:
    command_id: str
    device_id: str
    client_time: str | None
    room_id: str
    actor_id: str
    character_id: str
    item_id: str
    expected_version: int


@dataclass(frozen=True, slots=True)
class UpdateGmNotesCommand:
    command_id: str
    device_id: str
    client_time: str | None
    room_id: str
    actor_id: str
    campaign: str
    other: str
    expected_version: int


@dataclass(frozen=True, slots=True)
class CreateNpcNoteCommand:
    command_id: str
    device_id: str
    client_time: str | None
    room_id: str
    actor_id: str
    name: str


@dataclass(frozen=True, slots=True)
class UpdateNpcNoteCommand:
    command_id: str
    device_id: str
    client_time: str | None
    room_id: str
    actor_id: str
    npc_id: str
    name: str
    details: str
    expected_version: int


@dataclass(frozen=True, slots=True)
class DeleteNpcNoteCommand:
    command_id: str
    device_id: str
    client_time: str | None
    room_id: str
    actor_id: str
    npc_id: str


@dataclass(frozen=True, slots=True)
class CreatePlayerNoteNodeCommand:
    command_id: str
    device_id: str
    client_time: str | None
    player_id: str
    kind: str
    name: str
    parent_id: str | None = None


@dataclass(frozen=True, slots=True)
class UpdatePlayerNoteNodeCommand:
    command_id: str
    device_id: str
    client_time: str | None
    player_id: str
    node_id: str
    name: str
    body: str
    expected_version: int


@dataclass(frozen=True, slots=True)
class RefreshDeviceCredentialCommand:
    command_id: str
    device_id: str
    client_time: str | None
