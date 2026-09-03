from __future__ import annotations

from datetime import UTC, datetime

import pytest

from tabletop_companion.domain.combat import (
    Combat,
    Combatant,
    CombatantKind,
    CombatStatus,
    DiceExpression,
    DiceRoll,
    HealthActionType,
    InitiativeEntry,
    RollMode,
    RollVisibility,
)
from tabletop_companion.domain.errors import DomainValidationError, StateConflictError

NOW = datetime(2026, 9, 2, tzinfo=UTC)


def combatant(*, hp: int = 20, temporary: int = 0) -> Combatant:
    return Combatant(
        id="actor-1",
        combat_id="combat-1",
        entry_id="entry-1",
        kind=CombatantKind.CHARACTER,
        reference_id="character-1",
        name="Aria",
        max_hp=20,
        current_hp=hp,
        temporary_hp=temporary,
        armor_class=14,
        conditions=[],
        show_wound_state=True,
        wound_override=None,
        version=1,
        created_at=NOW,
    )


def test_damage_prevention_temporary_hp_and_overkill() -> None:
    target = combatant(hp=8, temporary=3)
    result = target.apply_health(HealthActionType.DAMAGE, 20, prevented=2, expected_version=1)
    assert (result.actual, result.prevented, result.excess) == (11, 2, 7)
    assert (target.current_hp, target.temporary_hp) == (0, 0)
    assert (result.hp_delta, result.temporary_hp_delta) == (-8, -3)


def test_healing_is_bounded_and_temporary_hp_does_not_stack() -> None:
    target = combatant(hp=10, temporary=4)
    healed = target.apply_health(HealthActionType.HEALING, 15, expected_version=1)
    temporary = target.apply_health(HealthActionType.TEMPORARY_HP, 3, expected_version=2)
    upgraded = target.apply_health(HealthActionType.TEMPORARY_HP, 7, expected_version=3)
    assert (healed.actual, healed.excess) == (10, 5)
    assert temporary.actual == 0
    assert upgraded.actual == 3
    assert target.temporary_hp == 7


@pytest.mark.parametrize(
    ("hp", "label"),
    [
        (20, "без единой царапины"),
        (10, "ранен"),
        (6, "едва держится"),
        (2, "при смерти"),
        (0, "мёртв"),
    ],
)
def test_monster_wound_categories(hp: int, label: str) -> None:
    assert combatant(hp=hp).wound_state() == label


def test_combat_lifecycle_turns_reorder_and_late_join() -> None:
    combat = Combat(
        id="combat-1",
        room_id="room-1",
        session_id="session-1",
        status=CombatStatus.PREPARATION,
        round_number=0,
        current_entry_id=None,
        entries=[],
        version=1,
        created_at=NOW,
        updated_at=NOW,
    )
    first = InitiativeEntry("entry-1", "Aria", 10, 0, ("actor-1",))
    second = InitiativeEntry("entry-2", "Goblin", 15, 1, ("actor-2",))
    combat.add_entry(first, expected_version=1, now=NOW)
    combat.add_entry(second, expected_version=2, now=NOW)
    combat.reorder(["entry-1", "entry-2"], expected_version=3, now=NOW)
    combat.start(expected_version=4, now=NOW)
    assert (combat.round_number, combat.current_entry_id) == (1, "entry-1")
    combat.move(1, expected_version=5, now=NOW)
    combat.move(1, expected_version=6, now=NOW)
    assert (combat.round_number, combat.current_entry_id) == (2, "entry-1")
    combat.move(-1, expected_version=7, now=NOW)
    assert (combat.round_number, combat.current_entry_id) == (1, "entry-2")
    combat.add_entry(
        InitiativeEntry("entry-3", "Late", 5, 2, ("actor-3",)),
        expected_version=8,
        now=NOW,
        late_join=True,
    )
    with pytest.raises(StateConflictError):
        combat.remove_entry("entry-3", expected_version=9, now=NOW)


@pytest.mark.parametrize(
    ("text", "normalized", "values", "total"),
    [("d20", "1d20", (4,), 4), ("2d6+3", "2d6+3", (4, 4), 11), ("1d20-1", "1d20-1", (4,), 3)],
)
def test_dice_expression(text: str, normalized: str, values: tuple[int, ...], total: int) -> None:
    expression = DiceExpression.parse(text)
    rolled, result = expression.roll(lambda _low, _high: 4)
    assert expression.normalized() == normalized
    assert rolled == values
    assert result == total


def test_invalid_dice_expression_is_rejected() -> None:
    with pytest.raises(DomainValidationError):
        DiceExpression.parse("2d1")


def test_delayed_roll_keeps_original_value_when_edited_and_can_be_revealed() -> None:
    roll = DiceRoll(
        id="roll-1",
        combat_id="combat-1",
        room_id="room-1",
        actor_id="actor-1",
        character_id="character-1",
        expression="1d20",
        mode=RollMode.DIGITAL,
        visibility=RollVisibility.DELAYED,
        recipient_player_id=None,
        values=(7,),
        original_result=7,
        result=7,
        reason=None,
        action_event_id=None,
        created_at=NOW,
    )
    roll.edit(12, "Бонус был пропущен")
    roll.reveal(NOW)
    assert (roll.original_result, roll.result, roll.reason) == (
        7,
        12,
        "Бонус был пропущен",
    )
    assert roll.visibility is RollVisibility.PUBLIC
    with pytest.raises(StateConflictError):
        roll.reveal(NOW)


def test_roll_edit_requires_a_reason() -> None:
    roll = DiceRoll(
        "roll-1",
        "combat-1",
        "room-1",
        "actor-1",
        None,
        "1d20",
        RollMode.PHYSICAL,
        RollVisibility.PUBLIC,
        None,
        (),
        15,
        15,
        None,
        None,
        NOW,
    )
    with pytest.raises(DomainValidationError):
        roll.edit(16, "  ")
