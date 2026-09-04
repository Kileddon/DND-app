from __future__ import annotations

from dataclasses import dataclass, field

from tabletop_companion.domain.models import AccessMode


@dataclass(frozen=True, slots=True)
class CreateRoomCommand:
    command_id: str
    device_id: str
    client_time: str | None
    gm_id: str
    name: str
    access_mode: AccessMode


@dataclass(frozen=True, slots=True)
class JoinLocalPlayerCommand:
    command_id: str
    device_id: str
    client_time: str | None
    room_id: str
    display_name: str


@dataclass(frozen=True, slots=True)
class StartCharacterDraftCommand:
    command_id: str
    device_id: str
    client_time: str | None
    room_id: str
    player_id: str
    name: str
    race_id: str = "human"
    class_id: str = "fighter"
    species_choices: dict[str, str] = field(default_factory=dict)
    stat_method: str = "standard"
    stats: dict[str, int] = field(default_factory=dict)
    background_pattern: str = "1+1+1"
    background_stats: tuple[str, str, str] = ("strength", "dexterity", "constitution")
    background_allocations: dict[str, int] = field(default_factory=dict)
    ruleset_version: str | None = None


@dataclass(frozen=True, slots=True)
class ChooseAbilityCardCommand:
    command_id: str
    device_id: str
    client_time: str | None
    player_id: str
    draft_id: str
    card_id: str
    expected_version: int


@dataclass(frozen=True, slots=True)
class RestartCharacterDraftCommand:
    command_id: str
    device_id: str
    client_time: str | None
    player_id: str
    draft_id: str
    expected_version: int


@dataclass(frozen=True, slots=True)
class ConfirmCharacterDraftCommand:
    command_id: str
    device_id: str
    client_time: str | None
    player_id: str
    draft_id: str
    expected_version: int


@dataclass(frozen=True, slots=True)
class AddInventoryItemCommand:
    command_id: str
    device_id: str
    client_time: str | None
    actor_id: str
    character_id: str
    name: str
    quantity: int
    consumable: bool
    locked: bool
    equipped: bool
    charges: int | None
    expected_version: int
    unit_weight: str = "0"
    slot_compatibility: str = "none"


@dataclass(frozen=True, slots=True)
class EquipInventoryItemCommand:
    command_id: str
    device_id: str
    client_time: str | None
    actor_id: str
    character_id: str
    item_id: str
    slot: str | None
    expected_version: int


@dataclass(frozen=True, slots=True)
class CharacterLifecycleCommand:
    command_id: str
    device_id: str
    client_time: str | None
    actor_id: str
    character_id: str
    room_id: str
    expected_version: int
    action: str


@dataclass(frozen=True, slots=True)
class DiscardInventoryItemCommand:
    command_id: str
    device_id: str
    client_time: str | None
    actor_id: str
    character_id: str
    item_id: str
    quantity: int
    expected_version: int
