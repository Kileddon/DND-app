from __future__ import annotations

import logging
import secrets
import string
from collections.abc import Callable, Mapping
from dataclasses import asdict
from datetime import UTC, datetime
from typing import Any, TypeVar, cast
from uuid import uuid4

from tabletop_companion.application.commands import (
    AddInventoryItemCommand,
    ChooseAbilityCardCommand,
    ConfirmCharacterDraftCommand,
    CreateRoomCommand,
    DiscardInventoryItemCommand,
    JoinLocalPlayerCommand,
    RestartCharacterDraftCommand,
    StartCharacterDraftCommand,
)
from tabletop_companion.application.fingerprints import command_fingerprint
from tabletop_companion.application.ports import (
    ProcessedCommand,
    UnitOfWork,
    UnitOfWorkFactory,
)
from tabletop_companion.domain.errors import (
    ContentConfigurationError,
    DomainValidationError,
    IdempotencyConflictError,
    PermissionDeniedError,
)
from tabletop_companion.domain.events import DomainEvent
from tabletop_companion.domain.models import (
    AbilityCard,
    Character,
    CharacterDraft,
    InventoryItem,
    ItemDefinition,
    LocalPlayer,
    Room,
)
from tabletop_companion.domain.rules import CardSampler, SimpleRuleset

CommandT = TypeVar("CommandT")
ResultData = dict[str, Any]

logger = logging.getLogger(__name__)


class CommandOutcome:
    def __init__(
        self,
        data: ResultData,
        *,
        replayed: bool,
        events: tuple[DomainEvent, ...] = (),
    ) -> None:
        self.data = data
        self.replayed = replayed
        self.events = events


class CompanionService:
    def __init__(
        self,
        *,
        uow_factory: UnitOfWorkFactory,
        rulesets: Mapping[str, SimpleRuleset],
        sampler: CardSampler,
        id_factory: Callable[[], str] | None = None,
        clock: Callable[[], datetime] | None = None,
    ) -> None:
        self._uow_factory = uow_factory
        self._rulesets = dict(rulesets)
        self._sampler = sampler
        self._id_factory = id_factory or (lambda: str(uuid4()))
        self._clock = clock or (lambda: datetime.now(UTC))

    def create_room(self, command: CreateRoomCommand) -> CommandOutcome:
        def operation(uow: UnitOfWork) -> ResultData:
            if command.access_mode.value != "open":
                raise DomainValidationError(
                    "Only open local rooms are supported in the first vertical slice.",
                    details={"access_mode": command.access_mode.value},
                )
            timestamp = self._clock()
            room = Room(
                id=self._id_factory(),
                name=command.name.strip(),
                gm_id=command.gm_id,
                access_mode=command.access_mode,
                ruleset_version=self._default_ruleset().version,
                version=1,
                created_at=timestamp,
                code="".join(
                    secrets.choice(string.ascii_uppercase + string.digits) for _ in range(6)
                ),
            )
            if not room.name:
                raise DomainValidationError("Room name must not be blank.")
            uow.add_room(room)
            uow.add_event(
                self._event(
                    event_type="RoomCreated",
                    aggregate_type="room",
                    aggregate_id=room.id,
                    room_id=room.id,
                    actor_id=command.gm_id,
                    command_id=command.command_id,
                    target_ids=(room.id,),
                    payload={
                        "name": room.name,
                        "access_mode": room.access_mode.value,
                        "ruleset_version": room.ruleset_version,
                    },
                )
            )
            return self._room_data(room)

        return self._execute("create_room", command, command.gm_id, operation)

    def join_local_player(self, command: JoinLocalPlayerCommand) -> CommandOutcome:
        def operation(uow: UnitOfWork) -> ResultData:
            room = uow.get_room(command.room_id)
            timestamp = self._clock()
            player = LocalPlayer(
                id=self._id_factory(),
                room_id=room.id,
                display_name=command.display_name.strip(),
                version=1,
                created_at=timestamp,
            )
            if not player.display_name:
                raise DomainValidationError("Player display name must not be blank.")
            uow.add_local_player(player)
            uow.add_event(
                self._event(
                    event_type="LocalPlayerJoined",
                    aggregate_type="local_player",
                    aggregate_id=player.id,
                    room_id=room.id,
                    actor_id=player.id,
                    command_id=command.command_id,
                    target_ids=(player.id,),
                    payload={"display_name": player.display_name},
                )
            )
            return self._player_data(player)

        return self._execute(
            "join_local_player", command, f"local-device:{command.device_id}", operation
        )

    def start_character_draft(self, command: StartCharacterDraftCommand) -> CommandOutcome:
        def operation(uow: UnitOfWork) -> ResultData:
            room = uow.get_room(command.room_id)
            player = uow.get_local_player(command.player_id)
            self._ensure_player_room(player, room.id)
            ruleset = self._ruleset(room.ruleset_version)
            draft = ruleset.start_draft(
                draft_id=self._id_factory(),
                room_id=room.id,
                owner_id=player.id,
                name=command.name,
                sampler=self._sampler,
                now=self._clock(),
            )
            uow.add_character_draft(draft)
            uow.add_event(
                self._event(
                    event_type="CharacterDraftStarted",
                    aggregate_type="character_draft",
                    aggregate_id=draft.id,
                    room_id=room.id,
                    actor_id=player.id,
                    command_id=command.command_id,
                    target_ids=(draft.id,),
                    payload={"ruleset_version": draft.ruleset_version},
                )
            )
            return self._draft_data(draft, ruleset)

        return self._execute("start_character_draft", command, command.player_id, operation)

    def choose_ability_card(self, command: ChooseAbilityCardCommand) -> CommandOutcome:
        def operation(uow: UnitOfWork) -> ResultData:
            draft = uow.get_character_draft(command.draft_id)
            self._ensure_owner(draft.owner_id, command.player_id)
            ruleset = self._ruleset(draft.ruleset_version)
            round_number = len(draft.chosen_card_ids) + 1
            ruleset.choose_card(
                draft,
                command.card_id,
                expected_version=command.expected_version,
                sampler=self._sampler,
                now=self._clock(),
            )
            uow.save_character_draft(draft)
            uow.add_event(
                self._event(
                    event_type="AbilityCardSelected",
                    aggregate_type="character_draft",
                    aggregate_id=draft.id,
                    room_id=draft.room_id,
                    actor_id=command.player_id,
                    command_id=command.command_id,
                    source_id=command.card_id,
                    target_ids=(draft.id,),
                    payload={"card_id": command.card_id, "round": round_number},
                )
            )
            return self._draft_data(draft, ruleset)

        return self._execute("choose_ability_card", command, command.player_id, operation)

    def restart_character_draft(self, command: RestartCharacterDraftCommand) -> CommandOutcome:
        def operation(uow: UnitOfWork) -> ResultData:
            draft = uow.get_character_draft(command.draft_id)
            self._ensure_owner(draft.owner_id, command.player_id)
            ruleset = self._ruleset(draft.ruleset_version)
            ruleset.restart_draft(
                draft,
                expected_version=command.expected_version,
                sampler=self._sampler,
                now=self._clock(),
            )
            uow.save_character_draft(draft)
            uow.add_event(
                self._event(
                    event_type="CharacterDraftRestarted",
                    aggregate_type="character_draft",
                    aggregate_id=draft.id,
                    room_id=draft.room_id,
                    actor_id=command.player_id,
                    command_id=command.command_id,
                    target_ids=(draft.id,),
                    payload={"generation": draft.generation},
                )
            )
            return self._draft_data(draft, ruleset)

        return self._execute("restart_character_draft", command, command.player_id, operation)

    def confirm_character_draft(self, command: ConfirmCharacterDraftCommand) -> CommandOutcome:
        def operation(uow: UnitOfWork) -> ResultData:
            draft = uow.get_character_draft(command.draft_id)
            self._ensure_owner(draft.owner_id, command.player_id)
            ruleset = self._ruleset(draft.ruleset_version)
            character = ruleset.confirm_draft(
                draft,
                character_id=self._id_factory(),
                expected_version=command.expected_version,
                now=self._clock(),
            )
            uow.save_character_draft(draft)
            uow.add_character(character)
            uow.add_event(
                self._event(
                    event_type="CharacterCreated",
                    aggregate_type="character",
                    aggregate_id=character.id,
                    room_id=character.room_id,
                    actor_id=command.player_id,
                    command_id=command.command_id,
                    source_id=draft.id,
                    target_ids=(character.id,),
                    payload={
                        "ruleset_version": character.ruleset_version,
                        "ability_ids": list(character.ability_ids),
                        "draft_generation": draft.generation,
                    },
                )
            )
            return self._character_data(character, ruleset)

        return self._execute("confirm_character_draft", command, command.player_id, operation)

    def add_inventory_item(self, command: AddInventoryItemCommand) -> CommandOutcome:
        def operation(uow: UnitOfWork) -> ResultData:
            character = uow.get_character(command.character_id)
            self._ensure_owner(character.owner_id, command.actor_id)
            definition = ItemDefinition(
                id=self._id_factory(),
                name=command.name.strip(),
                consumable=command.consumable,
                locked=command.locked,
            )
            if not definition.name:
                raise DomainValidationError("Item name must not be blank.")
            item = InventoryItem(
                id=self._id_factory(),
                definition_id=definition.id,
                name=definition.name,
                consumable=definition.consumable,
                locked=definition.locked,
                quantity=command.quantity,
                equipped=command.equipped,
                charges=command.charges,
                created_at=self._clock(),
            )
            character.add_item(item, expected_version=command.expected_version)
            uow.add_item_definition(definition)
            uow.save_character(character)
            uow.add_event(
                self._event(
                    event_type="ItemGranted",
                    aggregate_type="character",
                    aggregate_id=character.id,
                    room_id=character.room_id,
                    actor_id=command.actor_id,
                    command_id=command.command_id,
                    source_id=item.definition_id,
                    target_ids=(character.id, item.id),
                    payload={
                        "item_id": item.id,
                        "definition_id": item.definition_id,
                        "name": item.name,
                        "quantity": item.quantity,
                        "consumable": item.consumable,
                    },
                )
            )
            return self._character_data(character, self._ruleset(character.ruleset_version))

        return self._execute("add_inventory_item", command, command.actor_id, operation)

    def discard_inventory_item(self, command: DiscardInventoryItemCommand) -> CommandOutcome:
        def operation(uow: UnitOfWork) -> ResultData:
            character = uow.get_character(command.character_id)
            self._ensure_owner(character.owner_id, command.actor_id)
            item = next(
                (candidate for candidate in character.inventory if candidate.id == command.item_id),
                None,
            )
            result = character.discard(
                command.item_id,
                command.quantity,
                expected_version=command.expected_version,
            )
            uow.save_character(character)
            uow.add_event(
                self._event(
                    event_type="ItemDiscarded",
                    aggregate_type="character",
                    aggregate_id=character.id,
                    room_id=character.room_id,
                    actor_id=command.actor_id,
                    command_id=command.command_id,
                    source_id=item.definition_id if item else None,
                    target_ids=(character.id, command.item_id),
                    payload={
                        "item_id": command.item_id,
                        "quantity": result.discarded_quantity,
                        "remaining_quantity": result.remaining_quantity,
                        "removed": result.removed,
                        "effect_applied": result.effect_applied,
                    },
                )
            )
            return self._character_data(character, self._ruleset(character.ruleset_version))

        return self._execute("discard_inventory_item", command, command.actor_id, operation)

    def get_room(self, room_id: str) -> ResultData:
        with self._uow_factory() as uow:
            return self._room_data(uow.get_room(room_id))

    def get_character_draft(self, draft_id: str) -> ResultData:
        with self._uow_factory() as uow:
            draft = uow.get_character_draft(draft_id)
            return self._draft_data(draft, self._ruleset(draft.ruleset_version))

    def get_character(self, character_id: str) -> ResultData:
        with self._uow_factory() as uow:
            character = uow.get_character(character_id)
            return self._character_data(character, self._ruleset(character.ruleset_version))

    def list_events(self, room_id: str) -> list[ResultData]:
        with self._uow_factory() as uow:
            uow.get_room(room_id)
            return [self._event_data(event) for event in uow.list_events(room_id)]

    def _execute(
        self,
        command_type: str,
        command: CommandT,
        actor_id: str,
        operation: Callable[[UnitOfWork], ResultData],
    ) -> CommandOutcome:
        command_data: dict[str, Any] = asdict(cast(Any, command))
        command_id = str(command_data["command_id"])
        device_id = str(command_data["device_id"])
        client_time_value = command_data["client_time"]
        client_time = str(client_time_value) if client_time_value is not None else None
        payload_hash = command_fingerprint(command)

        with self._uow_factory() as uow:
            existing = uow.get_processed_command(command_id)
            if existing is not None:
                if (
                    existing.command_type != command_type
                    or existing.actor_id != actor_id
                    or existing.payload_hash != payload_hash
                ):
                    raise IdempotencyConflictError(
                        "Command ID was already used with different command content.",
                        details={"command_id": command_id},
                    )
                logger.info(
                    "command_replayed",
                    extra={"command_id": command_id, "command_type": command_type},
                )
                return CommandOutcome(dict(existing.result), replayed=True)

            result = operation(uow)
            uow.add_processed_command(
                ProcessedCommand(
                    command_id=command_id,
                    command_type=command_type,
                    payload_hash=payload_hash,
                    actor_id=actor_id,
                    device_id=device_id,
                    client_time=client_time,
                    host_time=self._clock().isoformat(),
                    result=result,
                )
            )
            uow.commit()

        with self._uow_factory() as uow:
            events = tuple(uow.list_events_by_command(command_id))

        logger.info(
            "command_processed",
            extra={"command_id": command_id, "command_type": command_type},
        )
        return CommandOutcome(result, replayed=False, events=events)

    def _event(
        self,
        *,
        event_type: str,
        aggregate_type: str,
        aggregate_id: str,
        room_id: str,
        actor_id: str,
        command_id: str,
        target_ids: tuple[str, ...],
        payload: ResultData,
        source_id: str | None = None,
    ) -> DomainEvent:
        return DomainEvent(
            id=self._id_factory(),
            event_type=event_type,
            aggregate_type=aggregate_type,
            aggregate_id=aggregate_id,
            room_id=room_id,
            actor_id=actor_id,
            source_id=source_id,
            target_ids=target_ids,
            payload=payload,
            visibility="room",
            schema_version=1,
            command_id=command_id,
            occurred_at=self._clock(),
        )

    def _default_ruleset(self) -> SimpleRuleset:
        if len(self._rulesets) != 1:
            raise ContentConfigurationError("A default ruleset is not configured unambiguously.")
        return next(iter(self._rulesets.values()))

    def _ruleset(self, version: str) -> SimpleRuleset:
        try:
            return self._rulesets[version]
        except KeyError as error:
            raise ContentConfigurationError(
                "The requested ruleset is not available.", details={"ruleset_version": version}
            ) from error

    @staticmethod
    def _ensure_owner(owner_id: str, actor_id: str) -> None:
        if owner_id != actor_id:
            raise PermissionDeniedError("The player does not control this character.")

    @staticmethod
    def _ensure_player_room(player: LocalPlayer, room_id: str) -> None:
        if player.room_id != room_id:
            raise PermissionDeniedError("The player does not belong to this room.")

    @staticmethod
    def _card_data(card: AbilityCard) -> ResultData:
        return {
            "id": card.id,
            "name": card.name,
            "description": card.description,
            "kind": card.kind,
            "properties": list(card.properties),
        }

    @staticmethod
    def _room_data(room: Room) -> ResultData:
        return {
            "id": room.id,
            "name": room.name,
            "gm_id": room.gm_id,
            "access_mode": room.access_mode.value,
            "ruleset_version": room.ruleset_version,
            "version": room.version,
            "created_at": room.created_at.isoformat(),
            "code": room.code,
        }

    @staticmethod
    def _player_data(player: LocalPlayer) -> ResultData:
        return {
            "id": player.id,
            "room_id": player.room_id,
            "display_name": player.display_name,
            "version": player.version,
            "created_at": player.created_at.isoformat(),
        }

    def _draft_data(self, draft: CharacterDraft, ruleset: SimpleRuleset) -> ResultData:
        return {
            "id": draft.id,
            "room_id": draft.room_id,
            "owner_id": draft.owner_id,
            "name": draft.name,
            "ruleset_version": draft.ruleset_version,
            "stats": dict(draft.stats),
            "offered_cards": [
                self._card_data(ruleset.card(card_id)) for card_id in draft.offered_card_ids
            ],
            "chosen_cards": [
                self._card_data(ruleset.card(card_id)) for card_id in draft.chosen_card_ids
            ],
            "completed_rounds": len(draft.chosen_card_ids),
            "required_rounds": ruleset.rounds_required,
            "ready_to_confirm": len(draft.chosen_card_ids) == ruleset.rounds_required,
            "generation": draft.generation,
            "status": draft.status.value,
            "version": draft.version,
            "created_at": draft.created_at.isoformat(),
            "updated_at": draft.updated_at.isoformat(),
        }

    def _character_data(self, character: Character, ruleset: SimpleRuleset) -> ResultData:
        return {
            "id": character.id,
            "draft_id": character.draft_id,
            "room_id": character.room_id,
            "owner_id": character.owner_id,
            "name": character.name,
            "ruleset_version": character.ruleset_version,
            "stats": dict(character.stats),
            "abilities": [
                self._card_data(ruleset.card(card_id)) for card_id in character.ability_ids
            ],
            "inventory": [
                {
                    "id": item.id,
                    "definition_id": item.definition_id,
                    "name": item.name,
                    "consumable": item.consumable,
                    "locked": item.locked,
                    "quantity": item.quantity,
                    "equipped": item.equipped,
                    "charges": item.charges,
                    "created_at": item.created_at.isoformat(),
                }
                for item in character.inventory
            ],
            "version": character.version,
            "created_at": character.created_at.isoformat(),
        }

    @staticmethod
    def _event_data(event: DomainEvent) -> ResultData:
        return {
            "id": event.id,
            "event_type": event.event_type,
            "aggregate_type": event.aggregate_type,
            "aggregate_id": event.aggregate_id,
            "room_id": event.room_id,
            "actor_id": event.actor_id,
            "source_id": event.source_id,
            "target_ids": list(event.target_ids),
            "payload": dict(event.payload),
            "visibility": event.visibility,
            "schema_version": event.schema_version,
            "command_id": event.command_id,
            "occurred_at": event.occurred_at.isoformat(),
            "cursor": event.cursor,
            "session_id": event.session_id,
        }
