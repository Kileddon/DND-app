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
class RaceDefinition:
    id: str
    name: str
    description: str
    hp_bonus: int = 0


@dataclass(frozen=True, slots=True)
class ClassDefinition:
    id: str
    name: str
    description: str
    base_hp: int
    base_armor_class: int


@dataclass(frozen=True, slots=True)
class SimpleRuleset:
    version: str
    rounds_required: int
    cards_per_round: int
    allow_duplicates: bool
    max_rerolls: int
    stat_allocation: tuple[tuple[str, int], ...]
    cards: tuple[AbilityCard, ...]
    races: tuple[RaceDefinition, ...] = ()
    classes: tuple[ClassDefinition, ...] = ()

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
        race_id: str = "human",
        class_id: str = "fighter",
        now: datetime | None = None,
    ) -> CharacterDraft:
        normalized_name = name.strip()
        if not normalized_name:
            raise DomainValidationError("Character name must not be blank.")
        timestamp = now or datetime.now(UTC)
        self.race(race_id)
        self.character_class(class_id)
        stats = self.allocate_stats()
        return CharacterDraft(
            id=draft_id,
            room_id=room_id,
            owner_id=owner_id,
            name=normalized_name,
            ruleset_version=self.version,
            stats=stats,
            offered_card_ids=self._deal((), sampler, class_id=class_id, stats=stats),
            chosen_card_ids=[],
            generation=1,
            status=DraftStatus.ACTIVE,
            version=1,
            created_at=timestamp,
            updated_at=timestamp,
            race_id=race_id,
            class_id=class_id,
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
            draft.offered_card_ids = self._deal(
                tuple(draft.chosen_card_ids),
                sampler,
                class_id=draft.class_id,
                stats=draft.stats,
            )
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
        draft.offered_card_ids = self._deal((), sampler, class_id=draft.class_id, stats=draft.stats)
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
        character_class = self.character_class(draft.class_id)
        race = self.race(draft.race_id)
        max_hp = max(
            1,
            character_class.base_hp
            + ability_modifier(draft.stats.get("constitution", 10))
            + race.hp_bonus,
        )
        armor_class = character_class.base_armor_class + min(
            2, max(0, ability_modifier(draft.stats.get("dexterity", 10)))
        )
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
            race_id=draft.race_id,
            class_id=draft.class_id,
            max_hp=max_hp,
            current_hp=max_hp,
            armor_class=armor_class,
        )

    def card(self, card_id: str) -> AbilityCard:
        try:
            return self.cards_by_id[card_id]
        except KeyError as error:
            raise ContentConfigurationError(
                "Ruleset references an unknown ability card.", details={"card_id": card_id}
            ) from error

    def race(self, race_id: str) -> RaceDefinition:
        for race in self.races:
            if race.id == race_id:
                return race
        raise DomainValidationError("Unknown character race.", details={"race_id": race_id})

    def character_class(self, class_id: str) -> ClassDefinition:
        for character_class in self.classes:
            if character_class.id == class_id:
                return character_class
        raise DomainValidationError("Unknown character class.", details={"class_id": class_id})

    def validate_character_choices(
        self,
        *,
        race_id: str,
        class_id: str,
        stats: dict[str, int],
        ability_ids: Sequence[str],
    ) -> None:
        self.race(race_id)
        self.character_class(class_id)
        if len(set(ability_ids)) != len(ability_ids):
            raise DomainValidationError("Duplicate ability cards are not allowed.")
        for card_id in ability_ids:
            card = self.card(card_id)
            if not self._eligible(card, class_id, stats, ability_ids):
                raise DomainValidationError(
                    "Ability requirements are not met.",
                    details={"card_id": card_id},
                    code="ability_requirements_not_met",
                )
            if not self._compatible(card, ability_ids):
                raise DomainValidationError(
                    "Selected abilities are incompatible.",
                    details={"card_id": card_id},
                    code="incompatible_card",
                )

    def _deal(
        self,
        chosen_card_ids: tuple[str, ...],
        sampler: CardSampler,
        *,
        class_id: str = "fighter",
        stats: dict[str, int] | None = None,
    ) -> list[str]:
        actual_stats = stats or self.allocate_stats()
        candidates = [
            card.id
            for card in self.cards
            if (self.allow_duplicates or card.id not in chosen_card_ids)
            and self._compatible(card, chosen_card_ids)
            and self._eligible(card, class_id, actual_stats, chosen_card_ids)
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

    @staticmethod
    def _eligible(
        card: AbilityCard,
        class_id: str,
        stats: dict[str, int],
        chosen_card_ids: Sequence[str],
    ) -> bool:
        return (
            (not card.class_ids or class_id in card.class_ids)
            and all(stats.get(stat, 0) >= minimum for stat, minimum in card.required_stats)
            and card.required_ability_ids.issubset(chosen_card_ids)
        )

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
            frozenset({"fighter"}),
        ),
        AbilityCard(
            "arcane_focus",
            "Arcane Focus",
            "Shape a precise magical effect.",
            "active",
            ("magic",),
            frozenset({"battle_fury"}),
            frozenset({"wizard"}),
        ),
        AbilityCard(
            "guardian_stance",
            "Guardian Stance",
            "Protect a nearby ally.",
            "reaction",
            ("defence",),
            class_ids=frozenset({"fighter"}),
        ),
        AbilityCard(
            "healing_touch",
            "Healing Touch",
            "Restore a small amount of health.",
            "active",
            ("support", "magic"),
            class_ids=frozenset({"wizard"}),
        ),
        AbilityCard(
            "shadow_step",
            "Shadow Step",
            "Move unseen over a short distance.",
            "active",
            ("mobility",),
            class_ids=frozenset({"rogue"}),
        ),
        AbilityCard(
            "keen_eye",
            "Keen Eye",
            "Notice hidden details and danger.",
            "passive",
            ("exploration",),
            class_ids=frozenset({"wizard"}),
        ),
        AbilityCard(
            "inspiring_word",
            "Inspiring Word",
            "Bolster an ally's resolve.",
            "active",
            ("support",),
            class_ids=frozenset({"fighter"}),
        ),
        AbilityCard(
            "shield_bash",
            "Shield Bash",
            "Stagger a nearby opponent.",
            "active",
            ("martial", "control"),
            class_ids=frozenset({"fighter"}),
        ),
        AbilityCard(
            "wild_spark",
            "Wild Spark",
            "Release unstable elemental energy.",
            "active",
            ("magic",),
            class_ids=frozenset({"wizard"}),
        ),
        AbilityCard(
            "survival_instinct",
            "Survival Instinct",
            "Endure sudden danger.",
            "passive",
            ("defence",),
            class_ids=frozenset({"fighter"}),
        ),
        AbilityCard(
            "quick_hands",
            "Quick Hands",
            "Interact with gear in an instant.",
            "passive",
            ("utility",),
            class_ids=frozenset({"rogue"}),
        ),
        AbilityCard(
            "binding_vines",
            "Binding Vines",
            "Restrain a target briefly.",
            "active",
            ("nature", "control"),
            class_ids=frozenset({"wizard"}),
        ),
        AbilityCard(
            "second_wind",
            "Second Wind",
            "Regain composure and a small amount of health.",
            "active",
            class_ids=frozenset({"fighter"}),
        ),
        AbilityCard(
            "spell_shield",
            "Spell Shield",
            "Raise a brief barrier against harm.",
            "reaction",
            class_ids=frozenset({"wizard"}),
        ),
        AbilityCard(
            "sneak_attack",
            "Sneak Attack",
            "Exploit an opening for additional damage.",
            "passive",
            class_ids=frozenset({"rogue"}),
        ),
        AbilityCard(
            "uncanny_dodge",
            "Uncanny Dodge",
            "Reduce the impact of an attack you can see.",
            "reaction",
            class_ids=frozenset({"rogue"}),
        ),
        AbilityCard(
            "silver_tongue",
            "Silver Tongue",
            "Turn a tense conversation in your favour.",
            "passive",
            class_ids=frozenset({"rogue"}),
        ),
        AbilityCard(
            "trap_sense",
            "Trap Sense",
            "Notice and avoid hidden mechanisms.",
            "passive",
            class_ids=frozenset({"rogue"}),
        ),
    ),
    races=(
        RaceDefinition("human", "Human", "Adaptable and ambitious."),
        RaceDefinition("elf", "Elf", "Keen senses and a long memory."),
        RaceDefinition("dwarf", "Dwarf", "Sturdy and resolute.", hp_bonus=2),
    ),
    classes=(
        ClassDefinition("fighter", "Fighter", "Martial specialist.", 10, 14),
        ClassDefinition("wizard", "Wizard", "Scholar of arcane magic.", 6, 10),
        ClassDefinition("rogue", "Rogue", "Skilled and opportunistic.", 8, 12),
    ),
)
