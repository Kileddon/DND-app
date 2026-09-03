from __future__ import annotations

import logging
from collections.abc import Callable
from dataclasses import asdict, replace
from datetime import UTC, datetime
from typing import Any, TypeVar, cast
from uuid import uuid4

from tabletop_companion.application.combat_commands import (
    AddCharacterCommand,
    AddConditionCommand,
    AddMonstersCommand,
    ApplyHealthCommand,
    CancelHealthCommand,
    CombatCommand,
    CorrectHealthCommand,
    CreateCombatCommand,
    CreateMonsterTemplateCommand,
    EditRollCommand,
    MoveTurnCommand,
    RemoveConditionCommand,
    RemoveInitiativeEntryCommand,
    ReorderInitiativeCommand,
    RevealRollCommand,
    RollDiceCommand,
    SetWoundDisplayCommand,
    SupportCommand,
    TransitionCombatCommand,
)
from tabletop_companion.application.combat_ports import CombatUnitOfWork
from tabletop_companion.application.fingerprints import command_fingerprint
from tabletop_companion.application.ports import ProcessedCommand
from tabletop_companion.application.service import CommandOutcome
from tabletop_companion.domain.access import DeviceRole, LocalDevice
from tabletop_companion.domain.combat import (
    BUILTIN_CONDITIONS,
    Combat,
    Combatant,
    CombatantKind,
    CombatCondition,
    CombatStatus,
    DiceExpression,
    DiceRoll,
    EventCompensation,
    HealthActionType,
    InitiativeEntry,
    MonsterTemplate,
    RollMode,
    RollVisibility,
    build_combat_report,
)
from tabletop_companion.domain.errors import (
    DomainValidationError,
    IdempotencyConflictError,
    PermissionDeniedError,
    StateConflictError,
)
from tabletop_companion.domain.events import DomainEvent
from tabletop_companion.domain.sessions import SessionStatus

logger = logging.getLogger(__name__)
ResultData = dict[str, Any]
CommandT = TypeVar("CommandT")
CombatUowFactory = Callable[[], CombatUnitOfWork]


class CombatService:
    def __init__(
        self,
        *,
        uow_factory: CombatUowFactory,
        randint: Callable[[int, int], int],
        clock: Callable[[], datetime] | None = None,
        id_factory: Callable[[], str] | None = None,
    ) -> None:
        self._uow_factory = uow_factory
        self._randint = randint
        self._clock = clock or (lambda: datetime.now(UTC))
        self._id_factory = id_factory or (lambda: str(uuid4()))

    def create_combat(self, command: CreateCombatCommand, principal: LocalDevice) -> CommandOutcome:
        self._ensure_gm(principal, command.room_id)

        def operation(uow: CombatUnitOfWork) -> ResultData:
            session = uow.get_game_session(command.session_id)
            if session.room_id != command.room_id or session.status is not SessionStatus.ACTIVE:
                raise StateConflictError("Combat requires an active game session.")
            if uow.get_active_combat(session.id) is not None:
                raise StateConflictError("Session already has an unfinished combat.")
            now = self._clock()
            combat = Combat(
                id=self._id_factory(),
                room_id=command.room_id,
                session_id=session.id,
                status=CombatStatus.PREPARATION,
                round_number=0,
                current_entry_id=None,
                entries=[],
                version=1,
                created_at=now,
                updated_at=now,
            )
            uow.add_combat(combat)
            uow.add_event(self._combat_event("CombatCreated", combat, command, {}))
            return self._combat_data(combat)

        return self._execute("create_combat", command, principal.id, operation)

    def create_monster_template(
        self, command: CreateMonsterTemplateCommand, principal: LocalDevice
    ) -> CommandOutcome:
        self._ensure_gm(principal, command.room_id)

        def operation(uow: CombatUnitOfWork) -> ResultData:
            template = MonsterTemplate(
                id=self._id_factory(),
                room_id=command.room_id,
                name=command.name.strip(),
                image_url=command.image_url,
                max_hp=command.max_hp,
                current_hp=command.current_hp,
                armor_class=command.armor_class,
                notes=command.notes.strip(),
                conditions=tuple(item.strip() for item in command.conditions if item.strip()),
                actions=tuple(item.strip() for item in command.actions if item.strip()),
                created_at=self._clock(),
            )
            if not template.name:
                raise DomainValidationError("Monster name is required.")
            uow.add_monster_template(template)
            event = self._event(
                "MonsterTemplateCreated",
                command.room_id,
                None,
                template.id,
                principal.id,
                command.command_id,
                {"template_id": template.id, "name": template.name},
                visibility="gm",
            )
            uow.add_event(event)
            return self._template_data(template)

        return self._execute("create_monster_template", command, principal.id, operation)

    def add_character(self, command: AddCharacterCommand, principal: LocalDevice) -> CommandOutcome:
        self._ensure_gm(principal, command.room_id)

        def operation(uow: CombatUnitOfWork) -> ResultData:
            combat = self._combat_for_command(uow, command)
            character = uow.get_character(command.character_id)
            if character.room_id != command.room_id:
                raise PermissionDeniedError("Character does not belong to this room.")
            if any(actor.reference_id == character.id for actor in uow.list_combatants(combat.id)):
                raise StateConflictError("Character already participates in combat.")
            entry_id, actor_id, now = self._id_factory(), self._id_factory(), self._clock()
            actor = Combatant(
                id=actor_id,
                combat_id=combat.id,
                entry_id=entry_id,
                kind=CombatantKind.CHARACTER,
                reference_id=character.id,
                name=character.name,
                max_hp=command.max_hp,
                current_hp=command.current_hp,
                temporary_hp=0,
                armor_class=command.armor_class,
                conditions=[],
                show_wound_state=False,
                wound_override=None,
                version=1,
                created_at=now,
            )
            combat.add_entry(
                InitiativeEntry(entry_id, character.name, command.initiative, 9999, (actor_id,)),
                expected_version=command.expected_version,
                now=now,
                late_join=command.late_join,
            )
            uow.save_combat(combat)
            uow.add_combatant(actor)
            uow.add_event(
                self._combat_event(
                    "CombatParticipantAdded",
                    combat,
                    command,
                    {
                        "entry_id": entry_id,
                        "combatant_ids": [actor_id],
                        "late_join": command.late_join,
                    },
                )
            )
            return self._combat_data(combat, [*uow.list_combatants(combat.id), actor])

        return self._execute("add_combat_character", command, principal.id, operation)

    def add_monsters(self, command: AddMonstersCommand, principal: LocalDevice) -> CommandOutcome:
        self._ensure_gm(principal, command.room_id)

        def operation(uow: CombatUnitOfWork) -> ResultData:
            combat = self._combat_for_command(uow, command)
            template = uow.get_monster_template(command.template_id)
            if template.room_id != command.room_id or not 1 <= command.count <= 50:
                raise DomainValidationError("Monster group is invalid.")
            now = self._clock()
            created: list[Combatant] = []
            entry_ids = (
                [self._id_factory()]
                if command.grouped
                else [self._id_factory() for _ in range(command.count)]
            )
            for index in range(command.count):
                entry_id = entry_ids[0] if command.grouped else entry_ids[index]
                actor = Combatant(
                    id=self._id_factory(),
                    combat_id=combat.id,
                    entry_id=entry_id,
                    kind=CombatantKind.MONSTER,
                    reference_id=template.id,
                    name=f"{template.name} {index + 1}" if command.count > 1 else template.name,
                    max_hp=template.max_hp,
                    current_hp=template.current_hp,
                    temporary_hp=0,
                    armor_class=template.armor_class,
                    conditions=[
                        CombatCondition(self._id_factory(), name, "", None, True, now)
                        for name in template.conditions
                    ],
                    show_wound_state=True,
                    wound_override=None,
                    version=1,
                    created_at=now,
                )
                created.append(actor)
                uow.add_combatant(actor)
            entries: list[InitiativeEntry] = []
            for entry_id in entry_ids:
                members = tuple(item.id for item in created if item.entry_id == entry_id)
                label = template.name if len(members) == 1 else f"{template.name} x{len(members)}"
                entries.append(InitiativeEntry(entry_id, label, command.initiative, 9999, members))
            combat.add_entries(
                entries,
                expected_version=command.expected_version,
                now=now,
                late_join=combat.status is not CombatStatus.PREPARATION,
            )
            uow.save_combat(combat)
            uow.add_event(
                self._combat_event(
                    "CombatParticipantAdded",
                    combat,
                    command,
                    {"entry_ids": entry_ids, "combatant_ids": [item.id for item in created]},
                )
            )
            return self._combat_data(combat, [*uow.list_combatants(combat.id), *created])

        return self._execute("add_combat_monsters", command, principal.id, operation)

    def remove_entry(
        self, command: RemoveInitiativeEntryCommand, principal: LocalDevice
    ) -> CommandOutcome:
        self._ensure_gm(principal, command.room_id)

        def operation(uow: CombatUnitOfWork) -> ResultData:
            combat = self._combat_for_command(uow, command)
            combat.remove_entry(
                command.entry_id, expected_version=command.expected_version, now=self._clock()
            )
            uow.save_combat(combat)
            uow.delete_combatants_for_entry(combat.id, command.entry_id)
            uow.add_event(
                self._combat_event(
                    "CombatParticipantRemoved", combat, command, {"entry_id": command.entry_id}
                )
            )
            return self._combat_data(
                combat,
                [
                    item
                    for item in uow.list_combatants(combat.id)
                    if item.entry_id != command.entry_id
                ],
            )

        return self._execute("remove_combat_entry", command, principal.id, operation)

    def reorder(self, command: ReorderInitiativeCommand, principal: LocalDevice) -> CommandOutcome:
        return self._change_combat(
            "reorder_combat",
            "InitiativeReordered",
            command,
            principal,
            lambda combat: combat.reorder(
                list(command.entry_ids),
                expected_version=command.expected_version,
                now=self._clock(),
            ),
            {"entry_ids": list(command.entry_ids)},
        )

    def transition(
        self, command: TransitionCombatCommand, principal: LocalDevice
    ) -> CommandOutcome:
        actions: dict[str, Callable[[Combat], None]] = {
            "start": lambda value: value.start(
                expected_version=command.expected_version, now=self._clock()
            ),
            "pause": lambda value: value.pause(
                expected_version=command.expected_version, now=self._clock()
            ),
            "resume": lambda value: value.resume(
                expected_version=command.expected_version, now=self._clock()
            ),
            "complete": lambda value: value.complete(
                expected_version=command.expected_version, now=self._clock()
            ),
        }
        event_types = {
            "start": "CombatStarted",
            "pause": "CombatPaused",
            "resume": "CombatResumed",
            "complete": "CombatCompleted",
        }
        if command.action not in actions:
            raise DomainValidationError("Unknown combat transition.")
        return self._change_combat(
            "transition_combat",
            event_types[command.action],
            command,
            principal,
            actions[command.action],
            {},
        )

    def move_turn(self, command: MoveTurnCommand, principal: LocalDevice) -> CommandOutcome:
        if command.direction not in {-1, 1}:
            raise DomainValidationError("Turn direction must be -1 or 1.")
        return self._change_combat(
            "move_combat_turn",
            "CombatTurnChanged",
            command,
            principal,
            lambda combat: combat.move(
                command.direction, expected_version=command.expected_version, now=self._clock()
            ),
            {"direction": command.direction},
        )

    def apply_health(self, command: ApplyHealthCommand, principal: LocalDevice) -> CommandOutcome:
        self._ensure_gm(principal, command.room_id)

        def operation(uow: CombatUnitOfWork) -> ResultData:
            combat = uow.get_combat(command.combat_id)
            self._ensure_combat_room(combat, command.room_id)
            event, results = self._apply_health_in_uow(uow, combat, command, principal.id)
            uow.add_event(event)
            return {"event_id": event.id, "targets": results}

        return self._execute("apply_combat_health", command, principal.id, operation)

    def add_condition(self, command: AddConditionCommand, principal: LocalDevice) -> CommandOutcome:
        self._ensure_gm(principal, command.room_id)

        def operation(uow: CombatUnitOfWork) -> ResultData:
            combat = uow.get_combat(command.combat_id)
            self._ensure_combat_room(combat, command.room_id)
            target = uow.get_combatant(command.target_id)
            if target.combat_id != combat.id:
                raise PermissionDeniedError("Condition target does not belong to combat.")
            if command.source_id is not None:
                source = uow.get_combatant(command.source_id)
                if source.combat_id != combat.id:
                    raise PermissionDeniedError("Condition source does not belong to combat.")
            name = BUILTIN_CONDITIONS.get(command.catalog_id or "", command.name.strip())
            if not name:
                raise DomainValidationError("Condition name is required.")
            condition = CombatCondition(
                self._id_factory(),
                name,
                command.description.strip(),
                command.source_id,
                command.visible_to_players,
                self._clock(),
            )
            target.add_condition(condition, expected_version=command.expected_version)
            uow.save_combatant(target)
            event = self._event(
                "ConditionAdded",
                command.room_id,
                combat.session_id,
                combat.id,
                principal.id,
                command.command_id,
                {
                    "combat_id": combat.id,
                    "target_id": target.id,
                    "condition": self._condition_data(condition),
                },
                visibility="room" if condition.visible_to_players else "gm",
            )
            uow.add_event(event)
            return self._combatant_data(target, gm=True)

        return self._execute("add_combat_condition", command, principal.id, operation)

    def remove_condition(
        self, command: RemoveConditionCommand, principal: LocalDevice
    ) -> CommandOutcome:
        self._ensure_gm(principal, command.room_id)

        def operation(uow: CombatUnitOfWork) -> ResultData:
            combat = uow.get_combat(command.combat_id)
            self._ensure_combat_room(combat, command.room_id)
            target = uow.get_combatant(command.target_id)
            if target.combat_id != combat.id:
                raise PermissionDeniedError("Condition target does not belong to combat.")
            removed = target.remove_condition(
                command.condition_id, expected_version=command.expected_version
            )
            uow.save_combatant(target)
            uow.add_event(
                self._event(
                    "ConditionRemoved",
                    command.room_id,
                    combat.session_id,
                    combat.id,
                    principal.id,
                    command.command_id,
                    {"combat_id": combat.id, "target_id": target.id, "condition_id": removed.id},
                    visibility="room" if removed.visible_to_players else "gm",
                )
            )
            return self._combatant_data(target, gm=True)

        return self._execute("remove_combat_condition", command, principal.id, operation)

    def set_wound_display(
        self, command: SetWoundDisplayCommand, principal: LocalDevice
    ) -> CommandOutcome:
        self._ensure_gm(principal, command.room_id)

        def operation(uow: CombatUnitOfWork) -> ResultData:
            combat = uow.get_combat(command.combat_id)
            target = uow.get_combatant(command.target_id)
            self._ensure_combat_room(combat, command.room_id)
            if target.combat_id != combat.id:
                raise PermissionDeniedError("Wound target does not belong to combat.")
            if target.kind is not CombatantKind.MONSTER:
                raise DomainValidationError("Wound display applies only to monsters.")
            target.ensure_version(command.expected_version)
            target.show_wound_state = command.show
            target.wound_override = command.override.strip() if command.override else None
            target.version += 1
            uow.save_combatant(target)
            uow.add_event(
                self._event(
                    "MonsterWoundDisplayChanged",
                    command.room_id,
                    combat.session_id,
                    combat.id,
                    principal.id,
                    command.command_id,
                    {
                        "combat_id": combat.id,
                        "target_id": target.id,
                        "wound_state": target.wound_state(),
                    },
                )
            )
            return self._combatant_data(target, gm=True)

        return self._execute("set_monster_wound_display", command, principal.id, operation)

    def roll(self, command: RollDiceCommand, principal: LocalDevice) -> CommandOutcome:
        if principal.room_id != command.room_id:
            raise PermissionDeniedError("Device does not belong to this room.")
        if principal.role is DeviceRole.PLAYER:
            if command.visibility is RollVisibility.SECRET or len(command.actor_ids) != 1:
                raise PermissionDeniedError("Players cannot make secret or mass rolls.")
            if principal.player_id is None:
                raise PermissionDeniedError("Player profile is required.")

        def operation(uow: CombatUnitOfWork) -> ResultData:
            combat = uow.get_combat(command.combat_id)
            self._ensure_combat_room(combat, command.room_id)
            actors = [uow.get_combatant(actor_id) for actor_id in command.actor_ids]
            if not actors:
                raise DomainValidationError("At least one roll actor is required.")
            if any(actor.combat_id != combat.id for actor in actors):
                raise PermissionDeniedError("Roll actor does not belong to combat.")
            if principal.role is DeviceRole.PLAYER:
                character = uow.get_character(cast(str, actors[0].reference_id))
                if character.owner_id != principal.player_id:
                    raise PermissionDeniedError("Player does not control the roll actor.")
            expression = DiceExpression.parse(command.expression)
            rolls: list[DiceRoll] = []
            for actor in actors:
                values: tuple[int, ...]
                if command.mode is RollMode.PHYSICAL:
                    if command.physical_result is None:
                        raise DomainValidationError("Physical roll result is required.")
                    values, result = (), command.physical_result
                else:
                    values, result = expression.roll(self._randint)
                roll = DiceRoll(
                    id=self._id_factory(),
                    combat_id=combat.id,
                    room_id=command.room_id,
                    actor_id=actor.id,
                    character_id=actor.reference_id
                    if actor.kind is CombatantKind.CHARACTER
                    else None,
                    expression=expression.normalized(),
                    mode=command.mode,
                    visibility=command.visibility,
                    recipient_player_id=command.recipient_player_id or principal.player_id,
                    values=values,
                    original_result=result,
                    result=result,
                    reason=None,
                    action_event_id=command.action_event_id,
                    created_at=self._clock(),
                )
                if roll.visibility is RollVisibility.PRIVATE and roll.recipient_player_id is None:
                    raise DomainValidationError("Private roll needs a recipient player.")
                uow.add_dice_roll(roll)
                rolls.append(roll)
            visibility = self._roll_event_visibility(rolls[0])
            event = self._event(
                "DiceRolled",
                command.room_id,
                combat.session_id,
                combat.id,
                principal.id,
                command.command_id,
                {"combat_id": combat.id, "rolls": [self._roll_data(item) for item in rolls]},
                visibility=visibility,
            )
            uow.add_event(event)
            return {"rolls": [self._roll_data(item) for item in rolls]}

        return self._execute("roll_combat_dice", command, principal.id, operation)

    def edit_roll(self, command: EditRollCommand, principal: LocalDevice) -> CommandOutcome:
        self._ensure_gm(principal, command.room_id)

        def operation(uow: CombatUnitOfWork) -> ResultData:
            roll = uow.get_dice_roll(command.roll_id)
            if roll.room_id != command.room_id:
                raise PermissionDeniedError("Roll does not belong to this room.")
            roll.edit(command.result, command.reason)
            uow.save_dice_roll(roll)
            combat = uow.get_combat(roll.combat_id)
            uow.add_event(
                self._event(
                    "DiceRollEdited",
                    command.room_id,
                    combat.session_id,
                    combat.id,
                    principal.id,
                    command.command_id,
                    {
                        "combat_id": combat.id,
                        "roll_id": roll.id,
                        "original_result": roll.original_result,
                        "result": roll.result,
                        "reason": roll.reason,
                    },
                    visibility=self._roll_event_visibility(roll),
                )
            )
            return self._roll_data(roll)

        return self._execute("edit_combat_roll", command, principal.id, operation)

    def reveal_roll(self, command: RevealRollCommand, principal: LocalDevice) -> CommandOutcome:
        self._ensure_gm(principal, command.room_id)

        def operation(uow: CombatUnitOfWork) -> ResultData:
            roll = uow.get_dice_roll(command.roll_id)
            if roll.room_id != command.room_id:
                raise PermissionDeniedError("Roll does not belong to this room.")
            roll.reveal(self._clock())
            uow.save_dice_roll(roll)
            combat = uow.get_combat(roll.combat_id)
            uow.add_event(
                self._event(
                    "DiceRollRevealed",
                    command.room_id,
                    combat.session_id,
                    combat.id,
                    principal.id,
                    command.command_id,
                    {"combat_id": combat.id, "roll": self._roll_data(roll)},
                )
            )
            return self._roll_data(roll)

        return self._execute("reveal_combat_roll", command, principal.id, operation)

    def support(self, command: SupportCommand, principal: LocalDevice) -> CommandOutcome:
        if principal.role is not DeviceRole.PLAYER or principal.player_id is None:
            raise PermissionDeniedError("A player device is required.")
        if not command.description.strip():
            raise DomainValidationError("Support description is required.")

        def operation(uow: CombatUnitOfWork) -> ResultData:
            combat = uow.get_combat(command.combat_id)
            character = uow.get_character(command.character_id)
            if combat.room_id != command.room_id or character.owner_id != principal.player_id:
                raise PermissionDeniedError("Player does not control this character.")
            participants = uow.list_combatants(combat.id)
            actor = next((item for item in participants if item.reference_id == character.id), None)
            if actor is None:
                raise PermissionDeniedError("Character is not participating in this combat.")
            if combat.status is not CombatStatus.ACTIVE:
                raise StateConflictError("Support can only be declared during active combat.")
            if combat.current_entry_id == actor.entry_id:
                raise StateConflictError("Support can only be declared during another turn.")
            if command.roll_id is not None:
                roll = uow.get_dice_roll(command.roll_id)
                if roll.combat_id != combat.id or roll.character_id != character.id:
                    raise PermissionDeniedError(
                        "Roll does not belong to this character and combat."
                    )
            data = {
                "combat_id": combat.id,
                "character_id": character.id,
                "description": command.description.strip(),
                "roll_id": command.roll_id,
            }
            event = self._event(
                "SupportDeclared",
                command.room_id,
                combat.session_id,
                combat.id,
                principal.id,
                command.command_id,
                data,
                visibility=f"player:{principal.player_id}",
            )
            uow.add_event(event)
            return {"event_id": event.id, **data}

        return self._execute("declare_combat_support", command, principal.id, operation)

    def cancel_health(self, command: CancelHealthCommand, principal: LocalDevice) -> CommandOutcome:
        self._ensure_gm(principal, command.room_id)
        return self._compensate(command, principal, replacement=None)

    def correct_health(
        self, command: CorrectHealthCommand, principal: LocalDevice
    ) -> CommandOutcome:
        self._ensure_gm(principal, command.room_id)
        return self._compensate(command, principal, replacement=command)

    def snapshot(self, principal: LocalDevice) -> ResultData | None:
        with self._uow_factory() as uow:
            session = uow.get_unfinished_session(principal.room_id)
            if session is None:
                return None
            combats = uow.list_combats(session.id)
            if not combats:
                return None
            combat = next(
                (item for item in combats if item.status is not CombatStatus.COMPLETED), combats[-1]
            )
            actors = uow.list_combatants(combat.id)
            rolls = [
                item
                for item in uow.list_dice_rolls(combat.id)
                if self._roll_visible(item, principal)
            ]
            events = [
                item
                for item in uow.list_events(principal.room_id)
                if item.payload.get("combat_id") == combat.id
                and self.event_visible(item, principal)
            ]
            return {
                **self._combat_data(combat),
                "combatants": [self._combatant_projection(item, principal, uow) for item in actors],
                "monster_templates": [
                    self._template_data(item)
                    for item in uow.list_monster_templates(principal.room_id)
                ]
                if principal.role is DeviceRole.GM
                else [],
                "rolls": [self._roll_data(item) for item in rolls],
                "journal": [self.project_event(item, principal) for item in events[-100:]],
                "report": build_combat_report(events)
                if combat.status is CombatStatus.COMPLETED
                else None,
            }

    def event_visible(self, event: DomainEvent, principal: LocalDevice) -> bool:
        if principal.role is DeviceRole.GM:
            return event.visibility in {"room", "gm"} or event.visibility.startswith("player:")
        return event.visibility == "room" or event.visibility == f"player:{principal.player_id}"

    def project_event(self, event: DomainEvent, principal: LocalDevice) -> DomainEvent:
        if principal.role is DeviceRole.GM or event.event_type != "HealthChanged":
            return event
        payload = dict(event.payload)
        public_targets = []
        for target in payload.get("targets", []):
            if not isinstance(target, dict):
                continue
            own = target.get("owner_player_id") == principal.player_id
            if own:
                public_targets.append(target)
            else:
                public_targets.append(
                    {
                        key: target[key]
                        for key in ("target_id", "name", "kind", "entered", "wound_state")
                        if key in target
                    }
                )
        payload["targets"] = public_targets
        payload.pop("report_delta", None)
        return replace(event, payload=payload)

    def report(self, combat_id: str, principal: LocalDevice) -> ResultData:
        if principal.role is not DeviceRole.GM:
            raise PermissionDeniedError("GM access is required.")
        with self._uow_factory() as uow:
            combat = uow.get_combat(combat_id)
            self._ensure_combat_room(combat, principal.room_id)
            events = [
                event
                for event in uow.list_events(combat.room_id)
                if event.payload.get("combat_id") == combat.id
            ]
            return cast(ResultData, build_combat_report(events))

    def _compensate(
        self,
        command: CancelHealthCommand,
        principal: LocalDevice,
        replacement: CorrectHealthCommand | None,
    ) -> CommandOutcome:
        requested_replacement = replacement

        def operation(uow: CombatUnitOfWork) -> ResultData:
            original = uow.get_event(command.original_event_id)
            if (
                original.event_type != "HealthChanged"
                or original.payload.get("combat_id") != command.combat_id
            ):
                raise DomainValidationError(
                    "Only a health event from this combat can be compensated."
                )
            if uow.get_event_compensation(original.id) is not None:
                raise StateConflictError(
                    "Health event was already compensated.", code="event_already_compensated"
                )
            combat = uow.get_combat(command.combat_id)
            self._ensure_combat_room(combat, command.room_id)
            if requested_replacement is not None:
                for requested in requested_replacement.targets:
                    requested_target = uow.get_combatant(requested.target_id)
                    if requested_target.combat_id != combat.id:
                        raise PermissionDeniedError("Health target does not belong to combat.")
                    requested_target.ensure_version(requested.expected_version)
            current_versions: dict[str, int] = {}
            for item in original.payload.get("targets", []):
                target = uow.get_combatant(str(item["target_id"]))
                target.apply_compensation(
                    hp_delta=-int(item["hp_delta"]),
                    temporary_hp_delta=-int(item["temporary_hp_delta"]),
                    expected_version=target.version,
                )
                uow.save_combatant(target)
                current_versions[target.id] = target.version
            compensation_event = self._event(
                "HealthActionCompensated",
                command.room_id,
                combat.session_id,
                combat.id,
                principal.id,
                command.command_id,
                {
                    "combat_id": combat.id,
                    "original_event_id": original.id,
                    "report_delta": {
                        **cast(dict[str, Any], original.payload["report_delta"]),
                        "sign": -1,
                    },
                },
            )
            uow.add_event(compensation_event)
            replacement_event: DomainEvent | None = None
            replacement_results: list[ResultData] = []
            if requested_replacement is not None:
                effective_replacement = replace(
                    requested_replacement,
                    targets=tuple(
                        replace(
                            target,
                            expected_version=current_versions.get(
                                target.target_id, target.expected_version
                            ),
                        )
                        for target in requested_replacement.targets
                    ),
                )
                replacement_event, replacement_results = self._apply_health_in_uow(
                    uow, combat, effective_replacement, principal.id
                )
                uow.add_event(replacement_event)
            uow.add_event_compensation(
                EventCompensation(
                    original.id,
                    compensation_event.id,
                    replacement_event.id if replacement_event else None,
                    self._clock(),
                )
            )
            return {
                "original_event_id": original.id,
                "compensation_event_id": compensation_event.id,
                "replacement_event_id": replacement_event.id if replacement_event else None,
                "targets": replacement_results,
            }

        command_type = "correct_combat_health" if requested_replacement else "cancel_combat_health"
        return self._execute(command_type, command, principal.id, operation)

    def _apply_health_in_uow(
        self,
        uow: CombatUnitOfWork,
        combat: Combat,
        command: ApplyHealthCommand | CorrectHealthCommand,
        actor_id: str,
    ) -> tuple[DomainEvent, list[ResultData]]:
        results: list[ResultData] = []
        report_targets: list[ResultData] = []
        source = uow.get_combatant(command.source_id) if command.source_id else None
        if source is not None and source.combat_id != combat.id:
            raise PermissionDeniedError("Health source does not belong to combat.")
        if command.roll_id is not None:
            linked_roll = uow.get_dice_roll(command.roll_id)
            if linked_roll.combat_id != combat.id:
                raise PermissionDeniedError("Linked roll does not belong to combat.")
        for target_command in command.targets:
            target = uow.get_combatant(target_command.target_id)
            if target.combat_id != combat.id:
                raise PermissionDeniedError("Health target does not belong to combat.")
            result = target.apply_health(
                command.action,
                command.amount,
                prevented=command.prevented,
                expected_version=target_command.expected_version,
            )
            uow.save_combatant(target)
            owner = None
            if target.kind is CombatantKind.CHARACTER and target.reference_id:
                owner = uow.get_character(target.reference_id).owner_id
            relation = (
                "monster"
                if target.kind is CombatantKind.MONSTER
                else ("self" if source and source.id == target.id else "ally")
            )
            data: ResultData = {
                **asdict(result),
                "name": target.name,
                "kind": target.kind.value,
                "max_hp": target.max_hp,
                "owner_player_id": owner,
                "wound_state": target.wound_state(),
            }
            results.append(data)
            report_targets.append(
                {
                    "target_id": target.id,
                    "damage": result.actual if command.action is HealthActionType.DAMAGE else 0,
                    "healing": result.actual if command.action is HealthActionType.HEALING else 0,
                    "prevented": result.prevented,
                    "excess": result.excess if command.action is HealthActionType.DAMAGE else 0,
                    "relation": relation,
                }
            )
        payload = {
            "combat_id": combat.id,
            "source_id": command.source_id,
            "action": command.action.value,
            "entered": command.amount,
            "critical": command.critical,
            "roll_id": command.roll_id,
            "targets": results,
            "report_delta": {
                "sign": 1,
                "source_id": command.source_id,
                "critical": command.critical,
                "targets": report_targets,
            },
        }
        return self._event(
            "HealthChanged",
            combat.room_id,
            combat.session_id,
            combat.id,
            actor_id,
            command.command_id,
            payload,
            source_id=command.source_id,
            target_ids=tuple(item.target_id for item in command.targets),
        ), results

    def _change_combat(
        self,
        command_type: str,
        event_type: str,
        command: CombatCommand,
        principal: LocalDevice,
        change: Callable[[Combat], None],
        payload: ResultData,
    ) -> CommandOutcome:
        self._ensure_gm(principal, command.room_id)

        def operation(uow: CombatUnitOfWork) -> ResultData:
            combat = self._combat_for_command(uow, command)
            change(combat)
            uow.save_combat(combat)
            uow.add_event(self._combat_event(event_type, combat, command, payload))
            return self._combat_data(combat, uow.list_combatants(combat.id))

        return self._execute(command_type, command, principal.id, operation)

    def _execute(
        self,
        command_type: str,
        command: CommandT,
        actor_id: str,
        operation: Callable[[CombatUnitOfWork], ResultData],
    ) -> CommandOutcome:
        data = asdict(cast(Any, command))
        command_id = str(data["command_id"])
        fingerprint = command_fingerprint(command)
        with self._uow_factory() as uow:
            existing = uow.get_processed_command(command_id)
            if existing:
                if (
                    existing.command_type != command_type
                    or existing.actor_id != actor_id
                    or existing.payload_hash != fingerprint
                ):
                    raise IdempotencyConflictError(
                        "Command ID was already used with different command content."
                    )
                return CommandOutcome(dict(existing.result), replayed=True)
            result = operation(uow)
            uow.add_processed_command(
                ProcessedCommand(
                    command_id,
                    command_type,
                    fingerprint,
                    actor_id,
                    str(data["device_id"]),
                    cast(str | None, data.get("client_time")),
                    self._clock().isoformat(),
                    result,
                )
            )
            uow.commit()
        with self._uow_factory() as uow:
            events = tuple(uow.list_events_by_command(command_id))
        logger.info("combat_command_processed", extra={"command_type": command_type})
        return CommandOutcome(result, replayed=False, events=events)

    @staticmethod
    def _ensure_gm(principal: LocalDevice, room_id: str) -> None:
        if principal.role is not DeviceRole.GM or principal.room_id != room_id:
            raise PermissionDeniedError("A GM device for this room is required.")

    @staticmethod
    def _ensure_combat_room(combat: Combat, room_id: str) -> None:
        if combat.room_id != room_id:
            raise PermissionDeniedError("Combat does not belong to this room.")

    def _combat_for_command(self, uow: CombatUnitOfWork, command: CombatCommand) -> Combat:
        combat = uow.get_combat(command.combat_id)
        self._ensure_combat_room(combat, command.room_id)
        return combat

    def _event(
        self,
        event_type: str,
        room_id: str,
        session_id: str | None,
        aggregate_id: str,
        actor_id: str,
        command_id: str,
        payload: ResultData,
        *,
        visibility: str = "room",
        source_id: str | None = None,
        target_ids: tuple[str, ...] = (),
    ) -> DomainEvent:
        return DomainEvent(
            self._id_factory(),
            event_type,
            "combat",
            aggregate_id,
            room_id,
            actor_id,
            source_id,
            target_ids or (aggregate_id,),
            payload,
            visibility,
            1,
            command_id,
            self._clock(),
            session_id=session_id,
        )

    def _combat_event(
        self, event_type: str, combat: Combat, command: Any, payload: ResultData
    ) -> DomainEvent:
        return self._event(
            event_type,
            combat.room_id,
            combat.session_id,
            combat.id,
            str(command.device_id),
            str(command.command_id),
            {
                "combat_id": combat.id,
                "status": combat.status.value,
                "round_number": combat.round_number,
                "current_entry_id": combat.current_entry_id,
                "version": combat.version,
                **payload,
            },
        )

    @staticmethod
    def _condition_data(item: CombatCondition) -> ResultData:
        return {
            "id": item.id,
            "name": item.name,
            "description": item.description,
            "source_id": item.source_id,
            "visible_to_players": item.visible_to_players,
            "created_at": item.created_at.isoformat(),
        }

    @classmethod
    def _combatant_data(cls, item: Combatant, *, gm: bool) -> ResultData:
        data: ResultData = {
            "id": item.id,
            "entry_id": item.entry_id,
            "kind": item.kind.value,
            "reference_id": item.reference_id,
            "name": item.name,
            "conditions": [
                cls._condition_data(value)
                for value in item.conditions
                if gm or value.visible_to_players
            ],
            "wound_state": item.wound_state(),
            "version": item.version,
        }
        if gm:
            data.update(
                {
                    "max_hp": item.max_hp,
                    "current_hp": item.current_hp,
                    "temporary_hp": item.temporary_hp,
                    "armor_class": item.armor_class,
                    "show_wound_state": item.show_wound_state,
                    "wound_override": item.wound_override,
                }
            )
        return data

    def _combatant_projection(
        self, item: Combatant, principal: LocalDevice, uow: CombatUnitOfWork
    ) -> ResultData:
        if principal.role is DeviceRole.GM:
            return self._combatant_data(item, gm=True)
        own = False
        if item.kind is CombatantKind.CHARACTER and item.reference_id and principal.player_id:
            own = uow.get_character(item.reference_id).owner_id == principal.player_id
        data = self._combatant_data(item, gm=own)
        if item.kind is CombatantKind.MONSTER and not item.show_wound_state:
            data["wound_state"] = None
        return data

    @classmethod
    def _combat_data(cls, combat: Combat, actors: list[Combatant] | None = None) -> ResultData:
        data: ResultData = {
            "id": combat.id,
            "room_id": combat.room_id,
            "session_id": combat.session_id,
            "status": combat.status.value,
            "round_number": combat.round_number,
            "current_entry_id": combat.current_entry_id,
            "version": combat.version,
            "entries": [asdict(item) for item in combat.entries],
            "created_at": combat.created_at.isoformat(),
            "started_at": combat.started_at.isoformat() if combat.started_at else None,
            "completed_at": combat.completed_at.isoformat() if combat.completed_at else None,
        }
        if actors is not None:
            data["combatants"] = [cls._combatant_data(item, gm=True) for item in actors]
        return data

    @staticmethod
    def _template_data(item: MonsterTemplate) -> ResultData:
        return {
            "id": item.id,
            "name": item.name,
            "image_url": item.image_url,
            "max_hp": item.max_hp,
            "current_hp": item.current_hp,
            "armor_class": item.armor_class,
            "notes": item.notes,
            "conditions": list(item.conditions),
            "actions": list(item.actions),
        }

    @staticmethod
    def _roll_data(item: DiceRoll) -> ResultData:
        return {
            "id": item.id,
            "combat_id": item.combat_id,
            "actor_id": item.actor_id,
            "character_id": item.character_id,
            "expression": item.expression,
            "mode": item.mode.value,
            "visibility": item.visibility.value,
            "recipient_player_id": item.recipient_player_id,
            "values": list(item.values),
            "original_result": item.original_result,
            "result": item.result,
            "reason": item.reason,
            "action_event_id": item.action_event_id,
            "created_at": item.created_at.isoformat(),
            "revealed_at": item.revealed_at.isoformat() if item.revealed_at else None,
        }

    @staticmethod
    def _roll_event_visibility(roll: DiceRoll) -> str:
        if roll.visibility in {RollVisibility.SECRET, RollVisibility.DELAYED}:
            return "gm"
        if roll.visibility is RollVisibility.PRIVATE:
            return f"player:{roll.recipient_player_id}"
        return "room"

    @staticmethod
    def _roll_visible(roll: DiceRoll, principal: LocalDevice) -> bool:
        if principal.role is DeviceRole.GM:
            return True
        if roll.visibility is RollVisibility.PUBLIC:
            return True
        return (
            roll.visibility is RollVisibility.PRIVATE
            and roll.recipient_player_id == principal.player_id
        )
