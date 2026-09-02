from __future__ import annotations

import logging
import secrets
from collections.abc import Callable
from dataclasses import asdict, replace
from datetime import UTC, datetime, timedelta
from typing import Any, TypeVar, cast
from uuid import uuid4

from tabletop_companion.application.fingerprints import command_fingerprint
from tabletop_companion.application.local_commands import (
    BootstrapRoomCommand,
    CreatePairingCommand,
    CreateProfileCommand,
    CreateRoomInvitationCommand,
    CreateSessionCommand,
    ExchangePairingCommand,
    RecoverProfileCommand,
    RefreshDeviceCredentialCommand,
    RevokeDeviceCommand,
    RevokePairingCommand,
    RevokeRoomInvitationCommand,
    SelectCharacterCommand,
    TransitionSessionCommand,
)
from tabletop_companion.application.local_ports import LocalMultiplayerUnitOfWork
from tabletop_companion.application.ports import ProcessedCommand
from tabletop_companion.application.security import RoomPasswordHasher, SecretDigester
from tabletop_companion.application.service import CommandOutcome, ResultData
from tabletop_companion.domain.access import (
    DeviceRole,
    DeviceStatus,
    LocalDevice,
    PairingInvitation,
    PasswordPolicy,
    RoomInvitation,
)
from tabletop_companion.domain.errors import (
    AuthenticationError,
    DomainValidationError,
    EntityNotFoundError,
    IdempotencyConflictError,
    PermissionDeniedError,
    StateConflictError,
)
from tabletop_companion.domain.events import DomainEvent
from tabletop_companion.domain.models import AccessMode, LocalPlayer, Room
from tabletop_companion.domain.rules import SimpleRuleset
from tabletop_companion.domain.sessions import GameSession, SessionStatus

CommandT = TypeVar("CommandT")
LocalUnitOfWorkFactory = Callable[[], LocalMultiplayerUnitOfWork]

logger = logging.getLogger(__name__)


class LocalMultiplayerService:
    def __init__(
        self,
        *,
        uow_factory: LocalUnitOfWorkFactory,
        ruleset: SimpleRuleset,
        digester: SecretDigester,
        password_hasher: RoomPasswordHasher,
        id_factory: Callable[[], str] | None = None,
        clock: Callable[[], datetime] | None = None,
    ) -> None:
        self._uow_factory = uow_factory
        self._ruleset = ruleset
        self._digester = digester
        self._password_hasher = password_hasher
        self._id_factory = id_factory or (lambda: str(uuid4()))
        self._clock = clock or (lambda: datetime.now(UTC))
        self._password_policy = PasswordPolicy()

    def bootstrap_room(self, command: BootstrapRoomCommand) -> CommandOutcome:
        credential = self._digester.derive(
            "host-device-credential", f"{command.command_id}:{command.device_id}"
        )

        def operation(uow: LocalMultiplayerUnitOfWork) -> ResultData:
            password_hash: str | None = None
            if command.access_mode is AccessMode.PASSWORD:
                if command.password is None:
                    raise DomainValidationError("A password is required for this room.")
                self._password_policy.validate(command.password)
                password_hash = self._password_hasher.hash(command.password)
            elif command.password is not None:
                raise DomainValidationError("Password is only valid for a password room.")
            now = self._clock()
            room = Room(
                id=self._id_factory(),
                name=command.name.strip(),
                gm_id=command.gm_id,
                access_mode=command.access_mode,
                ruleset_version=self._ruleset.version,
                version=1,
                created_at=now,
                code=self._room_code(command.command_id),
                password_hash=password_hash,
            )
            if not room.name:
                raise DomainValidationError("Room name must not be blank.")
            device = LocalDevice(
                id=self._id_factory(),
                room_id=room.id,
                label=command.device_label.strip() or "GM device",
                role=DeviceRole.GM,
                credential_digest=self._digester.digest(credential),
                status=DeviceStatus.ACTIVE,
                created_at=now,
                last_seen_at=now,
                expires_at=now + timedelta(days=30),
            )
            uow.add_room(room)
            uow.add_local_device(device)
            uow.add_event(
                self._event(
                    event_type="RoomCreated",
                    aggregate_type="room",
                    aggregate_id=room.id,
                    room_id=room.id,
                    actor_id=command.gm_id,
                    command_id=command.command_id,
                    payload={
                        "name": room.name,
                        "access_mode": room.access_mode.value,
                        "ruleset_version": room.ruleset_version,
                    },
                )
            )
            return {"room": self._room_data(room), "device": self._device_data(device)}

        outcome = self._execute("bootstrap_room", command, command.gm_id, operation)
        outcome.data["device_credential"] = credential
        return outcome

    def authenticate(self, credential: str, *, touch: bool = True) -> LocalDevice:
        if not credential:
            raise AuthenticationError("A device credential is required.")
        try:
            with self._uow_factory() as uow:
                device = uow.get_device_by_credential_digest(self._digester.digest(credential))
                device.authenticate(self._clock())
                if touch:
                    device.touch(self._clock())
                    uow.save_local_device(device)
                    uow.commit()
                return device
        except EntityNotFoundError as error:
            raise AuthenticationError("Device credential is invalid.") from error

    def create_pairing(
        self, command: CreatePairingCommand, principal: LocalDevice
    ) -> CommandOutcome:
        self._ensure_gm(principal, command.room_id, command.actor_id)
        token = self._digester.derive("pairing-token", command.command_id)
        short_code = self._short_code(command.command_id)

        def operation(uow: LocalMultiplayerUnitOfWork) -> ResultData:
            if not 30 <= command.ttl_seconds <= 900:
                raise DomainValidationError("Pairing TTL must be between 30 and 900 seconds.")
            now = self._clock()
            invitation = PairingInvitation(
                id=self._id_factory(),
                room_id=command.room_id,
                role=command.role,
                token_digest=self._digester.digest(token),
                short_code_digest=self._digester.digest(short_code),
                expires_at=now + timedelta(seconds=command.ttl_seconds),
                created_by=principal.id,
                created_at=now,
            )
            uow.add_pairing_invitation(invitation)
            uow.add_event(
                self._event(
                    event_type="PairingInvitationCreated",
                    aggregate_type="pairing_invitation",
                    aggregate_id=invitation.id,
                    room_id=invitation.room_id,
                    actor_id=command.actor_id,
                    command_id=command.command_id,
                    payload={
                        "expires_at": invitation.expires_at.isoformat(),
                        "role": invitation.role.value,
                    },
                    visibility="gm",
                )
            )
            return {
                "id": invitation.id,
                "room_id": invitation.room_id,
                "expires_at": invitation.expires_at.isoformat(),
            }

        outcome = self._execute("create_pairing", command, command.actor_id, operation)
        outcome.data.update({"token": token, "short_code": short_code})
        return outcome

    def exchange_pairing(self, command: ExchangePairingCommand) -> CommandOutcome:
        supplied = command.token or command.short_code
        if supplied is None or (command.token is not None and command.short_code is not None):
            raise DomainValidationError("Provide exactly one pairing token or short code.")
        credential = self._digester.derive(
            "player-device-credential", f"{command.command_id}:{command.device_id}"
        )

        def operation(uow: LocalMultiplayerUnitOfWork) -> ResultData:
            try:
                if command.token is not None:
                    invitation = uow.get_pairing_by_token_digest(
                        self._digester.digest(command.token)
                    )
                else:
                    invitation = uow.get_pairing_by_short_code_digest(
                        self._digester.digest(cast(str, command.short_code).upper())
                    )
            except EntityNotFoundError as error:
                raise AuthenticationError("Pairing credential is invalid.") from error
            now = self._clock()
            invitation.consume(now)
            device = LocalDevice(
                id=self._id_factory(),
                room_id=invitation.room_id,
                label=command.device_label.strip() or "Player device",
                role=invitation.role,
                credential_digest=self._digester.digest(credential),
                status=DeviceStatus.ACTIVE,
                created_at=now,
                last_seen_at=now,
                expires_at=now + timedelta(days=30),
            )
            uow.save_pairing_invitation(invitation)
            uow.add_local_device(device)
            uow.add_event(
                self._event(
                    event_type="DevicePaired",
                    aggregate_type="local_device",
                    aggregate_id=device.id,
                    room_id=device.room_id,
                    actor_id=device.id,
                    command_id=command.command_id,
                    payload={"device_id": device.id, "role": device.role.value},
                    visibility="gm",
                )
            )
            return {"device": self._device_data(device)}

        outcome = self._execute(
            "exchange_pairing", command, f"pairing:{self._digester.digest(supplied)}", operation
        )
        outcome.data["device_credential"] = credential
        return outcome

    def revoke_pairing(
        self, command: RevokePairingCommand, principal: LocalDevice
    ) -> CommandOutcome:
        self._ensure_gm(principal, command.room_id, command.actor_id)

        def operation(uow: LocalMultiplayerUnitOfWork) -> ResultData:
            now = self._clock()
            if command.invitation_id is None:
                count = uow.revoke_pairing_invitations(command.room_id, now.isoformat())
                aggregate_id = command.room_id
            else:
                invitation = uow.get_pairing(command.invitation_id)
                if invitation.room_id != command.room_id:
                    raise PermissionDeniedError("Pairing invitation does not belong to this room.")
                invitation.revoke(now)
                uow.save_pairing_invitation(invitation)
                count = 1
                aggregate_id = invitation.id
            uow.add_event(
                self._event(
                    event_type="PairingInvitationsRevoked",
                    aggregate_type="pairing_invitation",
                    aggregate_id=aggregate_id,
                    room_id=command.room_id,
                    actor_id=command.actor_id,
                    command_id=command.command_id,
                    payload={"count": count},
                    visibility="gm",
                )
            )
            return {"revoked": count}

        return self._execute("revoke_pairing", command, command.actor_id, operation)

    def create_profile(
        self, command: CreateProfileCommand, principal: LocalDevice
    ) -> CommandOutcome:
        self._ensure_player_device(principal)
        recovery_code = self._digester.derive("profile-recovery", command.command_id)

        def operation(uow: LocalMultiplayerUnitOfWork) -> ResultData:
            device = uow.get_device(principal.id)
            device.authenticate(self._clock())
            if device.player_id is not None:
                raise StateConflictError("Device is already attached to a local profile.")
            room = uow.get_room(device.room_id)
            self._authorize_room_join(uow, room, command.password, command.invitation_token)
            now = self._clock()
            player = LocalPlayer(
                id=self._id_factory(),
                room_id=room.id,
                display_name=command.display_name.strip(),
                version=1,
                created_at=now,
                recovery_code_digest=self._digester.digest(recovery_code),
                updated_at=now,
            )
            if not player.display_name:
                raise DomainValidationError("Player display name must not be blank.")
            device.attach_player(player.id, now)
            uow.add_local_player(player)
            uow.save_local_device(device)
            uow.add_event(
                self._event(
                    event_type="LocalPlayerJoined",
                    aggregate_type="local_player",
                    aggregate_id=player.id,
                    room_id=room.id,
                    actor_id=player.id,
                    command_id=command.command_id,
                    payload={"display_name": player.display_name},
                )
            )
            return {"player": self._player_data(player), "device": self._device_data(device)}

        outcome = self._execute("create_profile", command, principal.id, operation)
        outcome.data["recovery_code"] = recovery_code
        return outcome

    def recover_profile(
        self, command: RecoverProfileCommand, principal: LocalDevice
    ) -> CommandOutcome:
        self._ensure_player_device(principal)

        def operation(uow: LocalMultiplayerUnitOfWork) -> ResultData:
            device = uow.get_device(principal.id)
            player = uow.get_local_player(command.player_id)
            if player.room_id != device.room_id or player.recovery_code_digest is None:
                raise AuthenticationError("Recovery credential is invalid.")
            if not secrets.compare_digest(
                player.recovery_code_digest, self._digester.digest(command.recovery_code)
            ):
                raise AuthenticationError("Recovery credential is invalid.")
            device.attach_player(player.id, self._clock())
            uow.save_local_device(device)
            uow.add_event(
                self._event(
                    event_type="LocalProfileRecovered",
                    aggregate_type="local_player",
                    aggregate_id=player.id,
                    room_id=player.room_id,
                    actor_id=player.id,
                    command_id=command.command_id,
                    payload={"device_id": device.id},
                    visibility="gm",
                )
            )
            return {"player": self._player_data(player), "device": self._device_data(device)}

        return self._execute("recover_profile", command, principal.id, operation)

    def select_character(
        self, command: SelectCharacterCommand, principal: LocalDevice
    ) -> CommandOutcome:
        self._ensure_player(principal, command.player_id)

        def operation(uow: LocalMultiplayerUnitOfWork) -> ResultData:
            player = uow.get_local_player(command.player_id)
            character = uow.get_character(command.character_id)
            if character.owner_id != player.id or character.room_id != principal.room_id:
                raise PermissionDeniedError("The player does not control this character.")
            if player.version != command.expected_version:
                raise StateConflictError(
                    "Player profile version is stale.",
                    details={
                        "expected_version": command.expected_version,
                        "current_version": player.version,
                        "current_state": self._player_data(player),
                    },
                )
            updated = replace(
                player,
                selected_character_id=character.id,
                version=player.version + 1,
                updated_at=self._clock(),
            )
            uow.save_local_player(updated)
            uow.add_event(
                self._event(
                    event_type="CharacterSelected",
                    aggregate_type="local_player",
                    aggregate_id=player.id,
                    room_id=player.room_id,
                    actor_id=player.id,
                    command_id=command.command_id,
                    payload={"character_id": character.id},
                )
            )
            return self._player_data(updated)

        return self._execute("select_character", command, command.player_id, operation)

    def create_room_invitation(
        self, command: CreateRoomInvitationCommand, principal: LocalDevice
    ) -> CommandOutcome:
        self._ensure_gm(principal, command.room_id, command.actor_id)
        token = self._digester.derive("room-invitation", command.command_id)

        def operation(uow: LocalMultiplayerUnitOfWork) -> ResultData:
            room = uow.get_room(command.room_id)
            if room.access_mode is not AccessMode.INVITATION:
                raise StateConflictError("Room does not use invitation access.")
            if not 30 <= command.ttl_seconds <= 86400 or not 1 <= command.max_uses <= 50:
                raise DomainValidationError("Invitation TTL or use limit is outside allowed range.")
            now = self._clock()
            invitation = RoomInvitation(
                id=self._id_factory(),
                room_id=room.id,
                token_digest=self._digester.digest(token),
                expires_at=now + timedelta(seconds=command.ttl_seconds),
                max_uses=command.max_uses,
                use_count=0,
                created_at=now,
            )
            uow.add_room_invitation(invitation)
            uow.add_event(
                self._event(
                    event_type="RoomInvitationCreated",
                    aggregate_type="room_invitation",
                    aggregate_id=invitation.id,
                    room_id=room.id,
                    actor_id=command.actor_id,
                    command_id=command.command_id,
                    payload={
                        "expires_at": invitation.expires_at.isoformat(),
                        "max_uses": invitation.max_uses,
                    },
                    visibility="gm",
                )
            )
            return {
                "id": invitation.id,
                "room_id": invitation.room_id,
                "expires_at": invitation.expires_at.isoformat(),
                "max_uses": invitation.max_uses,
                "use_count": invitation.use_count,
            }

        outcome = self._execute("create_room_invitation", command, command.actor_id, operation)
        outcome.data["invitation_token"] = token
        return outcome

    def revoke_room_invitation(
        self, command: RevokeRoomInvitationCommand, principal: LocalDevice
    ) -> CommandOutcome:
        self._ensure_gm(principal, command.room_id, command.actor_id)

        def operation(uow: LocalMultiplayerUnitOfWork) -> ResultData:
            invitation = uow.get_room_invitation(command.invitation_id)
            if invitation.room_id != command.room_id:
                raise PermissionDeniedError("Room invitation does not belong to this room.")
            invitation.revoke(self._clock())
            uow.save_room_invitation(invitation)
            uow.add_event(
                self._event(
                    event_type="RoomInvitationRevoked",
                    aggregate_type="room_invitation",
                    aggregate_id=invitation.id,
                    room_id=invitation.room_id,
                    actor_id=command.actor_id,
                    command_id=command.command_id,
                    payload={"invitation_id": invitation.id},
                    visibility="gm",
                )
            )
            return {"id": invitation.id, "revoked": True}

        return self._execute("revoke_room_invitation", command, command.actor_id, operation)

    def create_session(
        self, command: CreateSessionCommand, principal: LocalDevice
    ) -> CommandOutcome:
        self._ensure_gm(principal, command.room_id, command.actor_id)

        def operation(uow: LocalMultiplayerUnitOfWork) -> ResultData:
            if uow.get_unfinished_session(command.room_id) is not None:
                raise StateConflictError("Room already has an unfinished session.")
            now = self._clock()
            session = GameSession(
                id=self._id_factory(),
                room_id=command.room_id,
                status=SessionStatus.PREPARATION,
                version=1,
                created_at=now,
                updated_at=now,
            )
            uow.add_game_session(session)
            uow.add_event(
                self._session_event(
                    "GameSessionCreated", session, command.actor_id, command.command_id
                )
            )
            return self._session_data(session)

        return self._execute("create_session", command, command.actor_id, operation)

    def transition_session(
        self, command: TransitionSessionCommand, principal: LocalDevice
    ) -> CommandOutcome:
        self._ensure_gm(principal, command.room_id, command.actor_id)

        def operation(uow: LocalMultiplayerUnitOfWork) -> ResultData:
            session = uow.get_game_session(command.session_id)
            if session.room_id != command.room_id:
                raise PermissionDeniedError("Session does not belong to this room.")
            session.transition(
                command.target_status,
                expected_version=command.expected_version,
                now=self._clock(),
            )
            uow.save_game_session(session)
            event_names = {
                SessionStatus.LOBBY: "LobbyOpened",
                SessionStatus.ACTIVE: "GameSessionStarted"
                if session.started_at == session.updated_at
                else "GameSessionResumed",
                SessionStatus.PAUSED: "GameSessionPaused",
                SessionStatus.COMPLETED: "GameSessionCompleted",
            }
            uow.add_event(
                self._session_event(
                    event_names[command.target_status],
                    session,
                    command.actor_id,
                    command.command_id,
                )
            )
            return self._session_data(session)

        return self._execute("transition_session", command, command.actor_id, operation)

    def revoke_device(self, command: RevokeDeviceCommand, principal: LocalDevice) -> CommandOutcome:
        self._ensure_gm(principal, command.room_id, command.actor_id)

        def operation(uow: LocalMultiplayerUnitOfWork) -> ResultData:
            device = uow.get_device(command.target_device_id)
            if device.room_id != command.room_id:
                raise PermissionDeniedError("Device does not belong to this room.")
            if device.id == principal.id:
                raise StateConflictError("The active GM device cannot revoke itself.")
            device.revoke(self._clock())
            uow.save_local_device(device)
            uow.add_event(
                self._event(
                    event_type="DeviceRevoked",
                    aggregate_type="local_device",
                    aggregate_id=device.id,
                    room_id=device.room_id,
                    actor_id=command.actor_id,
                    command_id=command.command_id,
                    payload={"device_id": device.id},
                    visibility="gm",
                )
            )
            return self._device_data(device)

        return self._execute("revoke_device", command, command.actor_id, operation)

    def refresh_device_credential(
        self, command: RefreshDeviceCredentialCommand, principal: LocalDevice
    ) -> CommandOutcome:
        if command.device_id != principal.id:
            raise PermissionDeniedError("Command device does not match the authenticated device.")
        credential = self._digester.derive(
            "refreshed-device-credential", f"{command.command_id}:{principal.id}"
        )

        def operation(uow: LocalMultiplayerUnitOfWork) -> ResultData:
            device = uow.get_device(principal.id)
            now = self._clock()
            device.rotate_credential(
                self._digester.digest(credential),
                now=now,
                expires_at=now + timedelta(days=30),
            )
            uow.save_local_device(device)
            uow.add_event(
                self._event(
                    event_type="DeviceCredentialRefreshed",
                    aggregate_type="local_device",
                    aggregate_id=device.id,
                    room_id=device.room_id,
                    actor_id=device.player_id or device.id,
                    command_id=command.command_id,
                    payload={"device_id": device.id},
                    visibility="gm",
                )
            )
            return {"device": self._device_data(device)}

        outcome = self._execute("refresh_device_credential", command, principal.id, operation)
        outcome.data["device_credential"] = credential
        return outcome

    def snapshot(self, principal: LocalDevice) -> ResultData:
        with self._uow_factory() as uow:
            room = uow.get_room(principal.room_id)
            session = uow.get_unfinished_session(room.id)
            minimum, cursor = uow.event_cursor_bounds(room.id)
            del minimum
            players = uow.list_local_players(room.id)
            if principal.role is DeviceRole.GM:
                devices = uow.list_local_devices(room.id)
                return {
                    "cursor": cursor,
                    "current_device_id": principal.id,
                    "device": self._device_data(principal),
                    "room": self._room_data(room),
                    "session": self._session_data(session) if session else None,
                    "players": [self._player_data(player) for player in players],
                    "devices": [self._device_data(device) for device in devices],
                }
            if principal.player_id is None:
                return {
                    "cursor": cursor,
                    "current_device_id": principal.id,
                    "device": self._device_data(principal),
                    "room": self._public_room_data(room),
                    "session": self._session_data(session) if session else None,
                    "player": None,
                    "characters": [],
                }
            player = uow.get_local_player(principal.player_id)
            characters = uow.list_characters_for_player(player.id)
            own_devices = [
                device
                for device in uow.list_local_devices(room.id)
                if device.player_id == player.id
            ]
            return {
                "cursor": cursor,
                "current_device_id": principal.id,
                "device": self._device_data(principal),
                "room": self._public_room_data(room),
                "session": self._session_data(session) if session else None,
                "player": self._player_data(player),
                "characters": [
                    {
                        **self._character_summary(character),
                        "selected": character.id == player.selected_character_id,
                    }
                    for character in characters
                ],
                "devices": [self._device_data(device) for device in own_devices],
            }

    def replay_events(
        self, principal: LocalDevice, cursor: int, limit: int = 500
    ) -> list[DomainEvent]:
        with self._uow_factory() as uow:
            events = uow.list_events_after(principal.room_id, cursor, limit)
            if principal.role is DeviceRole.GM:
                return events
            return [event for event in events if event.visibility == "room"]

    def cursor_bounds(self, room_id: str) -> tuple[int | None, int]:
        with self._uow_factory() as uow:
            return uow.event_cursor_bounds(room_id)

    def room_status(self, principal: LocalDevice) -> ResultData:
        return self.snapshot(principal)

    def _execute(
        self,
        command_type: str,
        command: CommandT,
        actor_id: str,
        operation: Callable[[LocalMultiplayerUnitOfWork], ResultData],
    ) -> CommandOutcome:
        command_data = asdict(cast(Any, command))
        command_id = str(command_data["command_id"])
        device_id = str(command_data["device_id"])
        client_value = command_data.get("client_time")
        client_time = str(client_value) if client_value is not None else None
        fingerprint = command_fingerprint(command)
        with self._uow_factory() as uow:
            existing = uow.get_processed_command(command_id)
            if existing is not None:
                if (
                    existing.command_type != command_type
                    or existing.actor_id != actor_id
                    or existing.payload_hash != fingerprint
                ):
                    raise IdempotencyConflictError(
                        "Command ID was already used with different command content.",
                        details={"command_id": command_id},
                    )
                return CommandOutcome(dict(existing.result), replayed=True)
            result = operation(uow)
            uow.add_processed_command(
                ProcessedCommand(
                    command_id=command_id,
                    command_type=command_type,
                    payload_hash=fingerprint,
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
        logger.info("local_command_processed", extra={"command_type": command_type})
        return CommandOutcome(result, replayed=False, events=events)

    def _authorize_room_join(
        self,
        uow: LocalMultiplayerUnitOfWork,
        room: Room,
        password: str | None,
        invitation_token: str | None,
    ) -> None:
        if room.access_mode is AccessMode.OPEN:
            return
        if room.access_mode is AccessMode.PASSWORD:
            if (
                password is None
                or room.password_hash is None
                or not self._password_hasher.verify(room.password_hash, password)
            ):
                raise PermissionDeniedError("Room password is invalid.")
            return
        if invitation_token is None:
            raise PermissionDeniedError("A room invitation is required.")
        try:
            invitation = uow.get_room_invitation_by_digest(self._digester.digest(invitation_token))
        except EntityNotFoundError as error:
            raise PermissionDeniedError("Room invitation is invalid.") from error
        if invitation.room_id != room.id:
            raise PermissionDeniedError("Room invitation is invalid.")
        invitation.consume(self._clock())
        uow.save_room_invitation(invitation)

    @staticmethod
    def _ensure_gm(principal: LocalDevice, room_id: str, actor_id: str) -> None:
        if (
            principal.role is not DeviceRole.GM
            or principal.room_id != room_id
            or actor_id != principal.id
        ):
            raise PermissionDeniedError("A GM device for this room is required.")

    @staticmethod
    def _ensure_player_device(principal: LocalDevice) -> None:
        if principal.role is not DeviceRole.PLAYER:
            raise PermissionDeniedError("A player device is required.")

    @staticmethod
    def _ensure_player(principal: LocalDevice, player_id: str) -> None:
        if principal.role is not DeviceRole.PLAYER or principal.player_id != player_id:
            raise PermissionDeniedError("The device does not control this local profile.")

    def _room_code(self, material: str) -> str:
        alphabet = "ABCDEFGHJKLMNPQRSTUVWXYZ23456789"
        digest = self._digester.derive("room-code", material)
        return "".join(alphabet[ord(char) % len(alphabet)] for char in digest[:6])

    def _short_code(self, material: str) -> str:
        alphabet = "ABCDEFGHJKLMNPQRSTUVWXYZ23456789"
        digest = self._digester.derive("pairing-code", material)
        return "".join(alphabet[ord(char) % len(alphabet)] for char in digest[:8])

    def _event(
        self,
        *,
        event_type: str,
        aggregate_type: str,
        aggregate_id: str,
        room_id: str,
        actor_id: str,
        command_id: str,
        payload: ResultData,
        visibility: str = "room",
        session_id: str | None = None,
    ) -> DomainEvent:
        return DomainEvent(
            id=self._id_factory(),
            event_type=event_type,
            aggregate_type=aggregate_type,
            aggregate_id=aggregate_id,
            room_id=room_id,
            actor_id=actor_id,
            source_id=None,
            target_ids=(aggregate_id,),
            payload=payload,
            visibility=visibility,
            schema_version=1,
            command_id=command_id,
            occurred_at=self._clock(),
            session_id=session_id,
        )

    def _session_event(
        self, event_type: str, session: GameSession, actor_id: str, command_id: str
    ) -> DomainEvent:
        return self._event(
            event_type=event_type,
            aggregate_type="game_session",
            aggregate_id=session.id,
            room_id=session.room_id,
            actor_id=actor_id,
            command_id=command_id,
            payload={"status": session.status.value, "version": session.version},
            session_id=session.id,
        )

    @staticmethod
    def _room_data(room: Room) -> ResultData:
        return {
            "id": room.id,
            "name": room.name,
            "gm_id": room.gm_id,
            "code": room.code,
            "access_mode": room.access_mode.value,
            "ruleset_version": room.ruleset_version,
            "version": room.version,
            "created_at": room.created_at.isoformat(),
        }

    @staticmethod
    def _public_room_data(room: Room) -> ResultData:
        return {
            "id": room.id,
            "name": room.name,
            "code": room.code,
            "access_mode": room.access_mode.value,
        }

    @staticmethod
    def _player_data(player: LocalPlayer) -> ResultData:
        return {
            "id": player.id,
            "room_id": player.room_id,
            "display_name": player.display_name,
            "selected_character_id": player.selected_character_id,
            "version": player.version,
            "created_at": player.created_at.isoformat(),
            "updated_at": (player.updated_at or player.created_at).isoformat(),
        }

    @staticmethod
    def _device_data(device: LocalDevice) -> ResultData:
        return {
            "id": device.id,
            "room_id": device.room_id,
            "player_id": device.player_id,
            "label": device.label,
            "role": device.role.value,
            "status": device.status.value,
            "created_at": device.created_at.isoformat(),
            "last_seen_at": device.last_seen_at.isoformat(),
            "expires_at": device.expires_at.isoformat(),
            "revoked_at": device.revoked_at.isoformat() if device.revoked_at else None,
        }

    @staticmethod
    def _session_data(session: GameSession) -> ResultData:
        return {
            "id": session.id,
            "room_id": session.room_id,
            "status": session.status.value,
            "version": session.version,
            "created_at": session.created_at.isoformat(),
            "updated_at": session.updated_at.isoformat(),
            "started_at": session.started_at.isoformat() if session.started_at else None,
            "paused_at": session.paused_at.isoformat() if session.paused_at else None,
            "completed_at": session.completed_at.isoformat() if session.completed_at else None,
        }

    @staticmethod
    def _character_summary(character: Any) -> ResultData:
        return {
            "id": character.id,
            "name": character.name,
            "version": character.version,
            "selected": False,
        }
