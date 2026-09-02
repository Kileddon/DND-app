from __future__ import annotations

from collections.abc import Callable, Sequence
from dataclasses import dataclass
from datetime import UTC, datetime

from tabletop_companion.domain.errors import (
    ContentConfigurationError,
    DomainValidationError,
    StateConflictError,
)
from tabletop_companion.domain.models import (
    AbilityCard,
    Character,
    CharacterDraft,
    DraftStatus,
)

CardSampler = Callable[[Sequence[str], int], Sequence[str]]


def ability_modifier(score: int) -> int:
    return (score - 10) // 2


@dataclass(frozen=True, slots=True)
class SimpleRuleset:
    version: str
    rounds_required: int
    cards_per_round: int
    allow_duplicates: bool
    max_rerolls: int
    stat_allocation: tuple[tuple[str, int], ...]
    cards: tuple[AbilityCard, ...]

    @property
    def cards_by_id(self) -> dict[str, AbilityCard]:
        return {card.id: card for card in self.cards}

    def allocate_stats(self) -> dict[str, int]:
        return dict(self.stat_allocation)

    def start_draft(
        self,
        *,
        draft_id: str,
        room_id: str,
        owner_id: str,
        name: str,
        sampler: CardSampler,
        now: datetime | None = None,
    ) -> CharacterDraft:
        normalized_name = name.strip()
        if not normalized_name:
            raise DomainValidationError("Character name must not be blank.")
        timestamp = now or datetime.now(UTC)
        return CharacterDraft(
            id=draft_id,
            room_id=room_id,
            owner_id=owner_id,
            name=normalized_name,
            ruleset_version=self.version,
            stats=self.allocate_stats(),
            offered_card_ids=self._deal((), sampler),
            chosen_card_ids=[],
            generation=1,
            status=DraftStatus.ACTIVE,
            version=1,
            created_at=timestamp,
            updated_at=timestamp,
        )

    def choose_card(
        self,
        draft: CharacterDraft,
        card_id: str,
        *,
        expected_version: int,
        sampler: CardSampler,
        now: datetime | None = None,
    ) -> None:
        draft.ensure_active()
        draft.ensure_version(expected_version)
        if len(draft.chosen_card_ids) >= self.rounds_required:
            raise StateConflictError("All character draft rounds are already complete.")
        if card_id not in draft.offered_card_ids:
            raise DomainValidationError(
                "The selected card was not offered in the current round.",
                details={"card_id": card_id},
                code="card_not_offered",
            )

        selected = self.cards_by_id[card_id]
        if not self.allow_duplicates and card_id in draft.chosen_card_ids:
            raise DomainValidationError("Duplicate ability cards are not allowed.")
        if not self._compatible(selected, draft.chosen_card_ids):
            raise DomainValidationError(
                "The selected card is incompatible with an earlier choice.",
                details={"card_id": card_id},
                code="incompatible_card",
            )

        draft.chosen_card_ids.append(card_id)
        if len(draft.chosen_card_ids) == self.rounds_required:
            draft.offered_card_ids = []
        else:
            draft.offered_card_ids = self._deal(tuple(draft.chosen_card_ids), sampler)
        draft.version += 1
        draft.updated_at = now or datetime.now(UTC)

    def restart_draft(
        self,
        draft: CharacterDraft,
        *,
        expected_version: int,
        sampler: CardSampler,
        now: datetime | None = None,
    ) -> None:
        draft.ensure_active()
        draft.ensure_version(expected_version)
        draft.stats = self.allocate_stats()
        draft.chosen_card_ids = []
        draft.offered_card_ids = self._deal((), sampler)
        draft.generation += 1
        draft.version += 1
        draft.updated_at = now or datetime.now(UTC)

    def confirm_draft(
        self,
        draft: CharacterDraft,
        *,
        character_id: str,
        expected_version: int,
        now: datetime | None = None,
    ) -> Character:
        draft.ensure_active()
        draft.ensure_version(expected_version)
        if len(draft.chosen_card_ids) != self.rounds_required:
            raise StateConflictError(
                "Character draft is incomplete.",
                details={
                    "completed_rounds": len(draft.chosen_card_ids),
                    "required_rounds": self.rounds_required,
                },
                code="draft_incomplete",
            )

        timestamp = now or datetime.now(UTC)
        draft.status = DraftStatus.CONFIRMED
        draft.version += 1
        draft.updated_at = timestamp
        return Character(
            id=character_id,
            draft_id=draft.id,
            room_id=draft.room_id,
            owner_id=draft.owner_id,
            name=draft.name,
            ruleset_version=draft.ruleset_version,
            stats=dict(draft.stats),
            ability_ids=list(draft.chosen_card_ids),
            version=1,
            created_at=timestamp,
        )

    def card(self, card_id: str) -> AbilityCard:
        try:
            return self.cards_by_id[card_id]
        except KeyError as error:
            raise ContentConfigurationError(
                "Ruleset references an unknown ability card.", details={"card_id": card_id}
            ) from error

    def _deal(self, chosen_card_ids: tuple[str, ...], sampler: CardSampler) -> list[str]:
        candidates = [
            card.id
            for card in self.cards
            if (self.allow_duplicates or card.id not in chosen_card_ids)
            and self._compatible(card, chosen_card_ids)
        ]
        if len(candidates) < self.cards_per_round:
            raise ContentConfigurationError(
                "Not enough compatible ability cards to create the next round.",
                details={
                    "available_cards": len(candidates),
                    "cards_per_round": self.cards_per_round,
                },
            )
        offered = list(sampler(candidates, self.cards_per_round))
        if len(offered) != self.cards_per_round or len(set(offered)) != len(offered):
            raise ContentConfigurationError("Card sampler returned an invalid offer.")
        if any(card_id not in candidates for card_id in offered):
            raise ContentConfigurationError("Card sampler returned an unavailable card.")
        return offered

    def _compatible(self, card: AbilityCard, chosen_card_ids: Sequence[str]) -> bool:
        if any(chosen in card.incompatible_with for chosen in chosen_card_ids):
            return False
        return all(card.id not in self.card(chosen).incompatible_with for chosen in chosen_card_ids)


DEFAULT_RULESET = SimpleRuleset(
    version="simple-v1",
    rounds_required=4,
    cards_per_round=3,
    allow_duplicates=False,
    max_rerolls=0,
    stat_allocation=(
        ("strength", 15),
        ("dexterity", 14),
        ("constitution", 13),
        ("intelligence", 12),
        ("wisdom", 10),
        ("charisma", 8),
    ),
    cards=(
        AbilityCard(
            "battle_fury",
            "Battle Fury",
            "Strike harder at a cost.",
            "active",
            ("martial",),
            frozenset({"arcane_focus"}),
        ),
        AbilityCard(
            "arcane_focus",
            "Arcane Focus",
            "Shape a precise magical effect.",
            "active",
            ("magic",),
            frozenset({"battle_fury"}),
        ),
        AbilityCard(
            "guardian_stance", "Guardian Stance", "Protect a nearby ally.", "reaction", ("defence",)
        ),
        AbilityCard(
            "healing_touch",
            "Healing Touch",
            "Restore a small amount of health.",
            "active",
            ("support", "magic"),
        ),
        AbilityCard(
            "shadow_step",
            "Shadow Step",
            "Move unseen over a short distance.",
            "active",
            ("mobility",),
        ),
        AbilityCard(
            "keen_eye", "Keen Eye", "Notice hidden details and danger.", "passive", ("exploration",)
        ),
        AbilityCard(
            "inspiring_word", "Inspiring Word", "Bolster an ally's resolve.", "active", ("support",)
        ),
        AbilityCard(
            "shield_bash",
            "Shield Bash",
            "Stagger a nearby opponent.",
            "active",
            ("martial", "control"),
        ),
        AbilityCard(
            "wild_spark", "Wild Spark", "Release unstable elemental energy.", "active", ("magic",)
        ),
        AbilityCard(
            "survival_instinct",
            "Survival Instinct",
            "Endure sudden danger.",
            "passive",
            ("defence",),
        ),
        AbilityCard(
            "quick_hands",
            "Quick Hands",
            "Interact with gear in an instant.",
            "passive",
            ("utility",),
        ),
        AbilityCard(
            "binding_vines",
            "Binding Vines",
            "Restrain a target briefly.",
            "active",
            ("nature", "control"),
        ),
    ),
)
