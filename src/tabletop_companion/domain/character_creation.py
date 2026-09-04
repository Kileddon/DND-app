from __future__ import annotations

from dataclasses import dataclass
from decimal import Decimal
from enum import StrEnum
from typing import Final

from tabletop_companion.domain.errors import DomainValidationError

STAT_IDS: Final = (
    "strength",
    "dexterity",
    "constitution",
    "intelligence",
    "wisdom",
    "charisma",
)

STAT_NAMES: Final = {
    "strength": "Сила",
    "dexterity": "Ловкость",
    "constitution": "Телосложение",
    "intelligence": "Интеллект",
    "wisdom": "Мудрость",
    "charisma": "Харизма",
}

STAT_DESCRIPTIONS: Final = {
    "strength": "Измеряет физическую мощь персонажа и выносливость.",
    "constitution": (
        "Включает выносливость, натренированность, здоровье и физическую "
        "сопротивляемость невзгодам, ранениям и болезням."
    ),
    "dexterity": (
        "Включает координацию, проворство, скорость реакции, рефлексы и чувство равновесия."
    ),
    "intelligence": (
        "Представляет память, рассудительность и способность к обучению. Определяет число "
        "языков, которые может выучить персонаж."
    ),
    "wisdom": (
        "Описывает просвещённость, рассудительность, хитрость, силу воли, здравый смысл и интуицию."
    ),
    "charisma": "Измеряет убедительность, личностную притягательность и способность быть лидером.",
}


@dataclass(frozen=True, slots=True)
class CharacterClassDefinition:
    id: str
    name: str
    theme: str
    primary_stat: str
    difficulty: str
    hit_die: int


CLASS_DEFINITIONS: Final = (
    CharacterClassDefinition("bard", "Бард", "Выступления", "Харизма", "Высокая", 8),
    CharacterClassDefinition("barbarian", "Варвар", "Битвы", "Сила", "Средняя", 12),
    CharacterClassDefinition("fighter", "Воин", "Оружие", "Сила или Ловкость", "Низкая", 10),
    CharacterClassDefinition("wizard", "Волшебник", "Книги заклинаний", "Интеллект", "Средняя", 6),
    CharacterClassDefinition("druid", "Друид", "Природа", "Мудрость", "Высокая", 8),
    CharacterClassDefinition("cleric", "Жрец", "Боги", "Мудрость", "Средняя", 8),
    CharacterClassDefinition("warlock", "Колдун", "Оккультные знания", "Харизма", "Высокая", 8),
    CharacterClassDefinition(
        "monk", "Монах", "Безоружный бой", "Ловкость и Мудрость", "Высокая", 8
    ),
    CharacterClassDefinition("paladin", "Паладин", "Защита", "Сила и Харизма", "Средняя", 10),
    CharacterClassDefinition("rogue", "Плут", "Скрытность", "Ловкость", "Низкая", 8),
    CharacterClassDefinition(
        "ranger", "Следопыт", "Выживание", "Ловкость и Мудрость", "Средняя", 10
    ),
    CharacterClassDefinition("sorcerer", "Чародей", "Могущество", "Харизма", "Высокая", 6),
)

STANDARD_ARRAYS: Final = {
    "bard": (8, 14, 12, 13, 10, 15),
    "barbarian": (15, 13, 14, 10, 12, 8),
    "fighter": (15, 14, 13, 8, 10, 12),
    "wizard": (8, 12, 13, 15, 14, 10),
    "druid": (8, 12, 14, 13, 15, 10),
    "cleric": (14, 8, 13, 10, 15, 12),
    "warlock": (8, 14, 13, 12, 10, 15),
    "monk": (12, 15, 13, 10, 14, 8),
    "paladin": (15, 10, 13, 8, 12, 14),
    "rogue": (12, 15, 13, 14, 10, 8),
    "ranger": (12, 15, 13, 8, 14, 10),
    "sorcerer": (10, 13, 14, 8, 12, 15),
}

POINT_BUY_COSTS: Final = {8: 0, 9: 1, 10: 2, 11: 3, 12: 4, 13: 5, 14: 7, 15: 9}


class StatMethod(StrEnum):
    STANDARD = "standard"
    RANDOM = "random"
    POINT_BUY = "point_buy"


def ability_modifier(score: int) -> int:
    return (score - 10) // 2


def standard_stats(class_id: str) -> dict[str, int]:
    try:
        values = STANDARD_ARRAYS[class_id]
    except KeyError as error:
        raise DomainValidationError(
            "Unknown character class.", details={"class_id": class_id}
        ) from error
    return dict(zip(STAT_IDS, values, strict=True))


def point_buy_cost(stats: dict[str, int]) -> int:
    _ensure_complete_stats(stats)
    try:
        return sum(POINT_BUY_COSTS[value] for value in stats.values())
    except KeyError as error:
        raise DomainValidationError(
            "Point-buy values must be between 8 and 15.", code="invalid_point_buy"
        ) from error


def validate_point_buy(stats: dict[str, int]) -> None:
    if point_buy_cost(stats) != 27:
        raise DomainValidationError(
            "Point-buy must spend exactly 27 points.",
            details={"spent": point_buy_cost(stats), "required": 27},
            code="invalid_point_buy",
        )


def drop_lowest(values: tuple[int, int, int, int]) -> tuple[int, int]:
    if any(value < 1 or value > 6 for value in values):
        raise DomainValidationError("A 4d6 result contains an invalid die.")
    dropped_index = values.index(min(values))
    total = sum(value for index, value in enumerate(values) if index != dropped_index)
    return dropped_index, total


def apply_background_bonus(
    stats: dict[str, int], selected: tuple[str, str, str], pattern: str, allocations: dict[str, int]
) -> dict[str, int]:
    _ensure_complete_stats(stats)
    if len(set(selected)) != 3 or any(stat not in STAT_IDS for stat in selected):
        raise DomainValidationError(
            "Background requires three distinct abilities.", code="invalid_background"
        )
    expected = (
        sorted((2, 1)) if pattern == "2+1" else sorted((1, 1, 1)) if pattern == "1+1+1" else []
    )
    if sorted(allocations.values()) != expected or set(allocations) - set(selected):
        raise DomainValidationError(
            "Background bonuses do not match the selected pattern.", code="invalid_background"
        )
    result = dict(stats)
    for stat, bonus in allocations.items():
        result[stat] += bonus
        if result[stat] > 20:
            raise DomainValidationError(
                "An ability score cannot exceed 20.", code="ability_score_too_high"
            )
    return result


def derived_statistics(
    class_id: str, race_id: str, stats: dict[str, int], *, level: int = 1
) -> dict[str, int]:
    _ensure_complete_stats(stats)
    character_class = next((item for item in CLASS_DEFINITIONS if item.id == class_id), None)
    if character_class is None:
        raise DomainValidationError("Unknown character class.", details={"class_id": class_id})
    constitution = ability_modifier(stats["constitution"])
    dexterity = ability_modifier(stats["dexterity"])
    return {
        "max_hp": max(
            1, character_class.hit_die + constitution + (level if race_id == "dwarf" else 0)
        ),
        "armor_class": 10 + dexterity,
        "initiative": dexterity,
        "proficiency_bonus": 2 + max(0, (level - 1) // 4),
    }


class SlotCompatibility(StrEnum):
    HAND = "hand"
    ARMOR = "armor"
    OTHER = "other"
    NONE = "none"


EQUIPMENT_SLOTS: Final = (
    "left_hand",
    "right_hand",
    "armor",
    "other_1",
    "other_2",
    "other_3",
    "other_4",
)


def slot_is_compatible(compatibility: SlotCompatibility, slot: str) -> bool:
    if slot not in EQUIPMENT_SLOTS:
        return False
    return (
        (compatibility is SlotCompatibility.HAND and slot in {"left_hand", "right_hand"})
        or (compatibility is SlotCompatibility.ARMOR and slot == "armor")
        or (compatibility is SlotCompatibility.OTHER and slot.startswith("other_"))
    )


def visible_other_slot_count(occupied_slots: set[str]) -> int:
    indexes = [
        int(slot.removeprefix("other_")) for slot in occupied_slots if slot.startswith("other_")
    ]
    return min(4, max(1, max(indexes, default=0) + 1))


def inventory_weight(items: list[tuple[Decimal, int]]) -> Decimal:
    if any(weight < 0 or quantity < 0 for weight, quantity in items):
        raise DomainValidationError("Item weight and quantity must not be negative.")
    return sum((weight * quantity for weight, quantity in items), start=Decimal("0"))


def _ensure_complete_stats(stats: dict[str, int]) -> None:
    if set(stats) != set(STAT_IDS):
        raise DomainValidationError("All six ability scores are required.", code="incomplete_stats")
