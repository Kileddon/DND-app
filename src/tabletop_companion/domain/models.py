from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime
from enum import StrEnum

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
class LocalPlayer:
    id: str
    room_id: str
    display_name: str
    version: int
    created_at: datetime
    recovery_code_digest: str | None = None
    selected_character_id: str | None = None
    updated_at: datetime | None = None


@dataclass(frozen=True, slots=True)
class AbilityCard:
    id: str
    name: str
    description: str
    kind: str
    properties: tuple[str, ...] = ()
    incompatible_with: frozenset[str] = frozenset()


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

    def ensure_version(self, expected_version: int) -> None:
        if expected_version != self.version:
            raise StateConflictError(
                "Character version is stale.",
                details={"expected_version": expected_version, "current_version": self.version},
            )

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
        if item.equipped:
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
            )
            self.inventory[self.inventory.index(item)] = replacement

        self.version += 1
        return DiscardResult(
            item_id=item_id,
            discarded_quantity=quantity,
            remaining_quantity=remaining,
            removed=removed,
        )
