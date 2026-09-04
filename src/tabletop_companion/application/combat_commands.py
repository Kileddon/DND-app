from __future__ import annotations

from dataclasses import dataclass

from tabletop_companion.domain.combat import (
    HealthActionType,
    RollMode,
    RollSelection,
    RollVisibility,
)


@dataclass(frozen=True, slots=True)
class CombatCommand:
    command_id: str
    device_id: str
    client_time: str | None
    room_id: str
    combat_id: str
    expected_version: int


@dataclass(frozen=True, slots=True)
class CreateCombatCommand:
    command_id: str
    device_id: str
    client_time: str | None
    room_id: str
    session_id: str
    name: str = "Энкаунтер"


@dataclass(frozen=True, slots=True)
class AddCharacterCommand(CombatCommand):
    character_id: str
    initiative: int
    max_hp: int
    current_hp: int
    armor_class: int
    late_join: bool


@dataclass(frozen=True, slots=True)
class CreateMonsterTemplateCommand:
    command_id: str
    device_id: str
    client_time: str | None
    room_id: str
    name: str
    image_url: str | None
    max_hp: int
    current_hp: int
    armor_class: int
    notes: str
    conditions: tuple[str, ...]
    actions: tuple[str, ...]
    species: str = ""
    abilities: str = ""
    damage: str = ""
    items: str = ""


@dataclass(frozen=True, slots=True)
class AddMonstersCommand(CombatCommand):
    template_id: str
    initiative: int
    count: int
    grouped: bool


@dataclass(frozen=True, slots=True)
class RemoveInitiativeEntryCommand(CombatCommand):
    entry_id: str


@dataclass(frozen=True, slots=True)
class ReorderInitiativeCommand(CombatCommand):
    entry_ids: tuple[str, ...]


@dataclass(frozen=True, slots=True)
class TransitionCombatCommand(CombatCommand):
    action: str


@dataclass(frozen=True, slots=True)
class MoveTurnCommand(CombatCommand):
    direction: int


@dataclass(frozen=True, slots=True)
class HealthTargetCommand:
    target_id: str
    expected_version: int


@dataclass(frozen=True, slots=True)
class ApplyHealthCommand:
    command_id: str
    device_id: str
    client_time: str | None
    room_id: str
    combat_id: str
    source_id: str | None
    targets: tuple[HealthTargetCommand, ...]
    action: HealthActionType
    amount: int
    prevented: int
    critical: bool
    roll_id: str | None


@dataclass(frozen=True, slots=True)
class AddConditionCommand:
    command_id: str
    device_id: str
    client_time: str | None
    room_id: str
    combat_id: str
    target_id: str
    expected_version: int
    catalog_id: str | None
    name: str
    description: str
    source_id: str | None
    visible_to_players: bool
    persistent: bool = False


@dataclass(frozen=True, slots=True)
class RemoveConditionCommand:
    command_id: str
    device_id: str
    client_time: str | None
    room_id: str
    combat_id: str
    target_id: str
    condition_id: str
    expected_version: int


@dataclass(frozen=True, slots=True)
class SetWoundDisplayCommand:
    command_id: str
    device_id: str
    client_time: str | None
    room_id: str
    combat_id: str
    target_id: str
    expected_version: int
    show: bool
    override: str | None


@dataclass(frozen=True, slots=True)
class RollDiceCommand:
    command_id: str
    device_id: str
    client_time: str | None
    room_id: str
    combat_id: str
    actor_ids: tuple[str, ...]
    expression: str
    mode: RollMode
    visibility: RollVisibility
    recipient_player_id: str | None
    physical_result: int | None
    action_event_id: str | None
    selection: RollSelection = RollSelection.NEUTRAL


@dataclass(frozen=True, slots=True)
class EditRollCommand:
    command_id: str
    device_id: str
    client_time: str | None
    room_id: str
    roll_id: str
    result: int
    reason: str


@dataclass(frozen=True, slots=True)
class RevealRollCommand:
    command_id: str
    device_id: str
    client_time: str | None
    room_id: str
    roll_id: str


@dataclass(frozen=True, slots=True)
class SupportCommand:
    command_id: str
    device_id: str
    client_time: str | None
    room_id: str
    combat_id: str
    character_id: str
    description: str
    roll_id: str | None


@dataclass(frozen=True, slots=True)
class CancelHealthCommand:
    command_id: str
    device_id: str
    client_time: str | None
    room_id: str
    combat_id: str
    original_event_id: str


@dataclass(frozen=True, slots=True)
class CorrectHealthCommand(CancelHealthCommand):
    source_id: str | None
    targets: tuple[HealthTargetCommand, ...]
    action: HealthActionType
    amount: int
    prevented: int
    critical: bool
    roll_id: str | None
