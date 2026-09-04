from __future__ import annotations

import asyncio
import base64
import io
import socket
import time
from datetime import datetime
from ipaddress import ip_address
from typing import Annotated, Any
from uuid import UUID

import qrcode
from fastapi import (
    Cookie,
    Depends,
    FastAPI,
    Request,
    Response,
    WebSocket,
    WebSocketDisconnect,
    status,
)
from fastapi.responses import JSONResponse

from tabletop_companion.api.runtime import (
    EventHub,
    LiveConnection,
    SafeErrorLog,
    SlidingWindowRateLimiter,
)
from tabletop_companion.api.schemas import (
    AddInventoryItemRequest,
    BootstrapRoomRequest,
    CharacterLifecycleRequest,
    CharacterSelectRequest,
    CharacterUpdateRequest,
    ChooseAbilityCardRequest,
    CommandMeta,
    ConfirmCharacterDraftRequest,
    DeviceRevokeRequest,
    DiagnosticsView,
    DiscardInventoryItemRequest,
    EquipInventoryItemRequest,
    GmNotesUpdateRequest,
    LocalCommandResponse,
    NpcNoteCreateRequest,
    NpcNoteUpdateRequest,
    PairingCreateRequest,
    PairingExchangeRequest,
    ProfileCreateRequest,
    RestartCharacterDraftRequest,
    RoomDiceRollRequest,
    RoomInvitationCreateRequest,
    SessionCreateRequest,
    SessionTransitionRequest,
    SnapshotView,
    StartCharacterDraftRequest,
    WifiQrRequest,
)
from tabletop_companion.application.combat_service import CombatService
from tabletop_companion.application.commands import (
    AddInventoryItemCommand,
    CharacterLifecycleCommand,
    ChooseAbilityCardCommand,
    ConfirmCharacterDraftCommand,
    DiscardInventoryItemCommand,
    EquipInventoryItemCommand,
    RestartCharacterDraftCommand,
    StartCharacterDraftCommand,
)
from tabletop_companion.application.event_contracts import serialize_event
from tabletop_companion.application.local_commands import (
    BootstrapRoomCommand,
    CreateNpcNoteCommand,
    CreatePairingCommand,
    CreateProfileCommand,
    CreateRoomInvitationCommand,
    CreateSessionCommand,
    DeleteNpcNoteCommand,
    ExchangePairingCommand,
    GmAddInventoryItemCommand,
    GmDiscardInventoryItemCommand,
    KickPlayerCommand,
    RefreshDeviceCredentialCommand,
    RevokeDeviceCommand,
    RevokePairingCommand,
    RevokeRoomInvitationCommand,
    RollRoomDiceCommand,
    SelectCharacterCommand,
    TransitionSessionCommand,
    UpdateCharacterCommand,
    UpdateGmNotesCommand,
    UpdateNpcNoteCommand,
)
from tabletop_companion.application.local_service import LocalMultiplayerService
from tabletop_companion.application.replay import ReplayMode, choose_replay_mode
from tabletop_companion.application.service import CommandOutcome, CompanionService
from tabletop_companion.config import Settings
from tabletop_companion.domain.access import DeviceRole, LocalDevice
from tabletop_companion.domain.errors import (
    AuthenticationError,
    DomainValidationError,
    PermissionDeniedError,
    RateLimitError,
    UnsupportedEventVersionError,
)
from tabletop_companion.infrastructure.diagnostics import (
    database_diagnostics,
    local_addresses,
)

DEVICE_COOKIE = "ttc_device"
REALTIME_SCHEMA_VERSION = 1


def authenticated_device(
    request: Request,
    device_cookie: Annotated[str | None, Cookie(alias=DEVICE_COOKIE)] = None,
) -> LocalDevice:
    authorization = request.headers.get("authorization", "")
    bearer = authorization[7:] if authorization.lower().startswith("bearer ") else None
    service: LocalMultiplayerService = request.app.state.local_service
    return service.authenticate(bearer or device_cookie or "")


CurrentDevice = Annotated[LocalDevice, Depends(authenticated_device)]


def _client_time(value: datetime | None) -> str | None:
    return value.isoformat() if value else None


def _command_response(outcome: CommandOutcome) -> LocalCommandResponse:
    return LocalCommandResponse(
        data=outcome.data,
        meta=CommandMeta(replayed=outcome.replayed),
    )


def _set_device_cookie(response: Response, credential: str) -> None:
    response.set_cookie(
        DEVICE_COOKIE,
        credential,
        max_age=30 * 24 * 60 * 60,
        httponly=True,
        secure=False,
        samesite="strict",
        path="/",
    )


def _qr_data_url(value: str) -> str:
    image = qrcode.make(value)
    stream = io.BytesIO()
    image.save(stream)
    encoded = base64.b64encode(stream.getvalue()).decode("ascii")
    return f"data:image/png;base64,{encoded}"


def _wifi_qr_payload(ssid: str, security: str, password: str) -> str:
    def escaped(value: str) -> str:
        return value.replace("\\", "\\\\").replace(";", "\\;").replace(":", "\\:")

    return f"WIFI:T:{security};S:{escaped(ssid)};P:{escaped(password)};;"


def _client_key(request: Request, action: str) -> str:
    host = request.client.host if request.client else "unknown"
    return f"{action}:{host}"


def _pairing_origin(request: Request, settings: Settings) -> str:
    hostname = request.url.hostname or "127.0.0.1"
    try:
        loopback = ip_address(hostname).is_loopback
    except ValueError:
        loopback = hostname.lower() == "localhost"
    if loopback:
        hostname = next(
            (address for address in local_addresses() if not address.startswith("127.")),
            hostname,
        )
    host = f"[{hostname}]" if ":" in hostname else hostname
    return f"{request.url.scheme}://{host}:{settings.port}"


def _ensure_matching_device(payload_device_id: str, principal: LocalDevice) -> None:
    if payload_device_id != principal.id:
        raise PermissionDeniedError("Command device does not match the authenticated device.")


async def _publish(hub: EventHub, outcome: CommandOutcome) -> None:
    if not outcome.replayed:
        await hub.publish(outcome.events)


def register_local_routes(
    app: FastAPI,
    local_service: LocalMultiplayerService,
    companion_service: CompanionService,
    hub: EventHub,
    limiter: SlidingWindowRateLimiter,
    settings: Settings,
    started_at: float,
    safe_errors: SafeErrorLog,
    combat_service: CombatService,
) -> None:
    async def snapshot_with_presence(current: LocalDevice) -> dict[str, Any]:
        data = local_service.snapshot(current)
        data["combat"] = combat_service.snapshot(current)
        data["encounters"] = combat_service.encounters(current)
        presence = await hub.device_presence(current.room_id)
        devices = data.get("devices", [])
        if isinstance(devices, list):
            for item in devices:
                if isinstance(item, dict):
                    current_presence = presence.get(str(item.get("id")))
                    item["connection_state"] = (
                        current_presence["state"] if current_presence else "offline"
                    )
                    item["connection_count"] = (
                        current_presence["connections"] if current_presence else 0
                    )
        return data

    @app.post(
        "/api/v2/host/rooms",
        response_model=LocalCommandResponse,
        status_code=status.HTTP_201_CREATED,
        tags=["local multiplayer"],
    )
    async def bootstrap_room(
        request: Request, response: Response, payload: BootstrapRoomRequest
    ) -> LocalCommandResponse:
        client_host = request.client.host if request.client else ""
        if client_host not in {"127.0.0.1", "::1", "localhost", "testclient"}:
            raise PermissionDeniedError("Room creation is only available on the host device.")
        outcome = local_service.bootstrap_room(
            BootstrapRoomCommand(
                command_id=str(payload.command_id),
                device_id=payload.device_id,
                client_time=_client_time(payload.client_time),
                gm_id=str(payload.gm_id),
                name=payload.name,
                access_mode=payload.access_mode,
                password=payload.password,
                device_label=payload.device_label,
            )
        )
        credential = str(outcome.data.pop("device_credential"))
        _set_device_cookie(response, credential)
        await _publish(hub, outcome)
        return _command_response(outcome)

    @app.post(
        "/api/v2/rooms/{room_id}/pairing",
        response_model=LocalCommandResponse,
        status_code=status.HTTP_201_CREATED,
        tags=["pairing"],
    )
    async def create_pairing(
        request: Request,
        room_id: UUID,
        payload: PairingCreateRequest,
        current: CurrentDevice,
    ) -> LocalCommandResponse:
        _ensure_matching_device(payload.device_id, current)
        outcome = local_service.create_pairing(
            CreatePairingCommand(
                command_id=str(payload.command_id),
                device_id=current.id,
                client_time=_client_time(payload.client_time),
                room_id=str(room_id),
                actor_id=current.id,
                role=payload.role,
                ttl_seconds=payload.ttl_seconds,
            ),
            current,
        )
        token = str(outcome.data.pop("token"))
        fragment_path = f"/#/pair/{token}"
        origin = _pairing_origin(request, settings)
        pair_url = f"{origin}{fragment_path}"
        outcome.data.update(
            {
                "pair_url": pair_url,
                "qr_data_url": _qr_data_url(pair_url),
            }
        )
        await _publish(hub, outcome)
        return _command_response(outcome)

    @app.post("/api/v2/rooms/{room_id}/wifi-qr", tags=["pairing"])
    async def wifi_qr(
        room_id: UUID, payload: WifiQrRequest, current: CurrentDevice
    ) -> dict[str, str]:
        if current.role is not DeviceRole.GM or current.room_id != str(room_id):
            raise PermissionDeniedError("A GM device for this room is required.")
        if payload.security != "nopass" and not payload.password:
            raise DomainValidationError("A password is required for a protected Wi-Fi network.")
        return {
            "qr_data_url": _qr_data_url(
                _wifi_qr_payload(payload.ssid, payload.security, payload.password)
            )
        }

    @app.delete(
        "/api/v2/rooms/{room_id}/pairing/{invitation_id}",
        response_model=LocalCommandResponse,
        tags=["pairing"],
    )
    async def revoke_pairing(
        room_id: UUID,
        invitation_id: str,
        payload: DeviceRevokeRequest,
        current: CurrentDevice,
    ) -> LocalCommandResponse:
        _ensure_matching_device(payload.device_id, current)
        target = None if invitation_id == "all" else invitation_id
        outcome = local_service.revoke_pairing(
            RevokePairingCommand(
                command_id=str(payload.command_id),
                device_id=current.id,
                client_time=_client_time(payload.client_time),
                room_id=str(room_id),
                actor_id=current.id,
                invitation_id=target,
            ),
            current,
        )
        await _publish(hub, outcome)
        return _command_response(outcome)

    @app.post(
        "/api/v2/pairing/exchange",
        response_model=LocalCommandResponse,
        status_code=status.HTTP_201_CREATED,
        tags=["pairing"],
    )
    async def exchange_pairing(
        request: Request, response: Response, payload: PairingExchangeRequest
    ) -> LocalCommandResponse:
        limiter.check(_client_key(request, "pairing_exchange"), limit=12, window_seconds=60)
        outcome = local_service.exchange_pairing(
            ExchangePairingCommand(
                command_id=str(payload.command_id),
                device_id=payload.device_id,
                client_time=_client_time(payload.client_time),
                token=payload.token,
                short_code=payload.short_code.upper() if payload.short_code else None,
                device_label=payload.device_label,
            )
        )
        credential = str(outcome.data.pop("device_credential"))
        _set_device_cookie(response, credential)
        await _publish(hub, outcome)
        return _command_response(outcome)

    @app.post(
        "/api/v2/me/profile",
        response_model=LocalCommandResponse,
        status_code=status.HTTP_201_CREATED,
        tags=["local identity"],
    )
    async def create_profile(
        request: Request,
        payload: ProfileCreateRequest,
        current: CurrentDevice,
    ) -> LocalCommandResponse:
        _ensure_matching_device(payload.device_id, current)
        limiter.check(_client_key(request, "room_join"), limit=10, window_seconds=60)
        outcome = local_service.create_profile(
            CreateProfileCommand(
                command_id=str(payload.command_id),
                device_id=current.id,
                client_time=_client_time(payload.client_time),
                display_name=payload.display_name,
                password=payload.password,
                invitation_token=payload.invitation_token,
            ),
            current,
        )
        await _publish(hub, outcome)
        return _command_response(outcome)

    @app.get("/api/v2/me/snapshot", response_model=SnapshotView, tags=["local identity"])
    async def snapshot(current: CurrentDevice) -> SnapshotView:
        return SnapshotView.model_validate(await snapshot_with_presence(current))

    @app.post(
        "/api/v2/me/credential/refresh",
        response_model=LocalCommandResponse,
        tags=["local identity"],
    )
    async def refresh_credential(
        response: Response,
        payload: DeviceRevokeRequest,
        current: CurrentDevice,
    ) -> LocalCommandResponse:
        _ensure_matching_device(payload.device_id, current)
        outcome = local_service.refresh_device_credential(
            RefreshDeviceCredentialCommand(
                command_id=str(payload.command_id),
                device_id=current.id,
                client_time=_client_time(payload.client_time),
            ),
            current,
        )
        credential = str(outcome.data.pop("device_credential"))
        _set_device_cookie(response, credential)
        await _publish(hub, outcome)
        if not outcome.replayed:
            await hub.disconnect_device(current.id)
        return _command_response(outcome)

    @app.get("/api/v2/characters/{character_id}", tags=["characters"])
    async def get_character(character_id: UUID, current: CurrentDevice) -> dict[str, Any]:
        character = companion_service.get_character(str(character_id))
        if current.role is not DeviceRole.GM and character["account_id"] != (
            current.account_id or current.player_id
        ):
            raise PermissionDeniedError("The device does not control this character.")
        if not companion_service.character_is_assigned(str(character_id), current.room_id):
            raise PermissionDeniedError("Character does not belong to this room.")
        return character

    @app.get("/api/v2/character-options", tags=["characters"])
    async def character_options(current: CurrentDevice) -> dict[str, Any]:
        return local_service.character_catalog(current)

    @app.post(
        "/api/v2/rooms/{room_id}/rolls",
        response_model=LocalCommandResponse,
        status_code=status.HTTP_201_CREATED,
        tags=["dice"],
    )
    async def roll_room_dice(
        room_id: UUID, payload: RoomDiceRollRequest, current: CurrentDevice
    ) -> LocalCommandResponse:
        _ensure_matching_device(payload.device_id, current)
        outcome = local_service.roll_room_dice(
            RollRoomDiceCommand(
                command_id=str(payload.command_id),
                device_id=current.id,
                client_time=_client_time(payload.client_time),
                room_id=str(room_id),
                actor_id=current.id,
                expression=payload.expression,
                selection=payload.selection,
                visibility=payload.visibility,
                mode=payload.mode,
                recipient_player_id=(
                    str(payload.recipient_player_id) if payload.recipient_player_id else None
                ),
                physical_result=payload.physical_result,
            ),
            current,
        )
        await _publish(hub, outcome)
        return _command_response(outcome)

    async def diagnostic_data(current: LocalDevice) -> DiagnosticsView:
        if current.role is not DeviceRole.GM:
            raise PermissionDeniedError("GM access is required.")
        snapshot_data = await snapshot_with_presence(current)
        realtime_stats = await hub.stats(current.room_id)
        database = database_diagnostics(settings.database_url)
        return DiagnosticsView(
            hostname=socket.gethostname(),
            addresses=local_addresses(),
            port=settings.port,
            api_available=True,
            access_policy=str(snapshot_data["room"]["access_mode"]),
            websocket_connections=realtime_stats["connections"],
            reconnecting_clients=realtime_stats["reconnecting"],
            players=len(snapshot_data.get("players", [])),
            devices=len(snapshot_data.get("devices", [])),
            event_cursor=int(snapshot_data["cursor"]),
            sqlite_bytes=int(database["sqlite_bytes"]),
            sqlite_journal_mode=str(database["sqlite_journal_mode"]),
            free_disk_bytes=int(database["free_disk_bytes"]),
            uptime_seconds=int(time.monotonic() - started_at),
            backend_version="0.2.0-alpha.1",
            frontend_version="0.2.0-alpha.1",
            database_revision=str(database["database_revision"]),
            last_errors=safe_errors.snapshot(),
        )

    @app.get("/api/v2/host/diagnostics", response_model=DiagnosticsView, tags=["system"])
    async def diagnostics(current: CurrentDevice) -> DiagnosticsView:
        return await diagnostic_data(current)

    @app.get("/api/v2/host/diagnostics/export", tags=["system"])
    async def export_diagnostics(
        current: CurrentDevice,
    ) -> JSONResponse:
        report = await diagnostic_data(current)
        return JSONResponse(
            report.model_dump(mode="json"),
            headers={"Content-Disposition": 'attachment; filename="ttc-diagnostics.json"'},
        )

    @app.post(
        "/api/v2/me/character-drafts",
        response_model=LocalCommandResponse,
        status_code=status.HTTP_201_CREATED,
        tags=["characters"],
    )
    async def start_draft(
        payload: StartCharacterDraftRequest,
        current: CurrentDevice,
    ) -> LocalCommandResponse:
        _ensure_matching_device(payload.device_id, current)
        if current.player_id is None:
            raise PermissionDeniedError("Create a local profile first.")
        outcome = companion_service.start_character_draft(
            StartCharacterDraftCommand(
                command_id=str(payload.command_id),
                device_id=current.id,
                client_time=_client_time(payload.client_time),
                room_id=current.room_id,
                player_id=current.player_id,
                name=payload.name,
                race_id=payload.race_id,
                class_id=payload.class_id,
                species_choices=payload.species_choices,
                stat_method=payload.stat_method,
                stats=payload.stats,
                background_pattern=payload.background_pattern,
                background_stats=payload.background_stats,
                background_allocations=payload.background_allocations,
                ruleset_version="character-v2",
            )
        )
        await _publish(hub, outcome)
        return _command_response(outcome)

    @app.post(
        "/api/v2/character-drafts/{draft_id}/choices",
        response_model=LocalCommandResponse,
        tags=["characters"],
    )
    async def choose_card(
        draft_id: UUID,
        payload: ChooseAbilityCardRequest,
        current: CurrentDevice,
    ) -> LocalCommandResponse:
        _ensure_matching_device(payload.device_id, current)
        if current.player_id is None:
            raise PermissionDeniedError("Create a local profile first.")
        outcome = companion_service.choose_ability_card(
            ChooseAbilityCardCommand(
                command_id=str(payload.command_id),
                device_id=current.id,
                client_time=_client_time(payload.client_time),
                player_id=current.player_id,
                draft_id=str(draft_id),
                card_id=payload.card_id,
                expected_version=payload.expected_version,
            )
        )
        await _publish(hub, outcome)
        return _command_response(outcome)

    @app.post(
        "/api/v2/characters/{character_id}/inventory/{item_id}/equipment",
        response_model=LocalCommandResponse,
        tags=["inventory"],
    )
    async def equip_item(
        character_id: UUID,
        item_id: UUID,
        payload: EquipInventoryItemRequest,
        current: CurrentDevice,
    ) -> LocalCommandResponse:
        _ensure_matching_device(payload.device_id, current)
        if current.player_id is None or str(payload.actor_id) != current.player_id:
            raise PermissionDeniedError("The device does not control this character.")
        outcome = companion_service.equip_inventory_item(
            EquipInventoryItemCommand(
                command_id=str(payload.command_id),
                device_id=current.id,
                client_time=_client_time(payload.client_time),
                actor_id=current.player_id,
                character_id=str(character_id),
                item_id=str(item_id),
                slot=payload.slot,
                expected_version=payload.expected_version,
            )
        )
        await _publish(hub, outcome)
        return _command_response(outcome)

    @app.post(
        "/api/v2/me/characters/{character_id}/lifecycle",
        response_model=LocalCommandResponse,
        tags=["characters"],
    )
    async def character_lifecycle(
        character_id: UUID,
        payload: CharacterLifecycleRequest,
        current: CurrentDevice,
    ) -> LocalCommandResponse:
        _ensure_matching_device(payload.device_id, current)
        if current.player_id is None:
            raise PermissionDeniedError("Create a local profile first.")
        outcome = companion_service.change_character_lifecycle(
            CharacterLifecycleCommand(
                command_id=str(payload.command_id),
                device_id=current.id,
                client_time=_client_time(payload.client_time),
                actor_id=current.player_id,
                character_id=str(character_id),
                room_id=current.room_id,
                expected_version=payload.expected_version,
                action=payload.action,
            )
        )
        await _publish(hub, outcome)
        return _command_response(outcome)

    @app.post(
        "/api/v2/character-drafts/{draft_id}/restart",
        response_model=LocalCommandResponse,
        tags=["characters"],
    )
    async def restart_draft(
        draft_id: UUID,
        payload: RestartCharacterDraftRequest,
        current: CurrentDevice,
    ) -> LocalCommandResponse:
        _ensure_matching_device(payload.device_id, current)
        if current.player_id is None:
            raise PermissionDeniedError("Create a local profile first.")
        outcome = companion_service.restart_character_draft(
            RestartCharacterDraftCommand(
                command_id=str(payload.command_id),
                device_id=current.id,
                client_time=_client_time(payload.client_time),
                player_id=current.player_id,
                draft_id=str(draft_id),
                expected_version=payload.expected_version,
            )
        )
        await _publish(hub, outcome)
        return _command_response(outcome)

    @app.post(
        "/api/v2/character-drafts/{draft_id}/confirm",
        response_model=LocalCommandResponse,
        status_code=status.HTTP_201_CREATED,
        tags=["characters"],
    )
    async def confirm_draft(
        draft_id: UUID,
        payload: ConfirmCharacterDraftRequest,
        current: CurrentDevice,
    ) -> LocalCommandResponse:
        _ensure_matching_device(payload.device_id, current)
        if current.player_id is None:
            raise PermissionDeniedError("Create a local profile first.")
        outcome = companion_service.confirm_character_draft(
            ConfirmCharacterDraftCommand(
                command_id=str(payload.command_id),
                device_id=current.id,
                client_time=_client_time(payload.client_time),
                player_id=current.player_id,
                draft_id=str(draft_id),
                expected_version=payload.expected_version,
            )
        )
        await _publish(hub, outcome)
        return _command_response(outcome)

    @app.post(
        "/api/v2/me/characters/{character_id}/select",
        response_model=LocalCommandResponse,
        tags=["characters"],
    )
    async def select_character(
        character_id: UUID,
        payload: CharacterSelectRequest,
        current: CurrentDevice,
    ) -> LocalCommandResponse:
        _ensure_matching_device(payload.device_id, current)
        if current.player_id is None:
            raise PermissionDeniedError("Create a local profile first.")
        if str(payload.character_id) != str(character_id):
            raise PermissionDeniedError("Character path and command do not match.")
        outcome = local_service.select_character(
            SelectCharacterCommand(
                command_id=str(payload.command_id),
                device_id=current.id,
                client_time=_client_time(payload.client_time),
                player_id=current.player_id,
                character_id=str(character_id),
                expected_version=payload.expected_version,
            ),
            current,
        )
        await _publish(hub, outcome)
        return _command_response(outcome)

    @app.post(
        "/api/v2/characters/{character_id}/inventory",
        response_model=LocalCommandResponse,
        status_code=status.HTTP_201_CREATED,
        tags=["inventory"],
    )
    async def add_item(
        character_id: UUID,
        payload: AddInventoryItemRequest,
        current: CurrentDevice,
    ) -> LocalCommandResponse:
        _ensure_matching_device(payload.device_id, current)
        if current.player_id is None or str(payload.actor_id) != current.player_id:
            raise PermissionDeniedError("The device does not control this character.")
        outcome = companion_service.add_inventory_item(
            AddInventoryItemCommand(
                command_id=str(payload.command_id),
                device_id=current.id,
                client_time=_client_time(payload.client_time),
                actor_id=current.player_id,
                character_id=str(character_id),
                name=payload.name,
                quantity=payload.quantity,
                consumable=payload.consumable,
                locked=payload.locked,
                equipped=payload.equipped,
                charges=payload.charges,
                expected_version=payload.expected_version,
                unit_weight=payload.unit_weight,
                slot_compatibility=payload.slot_compatibility,
            )
        )
        await _publish(hub, outcome)
        return _command_response(outcome)

    @app.post(
        "/api/v2/characters/{character_id}/inventory/{item_id}/discard",
        response_model=LocalCommandResponse,
        tags=["inventory"],
    )
    async def discard_item(
        character_id: UUID,
        item_id: UUID,
        payload: DiscardInventoryItemRequest,
        current: CurrentDevice,
    ) -> LocalCommandResponse:
        _ensure_matching_device(payload.device_id, current)
        if current.player_id is None or str(payload.actor_id) != current.player_id:
            raise PermissionDeniedError("The device does not control this character.")
        outcome = companion_service.discard_inventory_item(
            DiscardInventoryItemCommand(
                command_id=str(payload.command_id),
                device_id=current.id,
                client_time=_client_time(payload.client_time),
                actor_id=current.player_id,
                character_id=str(character_id),
                item_id=str(item_id),
                quantity=payload.quantity,
                expected_version=payload.expected_version,
            )
        )
        await _publish(hub, outcome)
        return _command_response(outcome)

    @app.post(
        "/api/v2/rooms/{room_id}/invitations",
        response_model=LocalCommandResponse,
        status_code=status.HTTP_201_CREATED,
        tags=["room access"],
    )
    async def create_room_invitation(
        room_id: UUID,
        payload: RoomInvitationCreateRequest,
        current: CurrentDevice,
    ) -> LocalCommandResponse:
        _ensure_matching_device(payload.device_id, current)
        outcome = local_service.create_room_invitation(
            CreateRoomInvitationCommand(
                command_id=str(payload.command_id),
                device_id=current.id,
                client_time=_client_time(payload.client_time),
                room_id=str(room_id),
                actor_id=current.id,
                ttl_seconds=payload.ttl_seconds,
                max_uses=payload.max_uses,
            ),
            current,
        )
        await _publish(hub, outcome)
        return _command_response(outcome)

    @app.delete(
        "/api/v2/rooms/{room_id}/invitations/{invitation_id}",
        response_model=LocalCommandResponse,
        tags=["room access"],
    )
    async def revoke_room_invitation(
        room_id: UUID,
        invitation_id: UUID,
        payload: DeviceRevokeRequest,
        current: CurrentDevice,
    ) -> LocalCommandResponse:
        _ensure_matching_device(payload.device_id, current)
        outcome = local_service.revoke_room_invitation(
            RevokeRoomInvitationCommand(
                command_id=str(payload.command_id),
                device_id=current.id,
                client_time=_client_time(payload.client_time),
                room_id=str(room_id),
                actor_id=current.id,
                invitation_id=str(invitation_id),
            ),
            current,
        )
        await _publish(hub, outcome)
        return _command_response(outcome)

    @app.post(
        "/api/v2/rooms/{room_id}/sessions",
        response_model=LocalCommandResponse,
        status_code=status.HTTP_201_CREATED,
        tags=["sessions"],
    )
    async def create_session(
        room_id: UUID,
        payload: SessionCreateRequest,
        current: CurrentDevice,
    ) -> LocalCommandResponse:
        _ensure_matching_device(payload.device_id, current)
        outcome = local_service.create_session(
            CreateSessionCommand(
                command_id=str(payload.command_id),
                device_id=current.id,
                client_time=_client_time(payload.client_time),
                room_id=str(room_id),
                actor_id=current.id,
            ),
            current,
        )
        await _publish(hub, outcome)
        return _command_response(outcome)

    @app.post(
        "/api/v2/rooms/{room_id}/sessions/{session_id}/transition",
        response_model=LocalCommandResponse,
        tags=["sessions"],
    )
    async def transition_session(
        room_id: UUID,
        session_id: UUID,
        payload: SessionTransitionRequest,
        current: CurrentDevice,
    ) -> LocalCommandResponse:
        _ensure_matching_device(payload.device_id, current)
        outcome = local_service.transition_session(
            TransitionSessionCommand(
                command_id=str(payload.command_id),
                device_id=current.id,
                client_time=_client_time(payload.client_time),
                room_id=str(room_id),
                actor_id=current.id,
                session_id=str(session_id),
                target_status=payload.target_status,
                expected_version=payload.expected_version,
            ),
            current,
        )
        await _publish(hub, outcome)
        return _command_response(outcome)

    @app.delete(
        "/api/v2/rooms/{room_id}/devices/{device_id}",
        response_model=LocalCommandResponse,
        tags=["devices"],
    )
    async def revoke_device(
        room_id: UUID,
        device_id: UUID,
        payload: DeviceRevokeRequest,
        current: CurrentDevice,
    ) -> LocalCommandResponse:
        _ensure_matching_device(payload.device_id, current)
        outcome = local_service.revoke_device(
            RevokeDeviceCommand(
                command_id=str(payload.command_id),
                device_id=current.id,
                client_time=_client_time(payload.client_time),
                room_id=str(room_id),
                actor_id=current.id,
                target_device_id=str(device_id),
            ),
            current,
        )
        await _publish(hub, outcome)
        if not outcome.replayed:
            await hub.disconnect_device(str(device_id))
        return _command_response(outcome)

    @app.delete(
        "/api/v2/rooms/{room_id}/players/{player_id}",
        response_model=LocalCommandResponse,
        tags=["lobby"],
    )
    async def kick_player(
        room_id: UUID,
        player_id: UUID,
        payload: DeviceRevokeRequest,
        current: CurrentDevice,
    ) -> LocalCommandResponse:
        _ensure_matching_device(payload.device_id, current)
        outcome = local_service.kick_player(
            KickPlayerCommand(
                command_id=str(payload.command_id),
                device_id=current.id,
                client_time=_client_time(payload.client_time),
                room_id=str(room_id),
                actor_id=current.id,
                player_id=str(player_id),
            ),
            current,
        )
        await _publish(hub, outcome)
        if not outcome.replayed:
            for target_device_id in outcome.data["device_ids"]:
                await hub.disconnect_device(str(target_device_id))
        return _command_response(outcome)

    @app.put(
        "/api/v2/rooms/{room_id}/characters/{character_id}",
        response_model=LocalCommandResponse,
        tags=["characters"],
    )
    async def update_character(
        room_id: UUID,
        character_id: UUID,
        payload: CharacterUpdateRequest,
        current: CurrentDevice,
    ) -> LocalCommandResponse:
        _ensure_matching_device(payload.device_id, current)
        outcome = local_service.update_character(
            UpdateCharacterCommand(
                command_id=str(payload.command_id),
                device_id=current.id,
                client_time=_client_time(payload.client_time),
                room_id=str(room_id),
                actor_id=current.id,
                character_id=str(character_id),
                name=payload.name,
                race_id=payload.race_id,
                class_id=payload.class_id,
                stats=payload.stats,
                ability_ids=tuple(payload.ability_ids),
                max_hp=payload.max_hp,
                current_hp=payload.current_hp,
                armor_class=payload.armor_class,
                expected_version=payload.expected_version,
                temporary_hp=payload.temporary_hp,
                level=payload.level,
                experience=payload.experience,
                initiative=payload.initiative,
                proficiency_bonus=payload.proficiency_bonus,
                size=payload.size,
                speed=payload.speed,
                darkvision=payload.darkvision,
                species_choices=payload.species_choices,
                persistent_conditions=payload.persistent_conditions,
            ),
            current,
        )
        await _publish(hub, outcome)
        return _command_response(outcome)

    @app.post(
        "/api/v2/rooms/{room_id}/characters/{character_id}/inventory",
        response_model=LocalCommandResponse,
        status_code=status.HTTP_201_CREATED,
        tags=["characters"],
    )
    async def gm_add_inventory_item(
        room_id: UUID,
        character_id: UUID,
        payload: AddInventoryItemRequest,
        current: CurrentDevice,
    ) -> LocalCommandResponse:
        _ensure_matching_device(payload.device_id, current)
        outcome = local_service.gm_add_inventory_item(
            GmAddInventoryItemCommand(
                command_id=str(payload.command_id),
                device_id=current.id,
                client_time=_client_time(payload.client_time),
                room_id=str(room_id),
                actor_id=current.id,
                character_id=str(character_id),
                name=payload.name,
                expected_version=payload.expected_version,
            ),
            current,
        )
        await _publish(hub, outcome)
        return _command_response(outcome)

    @app.post(
        "/api/v2/rooms/{room_id}/characters/{character_id}/inventory/{item_id}/discard",
        response_model=LocalCommandResponse,
        tags=["characters"],
    )
    async def gm_discard_inventory_item(
        room_id: UUID,
        character_id: UUID,
        item_id: UUID,
        payload: DiscardInventoryItemRequest,
        current: CurrentDevice,
    ) -> LocalCommandResponse:
        _ensure_matching_device(payload.device_id, current)
        outcome = local_service.gm_discard_inventory_item(
            GmDiscardInventoryItemCommand(
                command_id=str(payload.command_id),
                device_id=current.id,
                client_time=_client_time(payload.client_time),
                room_id=str(room_id),
                actor_id=current.id,
                character_id=str(character_id),
                item_id=str(item_id),
                expected_version=payload.expected_version,
            ),
            current,
        )
        await _publish(hub, outcome)
        return _command_response(outcome)

    @app.get("/api/v2/rooms/{room_id}/notes", tags=["gm notes"])
    async def get_gm_notes(room_id: UUID, current: CurrentDevice) -> dict[str, Any]:
        if str(room_id) != current.room_id:
            raise PermissionDeniedError("Room does not match the authenticated device.")
        return local_service.get_gm_notes(current)

    @app.put(
        "/api/v2/rooms/{room_id}/notes",
        response_model=LocalCommandResponse,
        tags=["gm notes"],
    )
    async def update_gm_notes(
        room_id: UUID,
        payload: GmNotesUpdateRequest,
        current: CurrentDevice,
    ) -> LocalCommandResponse:
        _ensure_matching_device(payload.device_id, current)
        outcome = local_service.update_gm_notes(
            UpdateGmNotesCommand(
                command_id=str(payload.command_id),
                device_id=current.id,
                client_time=_client_time(payload.client_time),
                room_id=str(room_id),
                actor_id=current.id,
                campaign=payload.campaign,
                other=payload.other,
                expected_version=payload.expected_version,
            ),
            current,
        )
        await _publish(hub, outcome)
        return _command_response(outcome)

    @app.post(
        "/api/v2/rooms/{room_id}/notes/npcs",
        response_model=LocalCommandResponse,
        status_code=status.HTTP_201_CREATED,
        tags=["gm notes"],
    )
    async def create_npc_note(
        room_id: UUID,
        payload: NpcNoteCreateRequest,
        current: CurrentDevice,
    ) -> LocalCommandResponse:
        _ensure_matching_device(payload.device_id, current)
        outcome = local_service.create_npc_note(
            CreateNpcNoteCommand(
                command_id=str(payload.command_id),
                device_id=current.id,
                client_time=_client_time(payload.client_time),
                room_id=str(room_id),
                actor_id=current.id,
                name=payload.name,
            ),
            current,
        )
        await _publish(hub, outcome)
        return _command_response(outcome)

    @app.put(
        "/api/v2/rooms/{room_id}/notes/npcs/{npc_id}",
        response_model=LocalCommandResponse,
        tags=["gm notes"],
    )
    async def update_npc_note(
        room_id: UUID,
        npc_id: UUID,
        payload: NpcNoteUpdateRequest,
        current: CurrentDevice,
    ) -> LocalCommandResponse:
        _ensure_matching_device(payload.device_id, current)
        outcome = local_service.update_npc_note(
            UpdateNpcNoteCommand(
                command_id=str(payload.command_id),
                device_id=current.id,
                client_time=_client_time(payload.client_time),
                room_id=str(room_id),
                actor_id=current.id,
                npc_id=str(npc_id),
                name=payload.name,
                details=payload.details,
                expected_version=payload.expected_version,
            ),
            current,
        )
        await _publish(hub, outcome)
        return _command_response(outcome)

    @app.delete(
        "/api/v2/rooms/{room_id}/notes/npcs/{npc_id}",
        response_model=LocalCommandResponse,
        tags=["gm notes"],
    )
    async def delete_npc_note(
        room_id: UUID,
        npc_id: UUID,
        payload: DeviceRevokeRequest,
        current: CurrentDevice,
    ) -> LocalCommandResponse:
        _ensure_matching_device(payload.device_id, current)
        outcome = local_service.delete_npc_note(
            DeleteNpcNoteCommand(
                command_id=str(payload.command_id),
                device_id=current.id,
                client_time=_client_time(payload.client_time),
                room_id=str(room_id),
                actor_id=current.id,
                npc_id=str(npc_id),
            ),
            current,
        )
        await _publish(hub, outcome)
        return _command_response(outcome)

    @app.websocket("/api/v2/realtime")
    async def realtime(websocket: WebSocket, cursor: int = 0) -> None:
        connection: LiveConnection | None = None
        try:
            host = websocket.client.host if websocket.client else "unknown"
            limiter.check(f"websocket:{host}", limit=120, window_seconds=60)
            credential = websocket.cookies.get(DEVICE_COOKIE, "")
            device = local_service.authenticate(credential, touch=False)
            if cursor < 0:
                raise UnsupportedEventVersionError("Realtime cursor must not be negative.")
            connection = await hub.connect(websocket, device, last_cursor=cursor)
            await websocket.accept()
            minimum, maximum = local_service.cursor_bounds(device.room_id)
            mode = choose_replay_mode(
                last_cursor=cursor,
                minimum_cursor=minimum,
                maximum_cursor=maximum,
                replay_limit=500,
            )
            if mode is ReplayMode.SNAPSHOT:
                snapshot_data = await snapshot_with_presence(device)
                await websocket.send_json(
                    {
                        "type": "snapshot",
                        "schema_version": REALTIME_SCHEMA_VERSION,
                        "cursor": snapshot_data["cursor"],
                        "payload": snapshot_data,
                    }
                )
                connection.last_cursor = int(snapshot_data["cursor"])
            else:
                for event in local_service.replay_events(device, cursor):
                    await websocket.send_json(
                        serialize_event(combat_service.project_event(event, device))
                    )
                    connection.last_cursor = max(connection.last_cursor, event.cursor or 0)
            connection.reconnecting = False
            await _realtime_loop(connection)
        except (AuthenticationError, PermissionDeniedError, RateLimitError):
            if connection is None:
                await websocket.close(code=4401, reason="authentication_failed")
        except UnsupportedEventVersionError:
            await websocket.close(code=4400, reason="unsupported_schema")
        except WebSocketDisconnect:
            pass
        finally:
            if connection is not None:
                await hub.disconnect(connection)


async def _realtime_loop(connection: LiveConnection) -> None:
    missed_heartbeats = 0
    while True:
        receive_task = asyncio.create_task(connection.websocket.receive_json())
        event_task = asyncio.create_task(connection.queue.get())
        done, pending = await asyncio.wait(
            {receive_task, event_task}, timeout=20, return_when=asyncio.FIRST_COMPLETED
        )
        for task in pending:
            task.cancel()
        if pending:
            await asyncio.gather(*pending, return_exceptions=True)
        if not done:
            missed_heartbeats += 1
            if missed_heartbeats > 2:
                await connection.websocket.close(code=4000, reason="heartbeat_timeout")
                return
            await connection.websocket.send_json(
                {"type": "ping", "schema_version": REALTIME_SCHEMA_VERSION}
            )
            continue
        if event_task in done:
            envelope = event_task.result()
            cursor_value = envelope["cursor"]
            if not isinstance(cursor_value, int):
                await connection.websocket.close(code=1011, reason="invalid_event_cursor")
                return
            cursor = cursor_value
            if cursor > connection.last_cursor:
                await connection.websocket.send_json(envelope)
                connection.last_cursor = cursor
        if receive_task in done:
            message: dict[str, Any] = receive_task.result()
            if message.get("schema_version") != REALTIME_SCHEMA_VERSION:
                await connection.websocket.close(code=4400, reason="unsupported_schema")
                return
            if message.get("type") not in {"pong", "ack"}:
                await connection.websocket.close(code=4400, reason="invalid_message")
                return
            missed_heartbeats = 0
            if message.get("type") == "ack" and isinstance(message.get("cursor"), int):
                connection.last_cursor = max(connection.last_cursor, int(message["cursor"]))
