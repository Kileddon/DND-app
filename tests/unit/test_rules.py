from __future__ import annotations

from collections.abc import Sequence
from dataclasses import replace
from random import Random

import pytest

from tabletop_companion.domain.errors import (
    ContentConfigurationError,
    DomainValidationError,
    StateConflictError,
)
from tabletop_companion.domain.rules import DEFAULT_RULESET, ability_modifier


def first_cards(population: Sequence[str], count: int) -> Sequence[str]:
    return list(population)[:count]


def test_automatic_stat_allocation_and_modifiers_are_versioned() -> None:
    draft = DEFAULT_RULESET.start_draft(
        draft_id="draft",
        room_id="room",
        owner_id="player",
        name="Aria",
        sampler=first_cards,
    )

    assert draft.ruleset_version == "simple-v1"
    assert draft.stats == {
        "strength": 15,
        "dexterity": 14,
        "constitution": 13,
        "intelligence": 12,
        "wisdom": 10,
        "charisma": 8,
    }
    assert ability_modifier(14) == 2
    assert ability_modifier(9) == -1


def test_seeded_card_offers_are_reproducible() -> None:
    first = DEFAULT_RULESET.start_draft(
        draft_id="first",
        room_id="room",
        owner_id="player",
        name="Aria",
        sampler=Random(42).sample,
    )
    second = DEFAULT_RULESET.start_draft(
        draft_id="second",
        room_id="room",
        owner_id="player",
        name="Aria",
        sampler=Random(42).sample,
    )

    assert first.offered_card_ids == second.offered_card_ids


def test_bad_content_pool_fails_with_diagnostic_error() -> None:
    undersized = replace(
        DEFAULT_RULESET,
        cards=tuple(replace(card, class_ids=frozenset()) for card in DEFAULT_RULESET.cards[:2]),
    )

    with pytest.raises(ContentConfigurationError, match="Not enough") as raised:
        undersized.start_draft(
            draft_id="draft",
            room_id="room",
            owner_id="player",
            name="Aria",
            sampler=first_cards,
        )

    assert raised.value.details == {"available_cards": 2, "cards_per_round": 3}


def test_four_rounds_choose_only_offered_unique_cards() -> None:
    draft = DEFAULT_RULESET.start_draft(
        draft_id="draft",
        room_id="room",
        owner_id="player",
        name="Aria",
        sampler=first_cards,
    )

    for round_number in range(4):
        selected = draft.offered_card_ids[0]
        DEFAULT_RULESET.choose_card(
            draft,
            selected,
            expected_version=draft.version,
            sampler=first_cards,
        )
        assert len(draft.chosen_card_ids) == round_number + 1

    assert len(draft.chosen_card_ids) == 4
    assert len(set(draft.chosen_card_ids)) == 4
    assert draft.offered_card_ids == []


def test_card_must_be_in_current_offer() -> None:
    draft = DEFAULT_RULESET.start_draft(
        draft_id="draft",
        room_id="room",
        owner_id="player",
        name="Aria",
        sampler=first_cards,
    )

    with pytest.raises(DomainValidationError, match="not offered") as raised:
        DEFAULT_RULESET.choose_card(
            draft,
            "healing_touch",
            expected_version=draft.version,
            sampler=first_cards,
        )

    assert raised.value.code == "card_not_offered"


def test_incompatible_card_is_rejected_even_if_content_offer_is_bad() -> None:
    draft = DEFAULT_RULESET.start_draft(
        draft_id="draft",
        room_id="room",
        owner_id="player",
        name="Aria",
        sampler=first_cards,
    )
    DEFAULT_RULESET.choose_card(
        draft,
        "battle_fury",
        expected_version=draft.version,
        sampler=first_cards,
    )
    draft.offered_card_ids = ["arcane_focus"]

    with pytest.raises(DomainValidationError, match="incompatible") as raised:
        DEFAULT_RULESET.choose_card(
            draft,
            "arcane_focus",
            expected_version=draft.version,
            sampler=first_cards,
        )

    assert raised.value.code == "incompatible_card"


def test_future_stat_and_ability_prerequisites_are_enforced() -> None:
    constrained_cards = tuple(
        replace(
            card,
            required_stats=(("strength", 16),),
            required_ability_ids=frozenset({"battle_fury"}),
        )
        if card.id == "second_wind"
        else card
        for card in DEFAULT_RULESET.cards
    )
    ruleset = replace(DEFAULT_RULESET, cards=constrained_cards)

    with pytest.raises(DomainValidationError) as raised:
        ruleset.validate_character_choices(
            race_id="human",
            class_id="fighter",
            stats={"strength": 15},
            ability_ids=["second_wind"],
        )
    assert raised.value.code == "ability_requirements_not_met"

    ruleset.validate_character_choices(
        race_id="human",
        class_id="fighter",
        stats={"strength": 16},
        ability_ids=["battle_fury", "second_wind"],
    )


def test_restart_clears_choices_and_increments_generation() -> None:
    draft = DEFAULT_RULESET.start_draft(
        draft_id="draft",
        room_id="room",
        owner_id="player",
        name="Aria",
        sampler=first_cards,
    )
    DEFAULT_RULESET.choose_card(
        draft,
        draft.offered_card_ids[0],
        expected_version=draft.version,
        sampler=first_cards,
    )

    DEFAULT_RULESET.restart_draft(
        draft,
        expected_version=draft.version,
        sampler=first_cards,
    )

    assert draft.chosen_card_ids == []
    assert len(draft.offered_card_ids) == 3
    assert draft.generation == 2


def test_incomplete_draft_cannot_be_confirmed() -> None:
    draft = DEFAULT_RULESET.start_draft(
        draft_id="draft",
        room_id="room",
        owner_id="player",
        name="Aria",
        sampler=first_cards,
    )

    with pytest.raises(StateConflictError, match="incomplete") as raised:
        DEFAULT_RULESET.confirm_draft(
            draft,
            character_id="character",
            expected_version=draft.version,
        )

    assert raised.value.code == "draft_incomplete"


def test_complete_draft_creates_character_and_cannot_confirm_again() -> None:
    draft = DEFAULT_RULESET.start_draft(
        draft_id="draft",
        room_id="room",
        owner_id="player",
        name="Aria",
        sampler=first_cards,
    )
    for _ in range(4):
        DEFAULT_RULESET.choose_card(
            draft,
            draft.offered_card_ids[0],
            expected_version=draft.version,
            sampler=first_cards,
        )

    character = DEFAULT_RULESET.confirm_draft(
        draft,
        character_id="character",
        expected_version=draft.version,
    )

    assert character.ability_ids == draft.chosen_card_ids
    assert len(character.ability_ids) == 4
    with pytest.raises(StateConflictError, match="already confirmed"):
        DEFAULT_RULESET.confirm_draft(
            draft,
            character_id="another-character",
            expected_version=draft.version,
        )
