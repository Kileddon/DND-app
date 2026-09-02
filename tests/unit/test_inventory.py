from __future__ import annotations

from dataclasses import replace
from datetime import UTC, datetime

import pytest

from tabletop_companion.domain.errors import (
    DomainValidationError,
    PermissionDeniedError,
    StateConflictError,
)
from tabletop_companion.domain.models import Character, InventoryItem

NOW = datetime(2026, 9, 2, tzinfo=UTC)


def character() -> Character:
    return Character(
        id="character",
        draft_id="draft",
        room_id="room",
        owner_id="player",
        name="Aria",
        ruleset_version="simple-v1",
        stats={},
        ability_ids=[],
        version=1,
        created_at=NOW,
    )


def item(
    *,
    item_id: str = "potion",
    quantity: int = 5,
    locked: bool = False,
    equipped: bool = False,
    consumable: bool = True,
) -> InventoryItem:
    return InventoryItem(
        id=item_id,
        definition_id=f"definition-{item_id}",
        name="Healing Potion",
        consumable=consumable,
        locked=locked,
        quantity=quantity,
        equipped=equipped,
        charges=3,
        created_at=NOW,
    )


def test_add_item_validates_quantity_and_non_consumable_stack() -> None:
    target = character()

    with pytest.raises(DomainValidationError, match="positive"):
        target.add_item(replace(item(), quantity=0), expected_version=1)
    with pytest.raises(DomainValidationError, match="quantity 1"):
        target.add_item(replace(item(), consumable=False, quantity=2), expected_version=1)


def test_discard_part_of_stack_does_not_apply_effect() -> None:
    target = character()
    target.add_item(item(), expected_version=1)

    result = target.discard("potion", 2, expected_version=2)

    assert result.remaining_quantity == 3
    assert result.removed is False
    assert result.effect_applied is False
    assert target.inventory[0].quantity == 3
    assert target.inventory[0].charges == 3


def test_discard_entire_stack_removes_instance() -> None:
    target = character()
    target.add_item(item(), expected_version=1)

    result = target.discard("potion", 5, expected_version=2)

    assert result.removed is True
    assert result.remaining_quantity == 0
    assert target.inventory == []


def test_discard_rejects_invalid_or_excessive_quantity() -> None:
    target = character()
    target.add_item(item(), expected_version=1)

    with pytest.raises(DomainValidationError, match="positive"):
        target.discard("potion", 0, expected_version=2)
    with pytest.raises(DomainValidationError, match="more than"):
        target.discard("potion", 6, expected_version=2)


def test_locked_item_cannot_be_discarded() -> None:
    target = character()
    target.add_item(item(locked=True), expected_version=1)

    with pytest.raises(PermissionDeniedError, match="locked"):
        target.discard("potion", 1, expected_version=2)


def test_equipped_item_requires_unequip_first() -> None:
    target = character()
    target.add_item(
        item(item_id="sword", quantity=1, equipped=True, consumable=False),
        expected_version=1,
    )

    with pytest.raises(StateConflictError, match="unequipped") as raised:
        target.discard("sword", 1, expected_version=2)

    assert raised.value.code == "item_equipped"


def test_stale_character_version_is_rejected() -> None:
    target = character()

    with pytest.raises(StateConflictError, match="stale"):
        target.add_item(item(), expected_version=99)
