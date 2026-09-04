from __future__ import annotations

from datetime import datetime
from uuid import UUID

from fastapi import FastAPI, status
from pydantic import BaseModel

from tabletop_companion.api.schemas import (
    AddInventoryItemRequest,
    CharacterDraftView,
    CharacterView,
    ChooseAbilityCardRequest,
    CommandMeta,
    CommandResponse,
    ConfirmCharacterDraftRequest,
    CreateRoomRequest,
    DiscardInventoryItemRequest,
    EventView,
    HealthView,
    JoinLocalPlayerRequest,
    ListMeta,
    ListResponse,
    LocalPlayerView,
    RestartCharacterDraftRequest,
    RoomView,
    StartCharacterDraftRequest,
)
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
from tabletop_companion.application.service import CommandOutcome, CompanionService


def _client_time(value: datetime | None) -> str | None:
    return value.isoformat() if value is not None else None


def _response[ModelT: BaseModel](
    view_type: type[ModelT], outcome: CommandOutcome
) -> CommandResponse[ModelT]:
    view = view_type.model_validate(outcome.data)
    return CommandResponse(data=view, meta=CommandMeta(replayed=outcome.replayed))


def register_routes(app: FastAPI, service: CompanionService) -> None:
    @app.get("/health", response_model=HealthView, tags=["system"])
    def health() -> HealthView:
        return HealthView(status="ok")

    @app.post(
        "/api/v1/rooms",
        response_model=CommandResponse[RoomView],
        status_code=status.HTTP_201_CREATED,
        tags=["rooms"],
    )
    def create_room(payload: CreateRoomRequest) -> CommandResponse[RoomView]:
        outcome = service.create_room(
            CreateRoomCommand(
                command_id=str(payload.command_id),
                device_id=payload.device_id,
                client_time=_client_time(payload.client_time),
                gm_id=str(payload.gm_id),
                name=payload.name,
                access_mode=payload.access_mode,
            )
        )
        return _response(RoomView, outcome)

    @app.get("/api/v1/rooms/{room_id}", response_model=RoomView, tags=["rooms"])
    def get_room(room_id: UUID) -> RoomView:
        return RoomView.model_validate(service.get_room(str(room_id)))

    @app.post(
        "/api/v1/rooms/{room_id}/players",
        response_model=CommandResponse[LocalPlayerView],
        status_code=status.HTTP_201_CREATED,
        tags=["rooms"],
    )
    def join_player(
        room_id: UUID, payload: JoinLocalPlayerRequest
    ) -> CommandResponse[LocalPlayerView]:
        outcome = service.join_local_player(
            JoinLocalPlayerCommand(
                command_id=str(payload.command_id),
                device_id=payload.device_id,
                client_time=_client_time(payload.client_time),
                room_id=str(room_id),
                display_name=payload.display_name,
            )
        )
        return _response(LocalPlayerView, outcome)

    @app.post(
        "/api/v1/rooms/{room_id}/players/{player_id}/character-drafts",
        response_model=CommandResponse[CharacterDraftView],
        status_code=status.HTTP_201_CREATED,
        tags=["characters"],
    )
    def start_draft(
        room_id: UUID, player_id: UUID, payload: StartCharacterDraftRequest
    ) -> CommandResponse[CharacterDraftView]:
        outcome = service.start_character_draft(
            StartCharacterDraftCommand(
                command_id=str(payload.command_id),
                device_id=payload.device_id,
                client_time=_client_time(payload.client_time),
                room_id=str(room_id),
                player_id=str(player_id),
                name=payload.name,
                race_id=payload.race_id,
                class_id=payload.class_id,
                species_choices=payload.species_choices,
                stat_method=payload.stat_method,
                stats=payload.stats,
                background_pattern=payload.background_pattern,
                background_stats=payload.background_stats,
                background_allocations=payload.background_allocations,
            )
        )
        return _response(CharacterDraftView, outcome)

    @app.get(
        "/api/v1/character-drafts/{draft_id}",
        response_model=CharacterDraftView,
        tags=["characters"],
    )
    def get_draft(draft_id: UUID) -> CharacterDraftView:
        return CharacterDraftView.model_validate(service.get_character_draft(str(draft_id)))

    @app.post(
        "/api/v1/character-drafts/{draft_id}/players/{player_id}/choices",
        response_model=CommandResponse[CharacterDraftView],
        tags=["characters"],
    )
    def choose_card(
        draft_id: UUID, player_id: UUID, payload: ChooseAbilityCardRequest
    ) -> CommandResponse[CharacterDraftView]:
        outcome = service.choose_ability_card(
            ChooseAbilityCardCommand(
                command_id=str(payload.command_id),
                device_id=payload.device_id,
                client_time=_client_time(payload.client_time),
                player_id=str(player_id),
                draft_id=str(draft_id),
                card_id=payload.card_id,
                expected_version=payload.expected_version,
            )
        )
        return _response(CharacterDraftView, outcome)

    @app.post(
        "/api/v1/character-drafts/{draft_id}/players/{player_id}/restart",
        response_model=CommandResponse[CharacterDraftView],
        tags=["characters"],
    )
    def restart_draft(
        draft_id: UUID, player_id: UUID, payload: RestartCharacterDraftRequest
    ) -> CommandResponse[CharacterDraftView]:
        outcome = service.restart_character_draft(
            RestartCharacterDraftCommand(
                command_id=str(payload.command_id),
                device_id=payload.device_id,
                client_time=_client_time(payload.client_time),
                player_id=str(player_id),
                draft_id=str(draft_id),
                expected_version=payload.expected_version,
            )
        )
        return _response(CharacterDraftView, outcome)

    @app.post(
        "/api/v1/character-drafts/{draft_id}/players/{player_id}/confirm",
        response_model=CommandResponse[CharacterView],
        status_code=status.HTTP_201_CREATED,
        tags=["characters"],
    )
    def confirm_draft(
        draft_id: UUID, player_id: UUID, payload: ConfirmCharacterDraftRequest
    ) -> CommandResponse[CharacterView]:
        outcome = service.confirm_character_draft(
            ConfirmCharacterDraftCommand(
                command_id=str(payload.command_id),
                device_id=payload.device_id,
                client_time=_client_time(payload.client_time),
                player_id=str(player_id),
                draft_id=str(draft_id),
                expected_version=payload.expected_version,
            )
        )
        return _response(CharacterView, outcome)

    @app.get(
        "/api/v1/characters/{character_id}",
        response_model=CharacterView,
        tags=["characters"],
    )
    def get_character(character_id: UUID) -> CharacterView:
        return CharacterView.model_validate(service.get_character(str(character_id)))

    @app.post(
        "/api/v1/characters/{character_id}/inventory",
        response_model=CommandResponse[CharacterView],
        status_code=status.HTTP_201_CREATED,
        tags=["inventory"],
    )
    def add_item(
        character_id: UUID, payload: AddInventoryItemRequest
    ) -> CommandResponse[CharacterView]:
        outcome = service.add_inventory_item(
            AddInventoryItemCommand(
                command_id=str(payload.command_id),
                device_id=payload.device_id,
                client_time=_client_time(payload.client_time),
                actor_id=str(payload.actor_id),
                character_id=str(character_id),
                name=payload.name,
                quantity=payload.quantity,
                consumable=payload.consumable,
                locked=payload.locked,
                equipped=payload.equipped,
                charges=payload.charges,
                expected_version=payload.expected_version,
            )
        )
        return _response(CharacterView, outcome)

    @app.post(
        "/api/v1/characters/{character_id}/inventory/{item_id}/discard",
        response_model=CommandResponse[CharacterView],
        tags=["inventory"],
    )
    def discard_item(
        character_id: UUID, item_id: UUID, payload: DiscardInventoryItemRequest
    ) -> CommandResponse[CharacterView]:
        outcome = service.discard_inventory_item(
            DiscardInventoryItemCommand(
                command_id=str(payload.command_id),
                device_id=payload.device_id,
                client_time=_client_time(payload.client_time),
                actor_id=str(payload.actor_id),
                character_id=str(character_id),
                item_id=str(item_id),
                quantity=payload.quantity,
                expected_version=payload.expected_version,
            )
        )
        return _response(CharacterView, outcome)

    @app.get(
        "/api/v1/rooms/{room_id}/events",
        response_model=ListResponse[EventView],
        tags=["events"],
    )
    def list_events(room_id: UUID) -> ListResponse[EventView]:
        events = [EventView.model_validate(item) for item in service.list_events(str(room_id))]
        return ListResponse(data=events, meta=ListMeta(count=len(events)))
