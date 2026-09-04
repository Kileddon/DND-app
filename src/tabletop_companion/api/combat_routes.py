from __future__ import annotations

from datetime import datetime
from io import BytesIO
from pathlib import Path
from typing import Any, Literal
from uuid import UUID, uuid4

from fastapi import FastAPI, Request, status
from PIL import Image, UnidentifiedImageError
from pydantic import BaseModel, Field

from tabletop_companion.api.local_routes import (
    CurrentDevice,
    _ensure_matching_device,
    _publish,
)
from tabletop_companion.api.runtime import EventHub
from tabletop_companion.api.schemas import CommandMeta, CommandRequest, LocalCommandResponse
from tabletop_companion.application.combat_commands import (
    AddCharacterCommand,
    AddConditionCommand,
    AddMonstersCommand,
    ApplyHealthCommand,
    CancelHealthCommand,
    CorrectHealthCommand,
    CreateCombatCommand,
    CreateMonsterTemplateCommand,
    EditRollCommand,
    HealthTargetCommand,
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
from tabletop_companion.application.combat_service import CombatService
from tabletop_companion.application.service import CommandOutcome
from tabletop_companion.domain.access import DeviceRole
from tabletop_companion.domain.combat import (
    HealthActionType,
    RollMode,
    RollSelection,
    RollVisibility,
)
from tabletop_companion.domain.errors import DomainValidationError, PermissionDeniedError


class CreateCombatRequest(CommandRequest):
    name: str = Field(default="Энкаунтер", min_length=1, max_length=120)


class CombatVersionRequest(CommandRequest):
    expected_version: int = Field(ge=1)


class AddCharacterRequest(CombatVersionRequest):
    character_id: UUID
    initiative: int = Field(ge=-100, le=100)
    max_hp: int = Field(ge=1, le=100000)
    current_hp: int = Field(ge=0, le=100000)
    armor_class: int = Field(default=10, ge=0, le=1000)
    late_join: bool = False


class MonsterTemplateRequest(CommandRequest):
    name: str = Field(min_length=1, max_length=120)
    image_url: str | None = Field(default=None, max_length=500)
    max_hp: int = Field(ge=1, le=100000)
    current_hp: int = Field(ge=0, le=100000)
    armor_class: int = Field(default=10, ge=0, le=1000)
    notes: str = Field(default="", max_length=2000)
    conditions: list[str] = Field(default_factory=list, max_length=50)
    actions: list[str] = Field(default_factory=list, max_length=50)
    species: str = Field(default="", max_length=120)
    abilities: str = Field(default="", max_length=4000)
    damage: str = Field(default="", max_length=1000)
    items: str = Field(default="", max_length=4000)


class AddMonstersRequest(CombatVersionRequest):
    template_id: UUID
    initiative: int = Field(ge=-100, le=100)
    count: int = Field(default=1, ge=1, le=50)
    grouped: bool = False


class ReorderRequest(CombatVersionRequest):
    entry_ids: list[UUID]


class TransitionRequest(CombatVersionRequest):
    action: Literal["start", "pause", "resume", "complete"]


class MoveTurnRequest(CombatVersionRequest):
    direction: Literal[-1, 1]


class HealthTargetRequest(BaseModel):
    target_id: UUID
    expected_version: int = Field(ge=1)


class HealthRequest(CommandRequest):
    source_id: UUID | None = None
    targets: list[HealthTargetRequest] = Field(min_length=1, max_length=50)
    action: HealthActionType
    amount: int = Field(ge=0, le=100000)
    prevented: int = Field(default=0, ge=0, le=100000)
    critical: bool = False
    roll_id: UUID | None = None


class ConditionRequest(CommandRequest):
    expected_version: int = Field(ge=1)
    catalog_id: str | None = Field(default=None, max_length=40)
    name: str = Field(default="", max_length=120)
    description: str = Field(default="", max_length=1000)
    source_id: UUID | None = None
    visible_to_players: bool = True
    persistent: bool = False


class WoundDisplayRequest(CombatVersionRequest):
    show: bool
    override: str | None = Field(default=None, max_length=120)


class RollRequest(CommandRequest):
    actor_ids: list[UUID] = Field(min_length=1, max_length=50)
    expression: str = Field(min_length=2, max_length=32)
    mode: RollMode = RollMode.DIGITAL
    visibility: RollVisibility = RollVisibility.PUBLIC
    recipient_player_id: UUID | None = None
    physical_result: int | None = Field(default=None, ge=-100000, le=100000)
    action_event_id: UUID | None = None
    selection: RollSelection = RollSelection.NEUTRAL


class EditRollRequest(CommandRequest):
    result: int = Field(ge=-100000, le=100000)
    reason: str = Field(min_length=1, max_length=500)


class SupportRequest(CommandRequest):
    character_id: UUID
    description: str = Field(min_length=1, max_length=500)
    roll_id: UUID | None = None


class CorrectHealthRequest(HealthRequest):
    pass


def _client_time(value: datetime | None) -> str | None:
    return value.isoformat() if value else None


def _response(outcome: CommandOutcome) -> LocalCommandResponse:
    return LocalCommandResponse(
        data=outcome.data,
        meta=CommandMeta(replayed=outcome.replayed),
    )


def _targets(values: list[HealthTargetRequest]) -> tuple[HealthTargetCommand, ...]:
    return tuple(HealthTargetCommand(str(item.target_id), item.expected_version) for item in values)


def register_combat_routes(app: FastAPI, service: CombatService, hub: EventHub) -> None:
    @app.post("/api/v2/rooms/{room_id}/media", tags=["media"])
    async def upload_media(
        room_id: UUID, request: Request, current: CurrentDevice
    ) -> dict[str, str]:
        if current.role is not DeviceRole.GM or current.room_id != str(room_id):
            raise PermissionDeniedError("A GM device for this room is required.")
        extension = Path(request.headers.get("X-Upload-Filename", "")).suffix.lower()
        if extension not in {".png", ".jpg", ".jpeg", ".webp", ".gif"}:
            raise DomainValidationError("Unsupported image format.", code="unsupported_image")
        if request.headers.get("content-type") not in {
            "image/png",
            "image/jpeg",
            "image/webp",
            "image/gif",
        }:
            raise DomainValidationError("Unsupported image content type.", code="unsupported_image")
        content = await request.body()
        if not content or len(content) > 8 * 1024 * 1024:
            raise DomainValidationError(
                "Image must be between 1 byte and 8 MB.", code="invalid_image"
            )
        try:
            with Image.open(BytesIO(content)) as image:
                image.verify()
        except (SyntaxError, UnidentifiedImageError, OSError):
            raise DomainValidationError(
                "The uploaded file is not a valid image.", code="invalid_image"
            ) from None
        media_root: Path = app.state.settings.media_library
        filename = f"{uuid4().hex}{extension}"
        target = (media_root / filename).resolve()
        if media_root.resolve() not in target.parents:
            raise PermissionDeniedError("Invalid media path.")
        target.write_bytes(content)
        return {"url": f"/media/{filename}"}

    @app.get("/api/v2/me/combat", tags=["combat"])
    async def get_combat(current: CurrentDevice) -> dict[str, Any] | None:
        return service.snapshot(current)

    @app.post(
        "/api/v2/rooms/{room_id}/sessions/{session_id}/combats",
        response_model=LocalCommandResponse,
        status_code=status.HTTP_201_CREATED,
        tags=["combat"],
    )
    async def create_combat(
        room_id: UUID,
        session_id: UUID,
        payload: CreateCombatRequest,
        current: CurrentDevice,
    ) -> LocalCommandResponse:
        _ensure_matching_device(payload.device_id, current)
        outcome = service.create_combat(
            CreateCombatCommand(
                str(payload.command_id),
                payload.device_id,
                _client_time(payload.client_time),
                str(room_id),
                str(session_id),
                payload.name,
            ),
            current,
        )
        await _publish(hub, outcome)
        return _response(outcome)

    @app.post(
        "/api/v2/rooms/{room_id}/monster-templates",
        response_model=LocalCommandResponse,
        status_code=status.HTTP_201_CREATED,
        tags=["combat"],
    )
    async def create_monster_template(
        room_id: UUID, payload: MonsterTemplateRequest, current: CurrentDevice
    ) -> LocalCommandResponse:
        _ensure_matching_device(payload.device_id, current)
        outcome = service.create_monster_template(
            CreateMonsterTemplateCommand(
                str(payload.command_id),
                payload.device_id,
                _client_time(payload.client_time),
                str(room_id),
                payload.name,
                payload.image_url,
                payload.max_hp,
                payload.current_hp,
                payload.armor_class,
                payload.notes,
                tuple(payload.conditions),
                tuple(payload.actions),
                payload.species,
                payload.abilities,
                payload.damage,
                payload.items,
            ),
            current,
        )
        await _publish(hub, outcome)
        return _response(outcome)

    @app.post(
        "/api/v2/rooms/{room_id}/combats/{combat_id}/characters",
        response_model=LocalCommandResponse,
        status_code=201,
        tags=["combat"],
    )
    async def add_character(
        room_id: UUID, combat_id: UUID, payload: AddCharacterRequest, current: CurrentDevice
    ) -> LocalCommandResponse:
        _ensure_matching_device(payload.device_id, current)
        outcome = service.add_character(
            AddCharacterCommand(
                str(payload.command_id),
                payload.device_id,
                _client_time(payload.client_time),
                str(room_id),
                str(combat_id),
                payload.expected_version,
                str(payload.character_id),
                payload.initiative,
                payload.max_hp,
                payload.current_hp,
                payload.armor_class,
                payload.late_join,
            ),
            current,
        )
        await _publish(hub, outcome)
        return _response(outcome)

    @app.post(
        "/api/v2/rooms/{room_id}/combats/{combat_id}/monsters",
        response_model=LocalCommandResponse,
        status_code=201,
        tags=["combat"],
    )
    async def add_monsters(
        room_id: UUID, combat_id: UUID, payload: AddMonstersRequest, current: CurrentDevice
    ) -> LocalCommandResponse:
        _ensure_matching_device(payload.device_id, current)
        outcome = service.add_monsters(
            AddMonstersCommand(
                str(payload.command_id),
                payload.device_id,
                _client_time(payload.client_time),
                str(room_id),
                str(combat_id),
                payload.expected_version,
                str(payload.template_id),
                payload.initiative,
                payload.count,
                payload.grouped,
            ),
            current,
        )
        await _publish(hub, outcome)
        return _response(outcome)

    @app.delete(
        "/api/v2/rooms/{room_id}/combats/{combat_id}/entries/{entry_id}",
        response_model=LocalCommandResponse,
        tags=["combat"],
    )
    async def remove_entry(
        room_id: UUID,
        combat_id: UUID,
        entry_id: UUID,
        payload: CombatVersionRequest,
        current: CurrentDevice,
    ) -> LocalCommandResponse:
        _ensure_matching_device(payload.device_id, current)
        outcome = service.remove_entry(
            RemoveInitiativeEntryCommand(
                str(payload.command_id),
                payload.device_id,
                _client_time(payload.client_time),
                str(room_id),
                str(combat_id),
                payload.expected_version,
                str(entry_id),
            ),
            current,
        )
        await _publish(hub, outcome)
        return _response(outcome)

    @app.post(
        "/api/v2/rooms/{room_id}/combats/{combat_id}/reorder",
        response_model=LocalCommandResponse,
        tags=["combat"],
    )
    async def reorder(
        room_id: UUID, combat_id: UUID, payload: ReorderRequest, current: CurrentDevice
    ) -> LocalCommandResponse:
        _ensure_matching_device(payload.device_id, current)
        outcome = service.reorder(
            ReorderInitiativeCommand(
                str(payload.command_id),
                payload.device_id,
                _client_time(payload.client_time),
                str(room_id),
                str(combat_id),
                payload.expected_version,
                tuple(str(item) for item in payload.entry_ids),
            ),
            current,
        )
        await _publish(hub, outcome)
        return _response(outcome)

    @app.post(
        "/api/v2/rooms/{room_id}/combats/{combat_id}/transition",
        response_model=LocalCommandResponse,
        tags=["combat"],
    )
    async def transition(
        room_id: UUID, combat_id: UUID, payload: TransitionRequest, current: CurrentDevice
    ) -> LocalCommandResponse:
        _ensure_matching_device(payload.device_id, current)
        outcome = service.transition(
            TransitionCombatCommand(
                str(payload.command_id),
                payload.device_id,
                _client_time(payload.client_time),
                str(room_id),
                str(combat_id),
                payload.expected_version,
                payload.action,
            ),
            current,
        )
        await _publish(hub, outcome)
        return _response(outcome)

    @app.post(
        "/api/v2/rooms/{room_id}/combats/{combat_id}/turn",
        response_model=LocalCommandResponse,
        tags=["combat"],
    )
    async def move_turn(
        room_id: UUID, combat_id: UUID, payload: MoveTurnRequest, current: CurrentDevice
    ) -> LocalCommandResponse:
        _ensure_matching_device(payload.device_id, current)
        outcome = service.move_turn(
            MoveTurnCommand(
                str(payload.command_id),
                payload.device_id,
                _client_time(payload.client_time),
                str(room_id),
                str(combat_id),
                payload.expected_version,
                payload.direction,
            ),
            current,
        )
        await _publish(hub, outcome)
        return _response(outcome)

    @app.post(
        "/api/v2/rooms/{room_id}/combats/{combat_id}/health",
        response_model=LocalCommandResponse,
        tags=["combat"],
    )
    async def health(
        room_id: UUID, combat_id: UUID, payload: HealthRequest, current: CurrentDevice
    ) -> LocalCommandResponse:
        _ensure_matching_device(payload.device_id, current)
        outcome = service.apply_health(
            ApplyHealthCommand(
                str(payload.command_id),
                payload.device_id,
                _client_time(payload.client_time),
                str(room_id),
                str(combat_id),
                str(payload.source_id) if payload.source_id else None,
                _targets(payload.targets),
                payload.action,
                payload.amount,
                payload.prevented,
                payload.critical,
                str(payload.roll_id) if payload.roll_id else None,
            ),
            current,
        )
        await _publish(hub, outcome)
        return _response(outcome)

    @app.post(
        "/api/v2/rooms/{room_id}/combats/{combat_id}/combatants/{target_id}/conditions",
        response_model=LocalCommandResponse,
        tags=["combat"],
    )
    async def add_condition(
        room_id: UUID,
        combat_id: UUID,
        target_id: UUID,
        payload: ConditionRequest,
        current: CurrentDevice,
    ) -> LocalCommandResponse:
        _ensure_matching_device(payload.device_id, current)
        outcome = service.add_condition(
            AddConditionCommand(
                str(payload.command_id),
                payload.device_id,
                _client_time(payload.client_time),
                str(room_id),
                str(combat_id),
                str(target_id),
                payload.expected_version,
                payload.catalog_id,
                payload.name,
                payload.description,
                str(payload.source_id) if payload.source_id else None,
                payload.visible_to_players,
                payload.persistent,
            ),
            current,
        )
        await _publish(hub, outcome)
        return _response(outcome)

    @app.delete(
        "/api/v2/rooms/{room_id}/combats/{combat_id}/combatants/{target_id}/conditions/{condition_id}",
        response_model=LocalCommandResponse,
        tags=["combat"],
    )
    async def remove_condition(
        room_id: UUID,
        combat_id: UUID,
        target_id: UUID,
        condition_id: UUID,
        payload: CombatVersionRequest,
        current: CurrentDevice,
    ) -> LocalCommandResponse:
        _ensure_matching_device(payload.device_id, current)
        outcome = service.remove_condition(
            RemoveConditionCommand(
                str(payload.command_id),
                payload.device_id,
                _client_time(payload.client_time),
                str(room_id),
                str(combat_id),
                str(target_id),
                str(condition_id),
                payload.expected_version,
            ),
            current,
        )
        await _publish(hub, outcome)
        return _response(outcome)

    @app.post(
        "/api/v2/rooms/{room_id}/combats/{combat_id}/combatants/{target_id}/wound-display",
        response_model=LocalCommandResponse,
        tags=["combat"],
    )
    async def wound_display(
        room_id: UUID,
        combat_id: UUID,
        target_id: UUID,
        payload: WoundDisplayRequest,
        current: CurrentDevice,
    ) -> LocalCommandResponse:
        _ensure_matching_device(payload.device_id, current)
        outcome = service.set_wound_display(
            SetWoundDisplayCommand(
                str(payload.command_id),
                payload.device_id,
                _client_time(payload.client_time),
                str(room_id),
                str(combat_id),
                str(target_id),
                payload.expected_version,
                payload.show,
                payload.override,
            ),
            current,
        )
        await _publish(hub, outcome)
        return _response(outcome)

    @app.post(
        "/api/v2/rooms/{room_id}/combats/{combat_id}/rolls",
        response_model=LocalCommandResponse,
        status_code=201,
        tags=["dice"],
    )
    async def roll(
        room_id: UUID, combat_id: UUID, payload: RollRequest, current: CurrentDevice
    ) -> LocalCommandResponse:
        _ensure_matching_device(payload.device_id, current)
        outcome = service.roll(
            RollDiceCommand(
                str(payload.command_id),
                payload.device_id,
                _client_time(payload.client_time),
                str(room_id),
                str(combat_id),
                tuple(str(item) for item in payload.actor_ids),
                payload.expression,
                payload.mode,
                payload.visibility,
                str(payload.recipient_player_id) if payload.recipient_player_id else None,
                payload.physical_result,
                str(payload.action_event_id) if payload.action_event_id else None,
                payload.selection,
            ),
            current,
        )
        await _publish(hub, outcome)
        return _response(outcome)

    @app.post(
        "/api/v2/rooms/{room_id}/rolls/{roll_id}/edit",
        response_model=LocalCommandResponse,
        tags=["dice"],
    )
    async def edit_roll(
        room_id: UUID, roll_id: UUID, payload: EditRollRequest, current: CurrentDevice
    ) -> LocalCommandResponse:
        _ensure_matching_device(payload.device_id, current)
        outcome = service.edit_roll(
            EditRollCommand(
                str(payload.command_id),
                payload.device_id,
                _client_time(payload.client_time),
                str(room_id),
                str(roll_id),
                payload.result,
                payload.reason,
            ),
            current,
        )
        await _publish(hub, outcome)
        return _response(outcome)

    @app.post(
        "/api/v2/rooms/{room_id}/rolls/{roll_id}/reveal",
        response_model=LocalCommandResponse,
        tags=["dice"],
    )
    async def reveal_roll(
        room_id: UUID, roll_id: UUID, payload: CommandRequest, current: CurrentDevice
    ) -> LocalCommandResponse:
        _ensure_matching_device(payload.device_id, current)
        outcome = service.reveal_roll(
            RevealRollCommand(
                str(payload.command_id),
                payload.device_id,
                _client_time(payload.client_time),
                str(room_id),
                str(roll_id),
            ),
            current,
        )
        await _publish(hub, outcome)
        return _response(outcome)

    @app.post(
        "/api/v2/rooms/{room_id}/combats/{combat_id}/support",
        response_model=LocalCommandResponse,
        status_code=201,
        tags=["combat"],
    )
    async def support(
        room_id: UUID, combat_id: UUID, payload: SupportRequest, current: CurrentDevice
    ) -> LocalCommandResponse:
        _ensure_matching_device(payload.device_id, current)
        outcome = service.support(
            SupportCommand(
                str(payload.command_id),
                payload.device_id,
                _client_time(payload.client_time),
                str(room_id),
                str(combat_id),
                str(payload.character_id),
                payload.description,
                str(payload.roll_id) if payload.roll_id else None,
            ),
            current,
        )
        await _publish(hub, outcome)
        return _response(outcome)

    @app.post(
        "/api/v2/rooms/{room_id}/combats/{combat_id}/events/{event_id}/cancel",
        response_model=LocalCommandResponse,
        tags=["combat"],
    )
    async def cancel(
        room_id: UUID,
        combat_id: UUID,
        event_id: UUID,
        payload: CommandRequest,
        current: CurrentDevice,
    ) -> LocalCommandResponse:
        _ensure_matching_device(payload.device_id, current)
        outcome = service.cancel_health(
            CancelHealthCommand(
                str(payload.command_id),
                payload.device_id,
                _client_time(payload.client_time),
                str(room_id),
                str(combat_id),
                str(event_id),
            ),
            current,
        )
        await _publish(hub, outcome)
        return _response(outcome)

    @app.post(
        "/api/v2/rooms/{room_id}/combats/{combat_id}/events/{event_id}/correct",
        response_model=LocalCommandResponse,
        tags=["combat"],
    )
    async def correct(
        room_id: UUID,
        combat_id: UUID,
        event_id: UUID,
        payload: CorrectHealthRequest,
        current: CurrentDevice,
    ) -> LocalCommandResponse:
        _ensure_matching_device(payload.device_id, current)
        outcome = service.correct_health(
            CorrectHealthCommand(
                str(payload.command_id),
                payload.device_id,
                _client_time(payload.client_time),
                str(room_id),
                str(combat_id),
                str(event_id),
                str(payload.source_id) if payload.source_id else None,
                _targets(payload.targets),
                payload.action,
                payload.amount,
                payload.prevented,
                payload.critical,
                str(payload.roll_id) if payload.roll_id else None,
            ),
            current,
        )
        await _publish(hub, outcome)
        return _response(outcome)

    @app.get("/api/v2/rooms/{room_id}/combats/{combat_id}/report", tags=["combat"])
    async def report(room_id: UUID, combat_id: UUID, current: CurrentDevice) -> dict[str, Any]:
        # The service performs role and room checks consistently with command routes.
        return service.report(str(combat_id), current)
