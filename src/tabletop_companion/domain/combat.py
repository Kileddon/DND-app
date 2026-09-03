from __future__ import annotations

import re
from collections.abc import Callable, Iterable
from dataclasses import dataclass
from datetime import datetime
from enum import StrEnum

from tabletop_companion.domain.errors import (
    DomainValidationError,
    StateConflictError,
)
from tabletop_companion.domain.events import DomainEvent


class CombatStatus(StrEnum):
    PREPARATION = "PREPARATION"
    ACTIVE = "ACTIVE"
    PAUSED = "PAUSED"
    COMPLETED = "COMPLETED"


class CombatantKind(StrEnum):
    CHARACTER = "character"
    MONSTER = "monster"


class HealthActionType(StrEnum):
    DAMAGE = "damage"
    HEALING = "healing"
    TEMPORARY_HP = "temporary_hp"
    PREVENTION = "prevention"


class RollVisibility(StrEnum):
    PUBLIC = "public"
    PRIVATE = "private"
    SECRET = "secret"
    DELAYED = "delayed"


class RollMode(StrEnum):
    DIGITAL = "digital"
    PHYSICAL = "physical"


class RollSelection(StrEnum):
    NEUTRAL = "neutral"
    ADVANTAGE = "advantage"
    DISADVANTAGE = "disadvantage"


@dataclass(frozen=True, slots=True)
class CombatCondition:
    id: str
    name: str
    description: str
    source_id: str | None
    visible_to_players: bool
    created_at: datetime


@dataclass(slots=True)
class Combatant:
    id: str
    combat_id: str
    entry_id: str
    kind: CombatantKind
    reference_id: str | None
    name: str
    max_hp: int
    current_hp: int
    temporary_hp: int
    armor_class: int
    conditions: list[CombatCondition]
    show_wound_state: bool
    wound_override: str | None
    version: int
    created_at: datetime

    def __post_init__(self) -> None:
        if self.max_hp <= 0:
            raise DomainValidationError("Maximum HP must be positive.")
        if not 0 <= self.current_hp <= self.max_hp:
            raise DomainValidationError("Current HP must be between zero and maximum HP.")
        if self.temporary_hp < 0:
            raise DomainValidationError("Temporary HP must not be negative.")
        if self.armor_class < 0:
            raise DomainValidationError("Armor class must not be negative.")

    def ensure_version(self, expected_version: int) -> None:
        if self.version != expected_version:
            raise StateConflictError(
                "Combatant version is stale.",
                details={"expected_version": expected_version, "current_version": self.version},
            )

    def apply_health(
        self,
        action: HealthActionType,
        amount: int,
        *,
        prevented: int = 0,
        expected_version: int,
    ) -> HealthResult:
        self.ensure_version(expected_version)
        if amount < 0:
            raise DomainValidationError("Health action amount must not be negative.")
        if prevented < 0 or prevented > amount:
            raise DomainValidationError("Prevented damage must be between zero and amount.")
        before_hp, before_temp = self.current_hp, self.temporary_hp
        actual = 0
        excess = 0
        if action is HealthActionType.DAMAGE:
            incoming = amount - prevented
            absorbed = min(self.temporary_hp, incoming)
            self.temporary_hp -= absorbed
            remaining = incoming - absorbed
            hp_damage = min(self.current_hp, remaining)
            self.current_hp -= hp_damage
            actual = absorbed + hp_damage
            excess = remaining - hp_damage
        elif action is HealthActionType.HEALING:
            if prevented:
                raise DomainValidationError("Healing cannot include prevented damage.")
            actual = min(amount, self.max_hp - self.current_hp)
            self.current_hp += actual
            excess = amount - actual
        elif action is HealthActionType.TEMPORARY_HP:
            if prevented:
                raise DomainValidationError("Temporary HP cannot include prevented damage.")
            previous = self.temporary_hp
            self.temporary_hp = max(previous, amount)
            actual = self.temporary_hp - previous
        else:
            if prevented:
                raise DomainValidationError("Prevention uses amount as the prevented value.")
            prevented = amount
        self.version += 1
        return HealthResult(
            target_id=self.id,
            entered=amount,
            actual=actual,
            prevented=prevented,
            excess=excess,
            hp_delta=self.current_hp - before_hp,
            temporary_hp_delta=self.temporary_hp - before_temp,
            current_hp=self.current_hp,
            temporary_hp=self.temporary_hp,
            version=self.version,
        )

    def apply_compensation(
        self, *, hp_delta: int, temporary_hp_delta: int, expected_version: int
    ) -> None:
        self.ensure_version(expected_version)
        next_hp = self.current_hp + hp_delta
        next_temp = self.temporary_hp + temporary_hp_delta
        if not 0 <= next_hp <= self.max_hp or next_temp < 0:
            raise StateConflictError(
                "The health action can no longer be compensated without overwriting later state."
            )
        self.current_hp = next_hp
        self.temporary_hp = next_temp
        self.version += 1

    def add_condition(self, condition: CombatCondition, *, expected_version: int) -> None:
        self.ensure_version(expected_version)
        if any(item.id == condition.id for item in self.conditions):
            raise StateConflictError("Condition already exists.")
        self.conditions.append(condition)
        self.version += 1

    def remove_condition(self, condition_id: str, *, expected_version: int) -> CombatCondition:
        self.ensure_version(expected_version)
        condition = next((item for item in self.conditions if item.id == condition_id), None)
        if condition is None:
            raise DomainValidationError("Condition does not belong to the combatant.")
        self.conditions.remove(condition)
        self.version += 1
        return condition

    def wound_state(self) -> str | None:
        if not self.show_wound_state:
            return None
        if self.wound_override:
            return self.wound_override
        if self.current_hp == 0:
            return "мёртв"
        percentage = self.current_hp * 100 / self.max_hp
        if percentage < 20:
            return "при смерти"
        if percentage < 40:
            return "едва держится"
        if self.current_hp == self.max_hp:
            return "без единой царапины"
        return "ранен"


@dataclass(frozen=True, slots=True)
class HealthResult:
    target_id: str
    entered: int
    actual: int
    prevented: int
    excess: int
    hp_delta: int
    temporary_hp_delta: int
    current_hp: int
    temporary_hp: int
    version: int


@dataclass(frozen=True, slots=True)
class InitiativeEntry:
    id: str
    name: str
    initiative: int
    position: int
    combatant_ids: tuple[str, ...]


@dataclass(frozen=True, slots=True)
class MonsterTemplate:
    id: str
    room_id: str
    name: str
    image_url: str | None
    max_hp: int
    current_hp: int
    armor_class: int
    notes: str
    conditions: tuple[str, ...]
    actions: tuple[str, ...]
    created_at: datetime

    def __post_init__(self) -> None:
        if self.max_hp <= 0 or not 0 <= self.current_hp <= self.max_hp:
            raise DomainValidationError("Monster HP is invalid.")
        if self.armor_class < 0:
            raise DomainValidationError("Monster armor class must not be negative.")


@dataclass(frozen=True, slots=True)
class EventCompensation:
    original_event_id: str
    compensation_event_id: str
    replacement_event_id: str | None
    created_at: datetime


@dataclass(slots=True)
class Combat:
    id: str
    room_id: str
    session_id: str
    status: CombatStatus
    round_number: int
    current_entry_id: str | None
    entries: list[InitiativeEntry]
    version: int
    created_at: datetime
    updated_at: datetime
    started_at: datetime | None = None
    completed_at: datetime | None = None

    def ensure_version(self, expected_version: int) -> None:
        if expected_version != self.version:
            raise StateConflictError(
                "Combat version is stale.",
                details={"expected_version": expected_version, "current_version": self.version},
            )

    def add_entry(
        self,
        entry: InitiativeEntry,
        *,
        expected_version: int,
        now: datetime,
        late_join: bool = False,
    ) -> None:
        self.add_entries([entry], expected_version=expected_version, now=now, late_join=late_join)

    def add_entries(
        self,
        entries: list[InitiativeEntry],
        *,
        expected_version: int,
        now: datetime,
        late_join: bool = False,
    ) -> None:
        self.ensure_version(expected_version)
        if self.status is CombatStatus.COMPLETED:
            raise StateConflictError("Completed combat cannot accept participants.")
        if self.status is not CombatStatus.PREPARATION and not late_join:
            raise StateConflictError(
                "Participants can only be added before combat or as late join."
            )
        new_ids = [item.id for item in entries]
        if len(set(new_ids)) != len(new_ids) or any(item.id in new_ids for item in self.entries):
            raise StateConflictError("Initiative entry already exists.")
        self.entries.extend(entries)
        self._sort_entries()
        self._touch(now)

    def remove_entry(self, entry_id: str, *, expected_version: int, now: datetime) -> None:
        self.ensure_version(expected_version)
        if self.status is not CombatStatus.PREPARATION:
            raise StateConflictError("Participants can only be removed before combat starts.")
        original = len(self.entries)
        self.entries = [item for item in self.entries if item.id != entry_id]
        if len(self.entries) == original:
            raise DomainValidationError("Initiative entry was not found.")
        self._reposition()
        self._touch(now)

    def reorder(self, entry_ids: list[str], *, expected_version: int, now: datetime) -> None:
        self.ensure_version(expected_version)
        if set(entry_ids) != {item.id for item in self.entries} or len(entry_ids) != len(
            self.entries
        ):
            raise DomainValidationError("Initiative order must contain every entry exactly once.")
        by_id = {item.id: item for item in self.entries}
        self.entries = [
            InitiativeEntry(
                id=by_id[entry_id].id,
                name=by_id[entry_id].name,
                initiative=by_id[entry_id].initiative,
                position=position,
                combatant_ids=by_id[entry_id].combatant_ids,
            )
            for position, entry_id in enumerate(entry_ids)
        ]
        self._touch(now)

    def start(self, *, expected_version: int, now: datetime) -> None:
        self.ensure_version(expected_version)
        if self.status is not CombatStatus.PREPARATION:
            raise StateConflictError("Only prepared combat can start.")
        if not self.entries:
            raise StateConflictError("Combat needs at least one initiative entry.")
        self.status = CombatStatus.ACTIVE
        self.round_number = 1
        self.current_entry_id = self.entries[0].id
        self.started_at = now
        self._touch(now)

    def pause(self, *, expected_version: int, now: datetime) -> None:
        self.ensure_version(expected_version)
        if self.status is not CombatStatus.ACTIVE:
            raise StateConflictError("Only active combat can pause.")
        self.status = CombatStatus.PAUSED
        self._touch(now)

    def resume(self, *, expected_version: int, now: datetime) -> None:
        self.ensure_version(expected_version)
        if self.status is not CombatStatus.PAUSED:
            raise StateConflictError("Only paused combat can resume.")
        self.status = CombatStatus.ACTIVE
        self._touch(now)

    def complete(self, *, expected_version: int, now: datetime) -> None:
        self.ensure_version(expected_version)
        if self.status not in {CombatStatus.ACTIVE, CombatStatus.PAUSED}:
            raise StateConflictError("Only started combat can complete.")
        self.status = CombatStatus.COMPLETED
        self.completed_at = now
        self._touch(now)

    def move(self, direction: int, *, expected_version: int, now: datetime) -> None:
        self.ensure_version(expected_version)
        if self.status is not CombatStatus.ACTIVE or self.current_entry_id is None:
            raise StateConflictError("Turns can only move during active combat.")
        current = next(
            index for index, item in enumerate(self.entries) if item.id == self.current_entry_id
        )
        next_index = (current + direction) % len(self.entries)
        if direction > 0 and next_index <= current:
            self.round_number += 1
        elif direction < 0 and next_index >= current and self.round_number > 1:
            self.round_number -= 1
        self.current_entry_id = self.entries[next_index].id
        self._touch(now)

    def _sort_entries(self) -> None:
        self.entries.sort(key=lambda item: (-item.initiative, item.position, item.id))
        self._reposition()

    def _reposition(self) -> None:
        self.entries = [
            InitiativeEntry(
                id=item.id,
                name=item.name,
                initiative=item.initiative,
                position=index,
                combatant_ids=item.combatant_ids,
            )
            for index, item in enumerate(self.entries)
        ]

    def _touch(self, now: datetime) -> None:
        self.version += 1
        self.updated_at = now


@dataclass(frozen=True, slots=True)
class DiceExpression:
    count: int
    sides: int
    modifier: int = 0

    _PATTERN = re.compile(r"^(?:(\d*)d(\d+))([+-]\d+)?$", re.IGNORECASE)

    @classmethod
    def parse(cls, value: str) -> DiceExpression:
        match = cls._PATTERN.fullmatch(value.strip())
        if match is None:
            raise DomainValidationError("Dice expression is invalid.")
        count = int(match.group(1) or 1)
        sides = int(match.group(2))
        modifier = int(match.group(3) or 0)
        if not 1 <= count <= 100 or not 2 <= sides <= 1000:
            raise DomainValidationError("Dice expression is outside allowed limits.")
        return cls(count=count, sides=sides, modifier=modifier)

    def roll(self, randint: Callable[[int, int], int]) -> tuple[tuple[int, ...], int]:
        values = tuple(randint(1, self.sides) for _ in range(self.count))
        return values, sum(values) + self.modifier

    def roll_selected(
        self, selection: RollSelection, randint: Callable[[int, int], int]
    ) -> tuple[tuple[tuple[int, ...], ...], tuple[int, ...], int]:
        attempt_count = 1 if selection is RollSelection.NEUTRAL else 2
        rolled = tuple(self.roll(randint) for _ in range(attempt_count))
        attempts = tuple(item[0] for item in rolled)
        totals = tuple(item[1] for item in rolled)
        if selection is RollSelection.ADVANTAGE:
            selected = max(range(attempt_count), key=totals.__getitem__)
        elif selection is RollSelection.DISADVANTAGE:
            selected = min(range(attempt_count), key=totals.__getitem__)
        else:
            selected = 0
        return attempts, totals, selected

    def normalized(self) -> str:
        modifier = f"{self.modifier:+d}" if self.modifier else ""
        return f"{self.count}d{self.sides}{modifier}"


@dataclass(slots=True)
class DiceRoll:
    id: str
    combat_id: str | None
    room_id: str
    actor_id: str
    character_id: str | None
    expression: str
    mode: RollMode
    visibility: RollVisibility
    recipient_player_id: str | None
    values: tuple[int, ...]
    original_result: int
    result: int
    reason: str | None
    action_event_id: str | None
    created_at: datetime
    revealed_at: datetime | None = None
    selection: RollSelection = RollSelection.NEUTRAL
    attempts: tuple[tuple[int, ...], ...] = ()
    attempt_totals: tuple[int, ...] = ()
    selected_attempt: int = 0

    def edit(self, value: int, reason: str) -> None:
        if not reason.strip():
            raise DomainValidationError("A roll edit requires a reason.")
        self.result = value
        self.reason = reason.strip()

    def reveal(self, now: datetime) -> None:
        if self.visibility is not RollVisibility.DELAYED or self.revealed_at is not None:
            raise StateConflictError("Only an unrevealed delayed roll can be revealed.")
        self.visibility = RollVisibility.PUBLIC
        self.revealed_at = now


def build_combat_report(events: Iterable[DomainEvent]) -> dict[str, object]:
    def integer(value: object) -> int:
        return value if isinstance(value, int) else 0

    report: dict[str, object] = {
        "damage_by_source": {},
        "damage_by_target": {},
        "damage_to_monsters": 0,
        "damage_to_allies": 0,
        "damage_to_self": 0,
        "healing": 0,
        "prevented_damage": 0,
        "excess_damage": 0,
        "critical_hits": 0,
    }
    by_source = report["damage_by_source"]
    by_target = report["damage_by_target"]
    assert isinstance(by_source, dict) and isinstance(by_target, dict)
    for event in events:
        delta = event.payload.get("report_delta")
        if not isinstance(delta, dict):
            continue
        sign = integer(delta.get("sign", 1))
        source_id = str(delta.get("source_id") or "environment")
        critical = int(bool(delta.get("critical")))
        for target in delta.get("targets", []):
            if not isinstance(target, dict):
                continue
            target_id = str(target["target_id"])
            damage = integer(target.get("damage", 0)) * sign
            by_source[source_id] = integer(by_source.get(source_id, 0)) + damage
            by_target[target_id] = integer(by_target.get(target_id, 0)) + damage
            relation = target.get("relation")
            key = {
                "monster": "damage_to_monsters",
                "ally": "damage_to_allies",
                "self": "damage_to_self",
            }.get(str(relation))
            if key:
                report[key] = integer(report[key]) + damage
            report["healing"] = (
                integer(report["healing"]) + integer(target.get("healing", 0)) * sign
            )
            report["prevented_damage"] = (
                integer(report["prevented_damage"]) + integer(target.get("prevented", 0)) * sign
            )
            report["excess_damage"] = (
                integer(report["excess_damage"]) + integer(target.get("excess", 0)) * sign
            )
        report["critical_hits"] = integer(report["critical_hits"]) + critical * sign
    return report


BUILTIN_CONDITIONS: dict[str, str] = {
    "blinded": "Ослеплён",
    "charmed": "Очарован",
    "frightened": "Испуган",
    "poisoned": "Отравлен",
    "prone": "Сбит с ног",  # noqa: RUF001
    "stunned": "Оглушён",
}
