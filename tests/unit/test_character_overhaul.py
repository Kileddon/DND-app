from datetime import UTC, datetime
from decimal import Decimal

import pytest

from tabletop_companion.domain.character_creation import (
    SlotCompatibility,
    ability_modifier,
    apply_background_bonus,
    derived_statistics,
    drop_lowest,
    inventory_weight,
    point_buy_cost,
    slot_is_compatible,
    standard_stats,
    validate_point_buy,
    visible_other_slot_count,
)
from tabletop_companion.domain.errors import DomainValidationError, StateConflictError
from tabletop_companion.domain.models import Character, InventoryItem
from tabletop_companion.domain.species import DRAGON_DAMAGE, species_sheet, validate_species_choices


def test_ability_modifier_uses_floor_for_negative_values() -> None:
    assert [ability_modifier(value) for value in (7, 8, 9, 10, 11, 15)] == [-2, -1, -1, 0, 0, 2]


def test_every_class_has_a_complete_standard_array() -> None:
    for class_id in (
        "bard",
        "barbarian",
        "fighter",
        "wizard",
        "druid",
        "cleric",
        "warlock",
        "monk",
        "paladin",
        "rogue",
        "ranger",
        "sorcerer",
    ):
        assert set(standard_stats(class_id)) == {
            "strength",
            "dexterity",
            "constitution",
            "intelligence",
            "wisdom",
            "charisma",
        }


def test_point_buy_requires_exactly_27_points() -> None:
    stats = dict(zip(standard_stats("fighter"), (15, 15, 15, 8, 8, 8), strict=True))
    assert point_buy_cost(stats) == 27
    validate_point_buy(stats)
    with pytest.raises(DomainValidationError, match="27"):
        validate_point_buy({**stats, "charisma": 9})


def test_background_patterns_are_validated_and_capped() -> None:
    base = standard_stats("fighter")
    result = apply_background_bonus(
        base,
        ("strength", "dexterity", "constitution"),
        "2+1",
        {"strength": 2, "constitution": 1},
    )
    assert (result["strength"], result["constitution"]) == (17, 14)
    with pytest.raises(DomainValidationError):
        apply_background_bonus(base, ("strength", "strength", "wisdom"), "1+1+1", {})


def test_drop_lowest_uses_first_minimum_deterministically() -> None:
    assert drop_lowest((2, 2, 5, 6)) == (0, 13)


def test_species_choices_and_derived_sheet() -> None:
    validate_species_choices(
        "elf",
        {"lineage": "wood", "spellcasting_stat": "wisdom", "keen_senses": "survival"},
    )
    sheet = species_sheet(
        "elf",
        {"lineage": "wood", "spellcasting_stat": "wisdom", "keen_senses": "survival"},
        1,
    )
    assert sheet["speed"] == 35
    assert DRAGON_DAMAGE["red"] == "fire"
    with pytest.raises(DomainValidationError):
        validate_species_choices("gnome", {"lineage": "forest"})


def test_level_one_derived_values_and_dwarf_toughness() -> None:
    stats = standard_stats("wizard")
    normal = derived_statistics("wizard", "elf", stats)
    dwarf = derived_statistics("wizard", "dwarf", stats)
    assert normal == {"max_hp": 7, "armor_class": 11, "initiative": 1, "proficiency_bonus": 2}
    assert dwarf["max_hp"] == normal["max_hp"] + 1


def test_equipment_compatibility_dynamic_slots_and_decimal_weight() -> None:
    assert slot_is_compatible(SlotCompatibility.HAND, "left_hand")
    assert not slot_is_compatible(SlotCompatibility.ARMOR, "right_hand")
    assert visible_other_slot_count(set()) == 1
    assert visible_other_slot_count({"other_1", "other_3"}) == 4
    assert inventory_weight([(Decimal("0.125"), 3), (Decimal("1.5"), 2)]) == Decimal("3.375")


def test_character_equipment_slot_conflict_and_archive_guard() -> None:
    now = datetime.now(UTC)
    items = [
        InventoryItem(
            "i1",
            "d1",
            "Меч",
            False,
            False,
            1,
            False,
            None,
            now,
            Decimal("1.5"),
            SlotCompatibility.HAND,
        ),
        InventoryItem(
            "i2",
            "d2",
            "Факел",
            False,
            False,
            1,
            False,
            None,
            now,
            Decimal("0.5"),
            SlotCompatibility.HAND,
        ),
    ]
    character = Character(
        "c", "d", "r", "p", "Герой", "simple-v1", standard_stats("fighter"), [], 1, now, items
    )
    character.equip("i1", "left_hand", expected_version=1)
    with pytest.raises(StateConflictError, match="occupied"):
        character.equip("i2", "left_hand", expected_version=2)
    with pytest.raises(StateConflictError) as error:
        character.archive(now=now, expected_version=2, active_encounter=True)
    assert error.value.code == "character_in_active_encounter"


def test_character_owner_can_edit_health_values() -> None:
    now = datetime.now(UTC)
    character = Character(
        "c", "d", "r", "p", "Герой", "simple-v1", standard_stats("fighter"), [], 1, now
    )
    character.max_hp = 12
    character.edit_health(current_hp=7, temporary_hp=3, expected_version=1)
    assert (character.current_hp, character.temporary_hp, character.version) == (7, 3, 2)
    with pytest.raises(DomainValidationError):
        character.edit_health(current_hp=13, temporary_hp=0, expected_version=2)
