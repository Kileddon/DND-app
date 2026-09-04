from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime
from decimal import Decimal
from enum import StrEnum

from tabletop_companion.domain.character_creation import (
    SlotCompatibility,
    inventory_weight,
    slot_is_compatible,
)
from tabletop_companion.domain.errors import (
    DomainValidationError,
    PermissionDeniedError,
    StateConflictError,
)


class AccessMode(StrEnum):
    OPEN = "open"
    PASSWORD = "password"
    INVITATION = "invitation"


class DraftStatus(StrEnum):
    ACTIVE = "active"
    CONFIRMED = "confirmed"


@dataclass(frozen=True, slots=True)
class Room:
    id: str
    name: str
    gm_id: str
    access_mode: AccessMode
    ruleset_version: str
    version: int
    created_at: datetime
    code: str = ""
    password_hash: str | None = None


@dataclass(frozen=True, slots=True)
class Account:
    id: str
    display_name: str
    version: int
    created_at: datetime
    updated_at: datetime
    cloud_identity: str | None = None


@dataclass(frozen=True, slots=True)
class LocalPlayer:
    id: str
    room_id: str
    display_name: str
    version: int
    created_at: datetime
    selected_character_id: str | None = None
    updated_at: datetime | None = None
    removed_at: datetime | None = None
    account_id: str | None = None


@dataclass(frozen=True, slots=True)
class AbilityCard:
    id: str
    name: str
    description: str
    kind: str
    properties: tuple[str, ...] = ()
    incompatible_with: frozenset[str] = frozenset()
    class_ids: frozenset[str] = frozenset()
    required_stats: tuple[tuple[str, int], ...] = ()
    required_ability_ids: frozenset[str] = frozenset()


@dataclass(slots=True)
class CharacterDraft:
    id: str
    room_id: str
    owner_id: str
    name: str
    ruleset_version: str
    stats: dict[str, int]
    offered_card_ids: list[str]
    chosen_card_ids: list[str]
    generation: int
    status: DraftStatus
    version: int
    created_at: datetime
    updated_at: datetime
    race_id: str = "human"
    class_id: str = "fighter"
    account_id: str | None = None
    step: str = "name"
    species_choices: dict[str, str] = field(default_factory=dict)
    stat_method: str | None = None
    base_stats: dict[str, int] = field(default_factory=dict)
    background: dict[str, object] = field(default_factory=dict)
    random_rolls: list[dict[str, object]] = field(default_factory=list)

    def ensure_active(self) -> None:
        if self.status is not DraftStatus.ACTIVE:
            raise StateConflictError("Character draft is already confirmed.")

    def ensure_version(self, expected_version: int) -> None:
        if expected_version != self.version:
            raise StateConflictError(
                "Character draft version is stale.",
                details={"expected_version": expected_version, "current_version": self.version},
            )


@dataclass(frozen=True, slots=True)
class ItemDefinition:
    id: str
    name: str
    consumable: bool
    locked: bool
    unit_weight: Decimal = Decimal("0")
    slot_compatibility: SlotCompatibility = SlotCompatibility.NONE


@dataclass(frozen=True, slots=True)
class InventoryItem:
    id: str
    definition_id: str
    name: str
    consumable: bool
    locked: bool
    quantity: int
    equipped: bool
    charges: int | None
    created_at: datetime
    unit_weight: Decimal = Decimal("0")
    slot_compatibility: SlotCompatibility = SlotCompatibility.NONE
    equipment_slot: str | None = None


@dataclass(frozen=True, slots=True)
class DiscardResult:
    item_id: str
    discarded_quantity: int
    remaining_quantity: int
    removed: bool
    effect_applied: bool = False


@dataclass(slots=True)
class Character:
    id: str
    draft_id: str
    room_id: str
    owner_id: str
    name: str
    ruleset_version: str
    stats: dict[str, int]
    ability_ids: list[str]
    version: int
    created_at: datetime
    inventory: list[InventoryItem] = field(default_factory=list)
    race_id: str = "human"
    class_id: str = "fighter"
    max_hp: int = 10
    current_hp: int = 10
    armor_class: int = 10
    account_id: str | None = None
    archived_at: datetime | None = None
    level: int = 1
    experience: int = 0
    temporary_hp: int = 0
    initiative: int = 0
    proficiency_bonus: int = 2
    size: str = "medium"
    speed: int = 30
    darkvision: int = 0
    species_choices: dict[str, str] = field(default_factory=dict)
    persistent_conditions: list[dict[str, object]] = field(default_factory=list)

    def ensure_version(self, expected_version: int) -> None:
        if expected_version != self.version:
            raise StateConflictError(
                "Character version is stale.",
                details={"expected_version": expected_version, "current_version": self.version},
            )

    def edit(
        self,
        *,
        name: str,
        race_id: str,
        class_id: str,
        stats: dict[str, int],
        ability_ids: list[str],
        max_hp: int,
        current_hp: int,
        armor_class: int,
        expected_version: int,
        temporary_hp: int = 0,
        level: int = 1,
        experience: int = 0,
        initiative: int = 0,
        proficiency_bonus: int = 2,
        size: str = "medium",
        speed: int = 30,
        darkvision: int = 0,
        species_choices: dict[str, str] | None = None,
        persistent_conditions: list[dict[str, object]] | None = None,
    ) -> None:
        self.ensure_version(expected_version)
        normalized_name = name.strip()
        if not normalized_name:
            raise DomainValidationError("Character name must not be blank.")
        if max_hp <= 0 or not 0 <= current_hp <= max_hp:
            raise DomainValidationError("Character health values are invalid.")
        if armor_class <= 0:
            raise DomainValidationError("Armor class must be positive.")
        if temporary_hp < 0 or not 1 <= level <= 20 or experience < 0:
            raise DomainValidationError("Character progression or temporary HP is invalid.")
        if not 2 <= proficiency_bonus <= 10 or size not in {"small", "medium"}:
            raise DomainValidationError("Character proficiency or size is invalid.")
        if not 0 <= speed <= 200 or not 0 <= darkvision <= 1000:
            raise DomainValidationError("Character movement or darkvision is invalid.")
        if any(not 1 <= value <= 30 for value in stats.values()):
            raise DomainValidationError("Character attributes must be between 1 and 30.")
        self.name = normalized_name
        self.race_id = race_id
        self.class_id = class_id
        self.stats = dict(stats)
        self.ability_ids = list(ability_ids)
        self.max_hp = max_hp
        self.current_hp = current_hp
        self.armor_class = armor_class
        self.temporary_hp = temporary_hp
        self.level = level
        self.experience = experience
        self.initiative = initiative
        self.proficiency_bonus = proficiency_bonus
        self.size = size
        self.speed = speed
        self.darkvision = darkvision
        if species_choices is not None:
            self.species_choices = dict(species_choices)
        if persistent_conditions is not None:
            self.persistent_conditions = [dict(item) for item in persistent_conditions]
        self.version += 1

    def edit_health(self, *, current_hp: int, temporary_hp: int, expected_version: int) -> None:
        self.ensure_version(expected_version)
        if not 0 <= current_hp <= self.max_hp or temporary_hp < 0:
            raise DomainValidationError("Character health values are invalid.")
        self.current_hp = current_hp
        self.temporary_hp = temporary_hp
        self.version += 1

    def add_item(self, item: InventoryItem, *, expected_version: int) -> None:
        self.ensure_version(expected_version)
        if item.quantity <= 0:
            raise DomainValidationError("Item quantity must be positive.")
        if not item.consumable and item.quantity != 1:
            raise DomainValidationError("A non-consumable item must have quantity 1.")
        if any(existing.id == item.id for existing in self.inventory):
            raise StateConflictError("Inventory item already exists.")
        self.inventory.append(item)
        self.version += 1

    @property
    def total_weight(self) -> Decimal:
        return inventory_weight([(item.unit_weight, item.quantity) for item in self.inventory])

    def equip(self, item_id: str, slot: str, *, expected_version: int) -> None:
        self.ensure_version(expected_version)
        item = self._item(item_id)
        if item.equipment_slot == slot:
            self.version += 1
            return
        if any(candidate.equipment_slot == slot for candidate in self.inventory):
            raise StateConflictError("Equipment slot is occupied.", code="equipment_slot_occupied")
        if not slot_is_compatible(item.slot_compatibility, slot):
            raise DomainValidationError(
                "Item is not compatible with this equipment slot.",
                code="incompatible_equipment_slot",
            )
        self._replace_item(item, equipment_slot=slot)
        self.version += 1

    def unequip(self, item_id: str, *, expected_version: int) -> None:
        self.ensure_version(expected_version)
        item = self._item(item_id)
        if item.equipment_slot is None:
            self.version += 1
            return
        self._replace_item(item, equipment_slot=None)
        self.version += 1

    def archive(self, *, now: datetime, expected_version: int, active_encounter: bool) -> None:
        self.ensure_version(expected_version)
        if active_encounter:
            raise StateConflictError(
                "A character in an active encounter cannot be archived.",
                code="character_in_active_encounter",
            )
        self.archived_at = now
        self.version += 1

    def restore(self, *, expected_version: int) -> None:
        self.ensure_version(expected_version)
        self.archived_at = None
        self.version += 1

    def discard(self, item_id: str, quantity: int, *, expected_version: int) -> DiscardResult:
        self.ensure_version(expected_version)
        if quantity <= 0:
            raise DomainValidationError("Discard quantity must be positive.")

        item = next((candidate for candidate in self.inventory if candidate.id == item_id), None)
        if item is None:
            raise DomainValidationError(
                "Inventory item does not belong to the character.",
                details={"item_id": item_id},
            )
        if item.locked:
            raise PermissionDeniedError("This item is locked and cannot be discarded.")
        if item.equipped or item.equipment_slot is not None:
            raise StateConflictError(
                "Equipped items must be unequipped before they can be discarded.",
                code="item_equipped",
            )
        if quantity > item.quantity:
            raise DomainValidationError(
                "Cannot discard more than the available quantity.",
                details={"available_quantity": item.quantity, "requested_quantity": quantity},
            )

        remaining = item.quantity - quantity
        removed = remaining == 0
        if removed:
            self.inventory.remove(item)
        else:
            replacement = InventoryItem(
                id=item.id,
                definition_id=item.definition_id,
                name=item.name,
                consumable=item.consumable,
                locked=item.locked,
                quantity=remaining,
                equipped=item.equipped,
                charges=item.charges,
                created_at=item.created_at,
                unit_weight=item.unit_weight,
                slot_compatibility=item.slot_compatibility,
                equipment_slot=item.equipment_slot,
            )
            self.inventory[self.inventory.index(item)] = replacement

        self.version += 1
        return DiscardResult(
            item_id=item_id,
            discarded_quantity=quantity,
            remaining_quantity=remaining,
            removed=removed,
        )

    def _item(self, item_id: str) -> InventoryItem:
        item = next((candidate for candidate in self.inventory if candidate.id == item_id), None)
        if item is None:
            raise DomainValidationError(
                "Inventory item does not belong to the character.", details={"item_id": item_id}
            )
        return item

    def _replace_item(self, item: InventoryItem, *, equipment_slot: str | None) -> None:
        self.inventory[self.inventory.index(item)] = InventoryItem(
            id=item.id,
            definition_id=item.definition_id,
            name=item.name,
            consumable=item.consumable,
            locked=item.locked,
            quantity=item.quantity,
            equipped=equipment_slot is not None,
            charges=item.charges,
            created_at=item.created_at,
            unit_weight=item.unit_weight,
            slot_compatibility=item.slot_compatibility,
            equipment_slot=equipment_slot,
        )


@dataclass(slots=True)
class GmNotes:
    room_id: str
    campaign: str
    other: str
    version: int
    updated_at: datetime


@dataclass(slots=True)
class NpcNote:
    id: str
    room_id: str
    name: str
    details: str
    version: int
    created_at: datetime
    updated_at: datetime


@dataclass(slots=True)
class PlayerNoteNode:
    id: str
    room_id: str
    player_id: str
    parent_id: str | None
    kind: str
    name: str
    body: str
    depth: int
    version: int
    created_at: datetime
    updated_at: datetime

    def edit(self, *, name: str, body: str, expected_version: int, now: datetime) -> None:
        if expected_version != self.version:
            raise StateConflictError("Player note changed concurrently.")
        normalized = name.strip()
        if not normalized:
            raise DomainValidationError("Player note name must not be blank.")
        if len(normalized) > 120 or len(body) > 50000:
            raise DomainValidationError("Player note is too long.")
        self.name = normalized
        self.body = body if self.kind == "note" else ""
        self.version += 1
        self.updated_at = now
