from __future__ import annotations

# ruff: noqa: RUF001
from dataclasses import dataclass
from typing import Final

from tabletop_companion.domain.errors import DomainValidationError


@dataclass(frozen=True, slots=True)
class SpeciesFeature:
    id: str
    name: str
    description: str
    required_level: int = 1


@dataclass(frozen=True, slots=True)
class SpeciesDefinition:
    id: str
    name: str
    description: str
    source_url: str
    creature_type: str
    sizes: tuple[str, ...]
    speed: int
    features: tuple[SpeciesFeature, ...]
    lineages: tuple[str, ...] = ()


GNOME_FEATURES = (
    SpeciesFeature("darkvision", "Тёмное зрение", "У вас есть Тёмное зрение дальностью 60 футов."),
    SpeciesFeature(
        "gnomish_cunning",
        "Гномья хитрость",
        "Вы совершаете с Преимуществом спасброски Интеллекта, Мудрости и Харизмы.",
    ),
    SpeciesFeature(
        "forest_lineage",
        "Лесной гном",
        "Вы знаете Малую иллюзию и всегда имеете подготовленным Разговор с животными.",
    ),
    SpeciesFeature(
        "rock_lineage",
        "Скальный гном",
        "Вы знаете Починку и Фокусы и можете создавать Крошечные заводные устройства.",
    ),
)

DWARF_FEATURES = (
    SpeciesFeature("darkvision", "Тёмное зрение", "У вас есть Тёмное зрение дальностью 120 футов."),
    SpeciesFeature(
        "dwarven_resilience",
        "Дварфийская устойчивость",
        "Вы сопротивляетесь Яду и лучше противостоите Отравлению.",
    ),
    SpeciesFeature(
        "dwarven_toughness",
        "Дварфийская крепость",
        "Ваш максимум Хитов увеличивается на 1 за каждый уровень.",
    ),
    SpeciesFeature(
        "stonecunning",
        "Знание камня",
        "На каменной поверхности вы можете временно получить Чувство вибрации 60 футов.",
    ),
)

DRAGONBORN_FEATURES = (
    SpeciesFeature(
        "draconic_ancestry",
        "Наследие драконов",
        "Наследие определяет тип урона дыхания и сопротивления.",
    ),
    SpeciesFeature(
        "breath_weapon",
        "Оружие дыхания",
        "Замените атаку выдохом магической энергии в конусе или линии.",
    ),
    SpeciesFeature(
        "damage_resistance",
        "Сопротивление урону",
        "Вы сопротивляетесь типу урона выбранного наследия.",
    ),
    SpeciesFeature("darkvision", "Тёмное зрение", "У вас есть Тёмное зрение дальностью 60 футов."),
    SpeciesFeature(
        "draconic_flight",
        "Драконий полёт",
        "Вы временно выпускаете призрачные крылья на 10 минут.",
        5,
    ),
)

ORC_FEATURES = (
    SpeciesFeature(
        "adrenaline_rush",
        "Выброс адреналина",
        "Бонусным действием совершите Рывок и получите временные Хиты.",
    ),
    SpeciesFeature("darkvision", "Тёмное зрение", "У вас есть Тёмное зрение дальностью 120 футов."),
    SpeciesFeature(
        "relentless_endurance",
        "Непоколебимая стойкость",
        "Вместо падения до 0 Хитов вы можете остаться с 1 Хитом.",
    ),
)

HALFLING_FEATURES = (
    SpeciesFeature(
        "brave", "Храбрый", "Вы совершаете с Преимуществом спасброски против состояния Испуганный."
    ),
    SpeciesFeature(
        "halfling_nimbleness",
        "Проворство полуросликов",
        "Вы можете перемещаться через пространство более крупного существа.",
    ),
    SpeciesFeature(
        "luck",
        "Удача",
        "Когда на к20 выпадает 1, вы можете перебросить кость и использовать новый результат.",
    ),
    SpeciesFeature(
        "naturally_stealthy",
        "Естественная скрытность",
        "Вы можете Затаиться за существом, которое больше вас хотя бы на размер.",
    ),
)

HUMAN_FEATURES = (
    SpeciesFeature(
        "resourceful", "Находчивый", "После Долгого отдыха вы получаете Героическое вдохновение."
    ),
    SpeciesFeature("skillful", "Умелый", "Вы получаете владение одним выбранным навыком."),
    SpeciesFeature("versatile", "Гибкий", "Вы получаете черту происхождения Одарённый."),
)

ELF_FEATURES = (
    SpeciesFeature("darkvision", "Тёмное зрение", "У вас есть Тёмное зрение дальностью 60 футов."),
    SpeciesFeature(
        "fey_ancestry",
        "Наследие фей",
        "Вы совершаете с Преимуществом спасброски против состояния Очарованный.",
    ),
    SpeciesFeature(
        "keen_senses",
        "Обострённые чувства",
        "Вы владеете Восприятием, Выживанием или Проницательностью.",
    ),
    SpeciesFeature("trance", "Транс", "Вы не спите и завершаете Долгий отдых за 4 часа медитации."),
    SpeciesFeature(
        "high_elf_1",
        "Высший эльф: Фокусы",
        "Вы знаете заговор Фокусы и можете менять его после Долгого отдыха.",
    ),
    SpeciesFeature(
        "high_elf_3",
        "Высший эльф: Обнаружение магии",
        "У вас всегда подготовлено Обнаружение магии.",
        3,
    ),
    SpeciesFeature(
        "high_elf_5", "Высший эльф: Туманный шаг", "У вас всегда подготовлен Туманный шаг.", 5
    ),
    SpeciesFeature(
        "drow_1",
        "Дроу: магия Подземья",
        "Тёмное зрение увеличивается до 120 футов; вы знаете Пляшущие огоньки.",
    ),
    SpeciesFeature("drow_3", "Дроу: Огонь фей", "У вас всегда подготовлен Огонь фей.", 3),
    SpeciesFeature("drow_5", "Дроу: Тьма", "У вас всегда подготовлена Тьма.", 5),
    SpeciesFeature(
        "wood_elf_1",
        "Лесной эльф: быстрота",
        "Скорость увеличивается до 35 футов; вы знаете Искусство друидов.",
    ),
    SpeciesFeature("wood_elf_3", "Лесной эльф: Скороход", "У вас всегда подготовлен Скороход.", 3),
    SpeciesFeature(
        "wood_elf_5",
        "Лесной эльф: Бесследное передвижение",
        "У вас всегда подготовлено Бесследное передвижение.",
        5,
    ),
)

SPECIES: Final = (
    SpeciesDefinition(
        "gnome",
        "Гном",
        "Волшебный миниатюрный народ изобретателей и иллюзионистов, живущий около 425 лет.",
        "https://next.dnd.su/species/gnome",
        "Гуманоид",
        ("small",),
        30,
        GNOME_FEATURES,
        ("forest", "rock"),
    ),
    SpeciesDefinition(
        "dwarf",
        "Дварф",
        "Стойкий народ камня и металла, созданный божеством кузни и живущий около 350 лет.",
        "https://next.dnd.su/species/dwarf",
        "Гуманоид",
        ("medium",),
        30,
        DWARF_FEATURES,
    ),
    SpeciesDefinition(
        "dragonborn",
        "Драконорождённый",
        "Наследники хроматических и металлических драконов, похожие на бескрылых "
        "двуногих драконов.",
        "https://next.dnd.su/species/dragonborn",
        "Гуманоид",
        ("medium",),
        30,
        DRAGONBORN_FEATURES,
        ("white", "bronze", "green", "gold", "red", "brass", "copper", "silver", "blue", "black"),
    ),
    SpeciesDefinition(
        "orc",
        "Орк",
        "Выносливый и решительный народ странников, несущий дары Груумша.",
        "https://next.dnd.su/species/orc",
        "Гуманоид",
        ("medium",),
        30,
        ORC_FEATURES,
    ),
    SpeciesDefinition(
        "halfling",
        "Полурослик",
        "Небольшой, храбрый и удачливый народ дома, общины и дальних путешествий.",
        "https://next.dnd.su/species/halfling",
        "Гуманоид",
        ("small",),
        30,
        HALFLING_FEATURES,
    ),
    SpeciesDefinition(
        "human",
        "Человек",
        "Многочисленные и разнообразные жители мультивселенной, известные честолюбием "
        "и находчивостью.",
        "https://next.dnd.su/species/human",
        "Гуманоид",
        ("medium", "small"),
        30,
        HUMAN_FEATURES,
    ),
    SpeciesDefinition(
        "elf",
        "Эльф",
        "Созданный Кореллоном долгоживущий народ Страны Фей, меняющийся под влиянием окружения.",
        "https://next.dnd.su/species/elf",
        "Гуманоид",
        ("medium",),
        30,
        ELF_FEATURES,
        ("high", "drow", "wood"),
    ),
)

DRAGON_DAMAGE: Final = {
    "white": "cold",
    "bronze": "lightning",
    "green": "poison",
    "gold": "fire",
    "red": "fire",
    "brass": "fire",
    "copper": "acid",
    "silver": "cold",
    "blue": "lightning",
    "black": "acid",
}


def validate_species_choices(species_id: str, choices: dict[str, str]) -> None:
    species = next((item for item in SPECIES if item.id == species_id), None)
    if species is None:
        raise DomainValidationError("Unknown character race.", details={"race_id": species_id})
    required: dict[str, tuple[str, ...]] = {
        "gnome": {
            "lineage": species.lineages,
            "spellcasting_stat": ("intelligence", "wisdom", "charisma"),
        },
        "dragonborn": {"lineage": species.lineages},
        "human": {
            "size": species.sizes,
            "skill": ("perception", "survival", "insight", "athletics", "arcana", "stealth"),
        },
        "elf": {
            "lineage": species.lineages,
            "spellcasting_stat": ("intelligence", "wisdom", "charisma"),
            "keen_senses": ("perception", "survival", "insight"),
        },
    }.get(species_id, {})
    if set(choices) != set(required) or any(
        choices[key] not in values for key, values in required.items()
    ):
        raise DomainValidationError(
            "Required racial choices are incomplete or invalid.", code="invalid_species_choices"
        )


def species_sheet(species_id: str, choices: dict[str, str], level: int) -> dict[str, object]:
    validate_species_choices(species_id, choices)
    species = next(item for item in SPECIES if item.id == species_id)
    speed = 35 if species_id == "elf" and choices.get("lineage") == "wood" else species.speed
    darkvision = (
        120
        if species_id in {"dwarf", "orc"}
        or (species_id == "elf" and choices.get("lineage") == "drow")
        else 60
        if species_id in {"gnome", "dragonborn", "elf"}
        else 0
    )
    return {
        "size": choices.get("size", species.sizes[0]),
        "speed": speed,
        "darkvision": darkvision,
        "features": [
            {
                "id": feature.id,
                "name": feature.name,
                "description": feature.description,
                "source": species.source_url,
                "required_level": feature.required_level,
                "available": level >= feature.required_level,
            }
            for feature in species.features
            if not feature.id.startswith(("forest_", "rock_", "high_elf_", "drow_", "wood_elf_"))
            or feature.id.startswith(
                choices.get("lineage", "none")
                .replace("forest", "forest")
                .replace("rock", "rock")
                .replace("high", "high_elf")
                .replace("wood", "wood_elf")
                + "_"
            )
        ],
    }
