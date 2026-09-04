from __future__ import annotations

from datetime import datetime
from typing import Any
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field

from tabletop_companion.domain.access import DeviceRole
from tabletop_companion.domain.combat import RollMode, RollSelection, RollVisibility
from tabletop_companion.domain.models import AccessMode
from tabletop_companion.domain.sessions import SessionStatus


class CommandMeta(BaseModel):
    replayed: bool


class CommandResponse[ViewT](BaseModel):
    data: ViewT
    meta: CommandMeta


class ListMeta(BaseModel):
    count: int


class ListResponse[ViewT](BaseModel):
    data: list[ViewT]
    meta: ListMeta


class ErrorBody(BaseModel):
    code: str
    message: str
    details: dict[str, Any] = Field(default_factory=dict)


class ErrorResponse(BaseModel):
    error: ErrorBody


class CommandRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    command_id: UUID
    device_id: str = Field(min_length=1, max_length=120)
    client_time: datetime | None = None


class CreateRoomRequest(CommandRequest):
    gm_id: UUID
    name: str = Field(min_length=1, max_length=120)
    access_mode: AccessMode = AccessMode.OPEN


class JoinLocalPlayerRequest(CommandRequest):
    display_name: str = Field(min_length=1, max_length=80)


class StartCharacterDraftRequest(CommandRequest):
    name: str = Field(min_length=1, max_length=80)
    race_id: str = Field(default="human", min_length=1, max_length=40)
    class_id: str = Field(default="fighter", min_length=1, max_length=40)
    species_choices: dict[str, str] = Field(default_factory=dict)
    stat_method: str = Field(default="standard", pattern="^(standard|random|point_buy)$")
    stats: dict[str, int] = Field(default_factory=dict)
    background_pattern: str = Field(default="1+1+1", pattern=r"^(2\+1|1\+1\+1)$")
    background_stats: tuple[str, str, str] = ("strength", "dexterity", "constitution")
    background_allocations: dict[str, int] = Field(default_factory=dict)


class ChooseAbilityCardRequest(CommandRequest):
    card_id: str = Field(min_length=1, max_length=80)
    expected_version: int = Field(ge=1)


class RestartCharacterDraftRequest(CommandRequest):
    expected_version: int = Field(ge=1)


class ConfirmCharacterDraftRequest(CommandRequest):
    expected_version: int = Field(ge=1)


class AddInventoryItemRequest(CommandRequest):
    actor_id: UUID
    name: str = Field(min_length=1, max_length=120)
    quantity: int = Field(ge=1)
    consumable: bool = False
    locked: bool = False
    equipped: bool = False
    charges: int | None = Field(default=None, ge=0)
    expected_version: int = Field(ge=1)
    unit_weight: str = Field(default="0", pattern=r"^\d+(?:\.\d{1,3})?$")
    slot_compatibility: str = Field(default="none", pattern="^(hand|armor|other|none)$")


class EquipInventoryItemRequest(CommandRequest):
    actor_id: UUID
    slot: str | None = Field(default=None, pattern="^(left_hand|right_hand|armor|other_[1-4])$")
    expected_version: int = Field(ge=1)


class CharacterLifecycleRequest(CommandRequest):
    expected_version: int = Field(ge=1)
    action: str = Field(pattern="^(assign|archive|restore)$")


class DiscardInventoryItemRequest(CommandRequest):
    actor_id: UUID
    quantity: int = Field(ge=1)
    expected_version: int = Field(ge=1)


class RoomDiceRollRequest(CommandRequest):
    expression: str = Field(min_length=2, max_length=32)
    selection: RollSelection = RollSelection.NEUTRAL
    visibility: RollVisibility = RollVisibility.PUBLIC
    mode: RollMode = RollMode.DIGITAL
    recipient_player_id: UUID | None = None
    physical_result: int | None = None


class AbilityCardView(BaseModel):
    id: str
    name: str
    description: str
    kind: str
    properties: list[str]
    class_ids: list[str] = Field(default_factory=list)
    required_stats: dict[str, int] = Field(default_factory=dict)
    required_ability_ids: list[str] = Field(default_factory=list)


class RoomView(BaseModel):
    id: UUID
    name: str
    gm_id: UUID
    access_mode: AccessMode
    ruleset_version: str
    version: int
    created_at: datetime
    code: str


class LocalPlayerView(BaseModel):
    id: UUID
    room_id: UUID
    display_name: str
    version: int
    created_at: datetime


class CharacterDraftView(BaseModel):
    id: UUID
    room_id: UUID
    owner_id: UUID
    name: str
    ruleset_version: str
    stats: dict[str, int]
    race_id: str
    class_id: str
    offered_cards: list[AbilityCardView]
    chosen_cards: list[AbilityCardView]
    completed_rounds: int
    required_rounds: int
    ready_to_confirm: bool
    generation: int
    status: str
    version: int
    created_at: datetime
    updated_at: datetime
    step: str = "name"
    species_choices: dict[str, str] = Field(default_factory=dict)
    stat_method: str | None = None
    base_stats: dict[str, int] = Field(default_factory=dict)
    background: dict[str, Any] = Field(default_factory=dict)
    random_rolls: list[dict[str, Any]] = Field(default_factory=list)


class InventoryItemView(BaseModel):
    id: UUID
    definition_id: UUID
    name: str
    consumable: bool
    locked: bool
    quantity: int
    equipped: bool
    charges: int | None
    created_at: datetime
    unit_weight: str = "0"
    slot_compatibility: str = "none"
    equipment_slot: str | None = None


class CharacterView(BaseModel):
    id: UUID
    draft_id: UUID
    room_id: UUID
    owner_id: UUID
    name: str
    ruleset_version: str
    stats: dict[str, int]
    race_id: str
    class_id: str
    max_hp: int
    current_hp: int
    armor_class: int
    abilities: list[AbilityCardView]
    inventory: list[InventoryItemView]
    version: int
    created_at: datetime
    account_id: UUID | None = None
    archived_at: datetime | None = None
    level: int = 1
    experience: int = 0
    temporary_hp: int = 0
    initiative: int = 0
    proficiency_bonus: int = 2
    size: str = "medium"
    speed: int = 30
    darkvision: int = 0
    species_choices: dict[str, str] = Field(default_factory=dict)
    total_weight: str = "0"


class EventView(BaseModel):
    id: UUID
    event_type: str
    aggregate_type: str
    aggregate_id: UUID
    room_id: UUID
    actor_id: str
    source_id: str | None
    target_ids: list[str]
    payload: dict[str, Any]
    visibility: str
    schema_version: int
    command_id: UUID
    occurred_at: datetime
    cursor: int
    session_id: UUID | None


class HealthView(BaseModel):
    status: str


class BootstrapRoomRequest(CommandRequest):
    gm_id: UUID
    name: str = Field(min_length=1, max_length=120)
    access_mode: AccessMode = AccessMode.OPEN
    password: str | None = Field(default=None, max_length=128)
    device_label: str = Field(default="GM laptop", min_length=1, max_length=120)


class PairingCreateRequest(CommandRequest):
    ttl_seconds: int = Field(default=300, ge=30, le=900)
    role: DeviceRole = DeviceRole.PLAYER


class PairingExchangeRequest(CommandRequest):
    token: str | None = Field(default=None, min_length=8, max_length=256)
    short_code: str | None = Field(default=None, min_length=6, max_length=16)
    device_label: str = Field(default="Player device", min_length=1, max_length=120)


class ProfileCreateRequest(CommandRequest):
    display_name: str = Field(min_length=1, max_length=80)
    password: str | None = Field(default=None, max_length=128)
    invitation_token: str | None = Field(default=None, max_length=256)


class CharacterSelectRequest(CommandRequest):
    character_id: UUID
    expected_version: int = Field(ge=1)


class RoomInvitationCreateRequest(CommandRequest):
    ttl_seconds: int = Field(default=3600, ge=30, le=86400)
    max_uses: int = Field(default=1, ge=1, le=50)


class SessionCreateRequest(CommandRequest):
    pass


class SessionTransitionRequest(CommandRequest):
    target_status: SessionStatus
    expected_version: int = Field(ge=1)


class DeviceRevokeRequest(CommandRequest):
    pass


class CharacterUpdateRequest(CommandRequest):
    name: str = Field(min_length=1, max_length=80)
    race_id: str = Field(min_length=1, max_length=40)
    class_id: str = Field(min_length=1, max_length=40)
    stats: dict[str, int]
    ability_ids: list[str]
    max_hp: int = Field(ge=1, le=100000)
    current_hp: int = Field(ge=0, le=100000)
    armor_class: int = Field(ge=1, le=1000)
    expected_version: int = Field(ge=1)
    temporary_hp: int = Field(default=0, ge=0, le=100000)
    level: int = Field(default=1, ge=1, le=20)
    experience: int = Field(default=0, ge=0)
    initiative: int = Field(default=0, ge=-20, le=20)
    proficiency_bonus: int = Field(default=2, ge=2, le=10)
    size: str = Field(default="medium", pattern="^(small|medium)$")
    speed: int = Field(default=30, ge=0, le=200)
    darkvision: int = Field(default=0, ge=0, le=1000)
    species_choices: dict[str, str] = Field(default_factory=dict)
    persistent_conditions: list[dict[str, Any]] = Field(default_factory=list)


class GmNotesUpdateRequest(CommandRequest):
    campaign: str = Field(max_length=20000)
    other: str = Field(max_length=20000)
    expected_version: int = Field(ge=0)


class NpcNoteCreateRequest(CommandRequest):
    name: str = Field(min_length=1, max_length=120)


class NpcNoteUpdateRequest(CommandRequest):
    name: str = Field(min_length=1, max_length=120)
    details: str = Field(max_length=20000)
    expected_version: int = Field(ge=1)


class LocalCommandResponse(BaseModel):
    data: dict[str, Any]
    meta: CommandMeta


class SnapshotView(BaseModel):
    model_config = ConfigDict(extra="allow")

    cursor: int
    room: dict[str, Any]
    session: dict[str, Any] | None


class DiagnosticsView(BaseModel):
    hostname: str
    addresses: list[str]
    port: int
    api_available: bool
    access_policy: str
    websocket_connections: int
    reconnecting_clients: int
    players: int
    devices: int
    event_cursor: int
    sqlite_bytes: int
    sqlite_journal_mode: str
    free_disk_bytes: int
    uptime_seconds: int
    backend_version: str
    frontend_version: str
    database_revision: str
    last_errors: list[dict[str, str]]
