from __future__ import annotations

import logging
from collections.abc import Callable
from dataclasses import asdict, replace
from datetime import UTC, datetime, timedelta
from random import SystemRandom
from typing import Any, TypeVar, cast
from uuid import uuid4

from tabletop_companion.application.fingerprints import command_fingerprint
from tabletop_companion.application.local_commands import (
    BootstrapRoomCommand,
    ClearCharacterSelectionCommand,
    CreateNpcNoteCommand,
    CreatePairingCommand,
    CreatePlayerNoteNodeCommand,
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
    UpdateOwnCharacterHealthCommand,
    UpdatePlayerNoteNodeCommand,
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
from tabletop_companion.domain.character_creation import (
    CLASS_DEFINITIONS,
    STAT_DESCRIPTIONS,
    STAT_NAMES,
)
from tabletop_companion.domain.combat import (
    DiceExpression,
    DiceRoll,
    RollMode,
    RollVisibility,
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
from tabletop_companion.domain.models import (
    AccessMode,
    Account,
    GmNotes,
    InventoryItem,
    ItemDefinition,
    LocalPlayer,
    NpcNote,
    PlayerNoteNode,
    Room,
)
from tabletop_companion.domain.rules import SimpleRuleset
from tabletop_companion.domain.sessions import GameSession, SessionStatus
from tabletop_companion.domain.species import SPECIES, validate_species_choices

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
        randint: Callable[[int, int], int] | None = None,
    ) -> None:
        self._uow_factory = uow_factory
        self._ruleset = ruleset
        self._digester = digester
        self._password_hasher = password_hasher
        self._id_factory = id_factory or (lambda: str(uuid4()))
        self._clock = clock or (lambda: datetime.now(UTC))
        self._randint = randint or SystemRandom().randint
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

        def operation(uow: LocalMultiplayerUnitOfWork) -> ResultData:
            device = uow.get_device(principal.id)
            device.authenticate(self._clock())
            if device.player_id is not None:
                raise StateConflictError("Device is already attached to a local profile.")
            room = uow.get_room(device.room_id)
            self._authorize_room_join(uow, room, command.password, command.invitation_token)
            now = self._clock()
            account_id = self._id_factory()
            account = Account(
                id=account_id,
                display_name=command.display_name.strip(),
                version=1,
                created_at=now,
                updated_at=now,
            )
            player = LocalPlayer(
                id=self._id_factory(),
                room_id=room.id,
                display_name=command.display_name.strip(),
                version=1,
                created_at=now,
                updated_at=now,
                account_id=account_id,
            )
            if not player.display_name:
                raise DomainValidationError("Player display name must not be blank.")
            device.attach_player(player.id, now)
            device.attach_account(account_id)
            uow.add_account(account)
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

        return self._execute("create_profile", command, principal.id, operation)

    def select_character(
        self, command: SelectCharacterCommand, principal: LocalDevice
    ) -> CommandOutcome:
        self._ensure_player(principal, command.player_id)

        def operation(uow: LocalMultiplayerUnitOfWork) -> ResultData:
            player = uow.get_local_player(command.player_id)
            character = uow.get_character(command.character_id)
            if character.account_id != (player.account_id or player.id):
                raise PermissionDeniedError("The player does not control this character.")
            if character.archived_at is not None:
                raise StateConflictError(
                    "Archived characters cannot be selected.", code="character_archived"
                )
            if not uow.is_character_assigned(character.id, principal.room_id):
                raise PermissionDeniedError("The character is not assigned to this room.")
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

    def clear_character_selection(
        self, command: ClearCharacterSelectionCommand, principal: LocalDevice
    ) -> CommandOutcome:
        self._ensure_player(principal, command.player_id)

        def operation(uow: LocalMultiplayerUnitOfWork) -> ResultData:
            player = uow.get_local_player(command.player_id)
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
                selected_character_id=None,
                version=player.version + 1,
                updated_at=self._clock(),
            )
            uow.save_local_player(updated)
            uow.add_event(
                self._event(
                    event_type="CharacterSelectionCleared",
                    aggregate_type="local_player",
                    aggregate_id=player.id,
                    room_id=player.room_id,
                    actor_id=player.id,
                    command_id=command.command_id,
                    payload={"character_id": player.selected_character_id},
                )
            )
            return self._player_data(updated)

        return self._execute("clear_character_selection", command, command.player_id, operation)

    def update_own_character_health(
        self, command: UpdateOwnCharacterHealthCommand, principal: LocalDevice
    ) -> CommandOutcome:
        self._ensure_player(principal, command.player_id)

        def operation(uow: LocalMultiplayerUnitOfWork) -> ResultData:
            player = uow.get_local_player(command.player_id)
            character = uow.get_character(command.character_id)
            if character.account_id != (player.account_id or player.id):
                raise PermissionDeniedError("The player does not control this character.")
            if not uow.is_character_assigned(character.id, principal.room_id):
                raise PermissionDeniedError("Character does not belong to this room.")
            character.edit_health(
                current_hp=command.current_hp,
                temporary_hp=command.temporary_hp,
                expected_version=command.expected_version,
            )
            uow.save_character(character)
            uow.add_event(
                self._event(
                    event_type="CharacterHealthEdited",
                    aggregate_type="character",
                    aggregate_id=character.id,
                    room_id=principal.room_id,
                    actor_id=player.id,
                    command_id=command.command_id,
                    payload={
                        "character_id": character.id,
                        "current_hp": character.current_hp,
                        "temporary_hp": character.temporary_hp,
                        "version": character.version,
                    },
                    visibility="room",
                )
            )
            return self._character_data(character)

        return self._execute("update_own_character_health", command, command.player_id, operation)

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

    def kick_player(self, command: KickPlayerCommand, principal: LocalDevice) -> CommandOutcome:
        self._ensure_gm(principal, command.room_id, command.actor_id)

        def operation(uow: LocalMultiplayerUnitOfWork) -> ResultData:
            player = uow.get_local_player(command.player_id)
            if player.room_id != command.room_id or player.removed_at is not None:
                raise PermissionDeniedError("Player does not belong to this lobby.")
            now = self._clock()
            removed = replace(
                player,
                selected_character_id=None,
                removed_at=now,
                updated_at=now,
                version=player.version + 1,
            )
            uow.save_local_player(removed)
            revoked_device_ids: list[str] = []
            for device in uow.list_local_devices(command.room_id):
                if device.player_id == player.id and device.status is DeviceStatus.ACTIVE:
                    device.revoke(now)
                    uow.save_local_device(device)
                    revoked_device_ids.append(device.id)
            uow.add_event(
                self._event(
                    event_type="PlayerKicked",
                    aggregate_type="local_player",
                    aggregate_id=player.id,
                    room_id=player.room_id,
                    actor_id=command.actor_id,
                    command_id=command.command_id,
                    payload={"player_id": player.id},
                    visibility="room",
                )
            )
            return {"player_id": player.id, "device_ids": revoked_device_ids}

        return self._execute("kick_player", command, command.actor_id, operation)

    def character_catalog(self, principal: LocalDevice) -> ResultData:
        del principal
        return {
            "races": [
                {
                    "id": race.id,
                    "name": race.name,
                    "description": race.description,
                    "hp_bonus": race.hp_bonus,
                }
                for race in self._ruleset.races
            ],
            "classes": [
                {
                    "id": character_class.id,
                    "name": character_class.name,
                    "description": character_class.description,
                    "base_hp": character_class.base_hp,
                    "base_armor_class": character_class.base_armor_class,
                }
                for character_class in self._ruleset.classes
            ],
            "abilities": [self._ability_data(card) for card in self._ruleset.cards],
            "class_details": [asdict(item) for item in CLASS_DEFINITIONS],
            "species": [
                {
                    **asdict(item),
                    "features": [asdict(feature) for feature in item.features],
                }
                for item in SPECIES
            ],
            "stats": [
                {"id": stat_id, "name": STAT_NAMES[stat_id], "description": description}
                for stat_id, description in STAT_DESCRIPTIONS.items()
            ],
        }

    def roll_room_dice(
        self, command: RollRoomDiceCommand, principal: LocalDevice
    ) -> CommandOutcome:
        if principal.room_id != command.room_id or principal.id != command.actor_id:
            raise PermissionDeniedError("Device does not belong to this room.")
        if principal.role is DeviceRole.PLAYER and command.visibility is RollVisibility.SECRET:
            raise PermissionDeniedError("Only the GM can make secret rolls.")

        def operation(uow: LocalMultiplayerUnitOfWork) -> ResultData:
            expression = DiceExpression.parse(command.expression)
            character_id: str | None = None
            if principal.role is DeviceRole.PLAYER:
                if principal.player_id is None:
                    raise PermissionDeniedError("Player profile is required.")
                player = uow.get_local_player(principal.player_id)
                character_id = player.selected_character_id
            if command.visibility is RollVisibility.PRIVATE and command.recipient_player_id is None:
                raise DomainValidationError(
                    "A private roll requires a recipient.", code="private_roll_recipient_required"
                )
            if command.recipient_player_id is not None:
                recipient = uow.get_local_player(command.recipient_player_id)
                if recipient.room_id != command.room_id:
                    raise PermissionDeniedError("Roll recipient does not belong to this room.")
            attempts: tuple[tuple[int, ...], ...]
            totals: tuple[int, ...]
            if command.mode is RollMode.PHYSICAL:
                if command.physical_result is None:
                    raise DomainValidationError(
                        "A physical roll requires a manual result.", code="physical_result_required"
                    )
                attempts = ((command.physical_result,),)
                totals = (command.physical_result,)
                selected = 0
            else:
                attempts, totals, selected = expression.roll_selected(
                    command.selection, self._randint
                )
            roll = DiceRoll(
                id=self._id_factory(),
                combat_id=None,
                room_id=command.room_id,
                actor_id=principal.id,
                character_id=character_id,
                expression=expression.normalized(),
                mode=command.mode,
                visibility=command.visibility,
                recipient_player_id=command.recipient_player_id,
                values=attempts[selected],
                original_result=totals[selected],
                result=totals[selected],
                reason=None,
                action_event_id=None,
                created_at=self._clock(),
                selection=command.selection,
                attempts=attempts,
                attempt_totals=totals,
                selected_attempt=selected,
            )
            uow.add_dice_roll(roll)
            session = uow.get_unfinished_session(command.room_id)
            uow.add_event(
                self._event(
                    event_type="DiceRolled",
                    aggregate_type="dice_roll",
                    aggregate_id=roll.id,
                    room_id=roll.room_id,
                    actor_id=principal.id,
                    command_id=command.command_id,
                    payload={"roll": self._roll_data(roll)},
                    visibility=(
                        "room"
                        if command.visibility is RollVisibility.PUBLIC
                        else "gm"
                        if command.visibility is RollVisibility.SECRET
                        else (
                            f"players:{principal.player_id},{command.recipient_player_id}"
                            if command.visibility is RollVisibility.PRIVATE
                            else f"player:{principal.player_id}"
                        )
                    ),
                    session_id=session.id if session else None,
                )
            )
            return {"roll": self._roll_data(roll)}

        return self._execute("roll_room_dice", command, command.actor_id, operation)

    def update_character(
        self, command: UpdateCharacterCommand, principal: LocalDevice
    ) -> CommandOutcome:
        self._ensure_gm(principal, command.room_id, command.actor_id)

        def operation(uow: LocalMultiplayerUnitOfWork) -> ResultData:
            character = uow.get_character(command.character_id)
            if not uow.is_character_assigned(character.id, command.room_id):
                raise PermissionDeniedError("Character does not belong to this room.")
            self._ruleset.validate_character_choices(
                race_id=command.race_id,
                class_id=command.class_id,
                stats=command.stats,
                ability_ids=command.ability_ids,
            )
            if command.species_choices is not None:
                validate_species_choices(command.race_id, command.species_choices)
            character.edit(
                name=command.name,
                race_id=command.race_id,
                class_id=command.class_id,
                stats=command.stats,
                ability_ids=list(command.ability_ids),
                max_hp=command.max_hp,
                current_hp=command.current_hp,
                armor_class=command.armor_class,
                expected_version=command.expected_version,
                temporary_hp=command.temporary_hp,
                level=command.level,
                experience=command.experience,
                initiative=command.initiative,
                proficiency_bonus=command.proficiency_bonus,
                size=command.size,
                speed=command.speed,
                darkvision=command.darkvision,
                species_choices=command.species_choices,
                persistent_conditions=command.persistent_conditions,
            )
            uow.save_character(character)
            uow.add_event(
                self._event(
                    event_type="CharacterEditedByGm",
                    aggregate_type="character",
                    aggregate_id=character.id,
                    room_id=command.room_id,
                    actor_id=command.actor_id,
                    command_id=command.command_id,
                    payload={"character_id": character.id, "version": character.version},
                    visibility="room",
                )
            )
            return self._character_data(character)

        return self._execute("update_character", command, command.actor_id, operation)

    def gm_add_inventory_item(
        self, command: GmAddInventoryItemCommand, principal: LocalDevice
    ) -> CommandOutcome:
        self._ensure_gm(principal, command.room_id, command.actor_id)

        def operation(uow: LocalMultiplayerUnitOfWork) -> ResultData:
            character = uow.get_character(command.character_id)
            if not uow.is_character_assigned(character.id, command.room_id):
                raise PermissionDeniedError("Character does not belong to this room.")
            name = command.name.strip()
            if not name:
                raise DomainValidationError("Item name cannot be blank.")
            definition = ItemDefinition(self._id_factory(), name, False, False)
            item = InventoryItem(
                id=self._id_factory(),
                definition_id=definition.id,
                name=name,
                consumable=False,
                locked=False,
                quantity=1,
                equipped=False,
                charges=None,
                created_at=self._clock(),
            )
            character.add_item(item, expected_version=command.expected_version)
            uow.add_item_definition(definition)
            uow.save_character(character)
            uow.add_event(
                self._event(
                    event_type="ItemGrantedByGm",
                    aggregate_type="character",
                    aggregate_id=character.id,
                    room_id=command.room_id,
                    actor_id=command.actor_id,
                    command_id=command.command_id,
                    payload={"item_id": item.id, "name": item.name},
                    visibility="room",
                )
            )
            return self._character_data(character)

        return self._execute("gm_add_inventory_item", command, command.actor_id, operation)

    def gm_discard_inventory_item(
        self, command: GmDiscardInventoryItemCommand, principal: LocalDevice
    ) -> CommandOutcome:
        self._ensure_gm(principal, command.room_id, command.actor_id)

        def operation(uow: LocalMultiplayerUnitOfWork) -> ResultData:
            character = uow.get_character(command.character_id)
            if not uow.is_character_assigned(character.id, command.room_id):
                raise PermissionDeniedError("Character does not belong to this room.")
            item = next(
                (candidate for candidate in character.inventory if candidate.id == command.item_id),
                None,
            )
            if item is None:
                raise EntityNotFoundError("Inventory item was not found.")
            character.ensure_version(command.expected_version)
            character.inventory.remove(item)
            character.version += 1
            uow.save_character(character)
            uow.add_event(
                self._event(
                    event_type="ItemRemovedByGm",
                    aggregate_type="character",
                    aggregate_id=character.id,
                    room_id=command.room_id,
                    actor_id=command.actor_id,
                    command_id=command.command_id,
                    payload={"item_id": item.id, "name": item.name},
                    visibility="room",
                )
            )
            return self._character_data(character)

        return self._execute("gm_discard_inventory_item", command, command.actor_id, operation)

    def get_gm_notes(self, principal: LocalDevice) -> ResultData:
        self._ensure_gm(principal, principal.room_id, principal.id)
        with self._uow_factory() as uow:
            notes = uow.get_gm_notes(principal.room_id)
            npcs = uow.list_npc_notes(principal.room_id)
            return {
                "campaign": notes.campaign if notes else "",
                "other": notes.other if notes else "",
                "version": notes.version if notes else 0,
                "npcs": [self._npc_data(npc) for npc in npcs],
            }

    def update_gm_notes(
        self, command: UpdateGmNotesCommand, principal: LocalDevice
    ) -> CommandOutcome:
        self._ensure_gm(principal, command.room_id, command.actor_id)

        def operation(uow: LocalMultiplayerUnitOfWork) -> ResultData:
            existing = uow.get_gm_notes(command.room_id)
            now = self._clock()
            if existing is None:
                if command.expected_version != 0:
                    raise StateConflictError("GM notes version is stale.")
                notes = GmNotes(command.room_id, command.campaign, command.other, 1, now)
                uow.add_gm_notes(notes)
            else:
                if existing.version != command.expected_version:
                    raise StateConflictError("GM notes version is stale.")
                existing.campaign = command.campaign
                existing.other = command.other
                existing.version += 1
                existing.updated_at = now
                notes = existing
                uow.save_gm_notes(notes)
            uow.add_event(
                self._event(
                    event_type="GmNotesUpdated",
                    aggregate_type="gm_notes",
                    aggregate_id=command.room_id,
                    room_id=command.room_id,
                    actor_id=command.actor_id,
                    command_id=command.command_id,
                    payload={"version": notes.version},
                    visibility="gm",
                )
            )
            return {"campaign": notes.campaign, "other": notes.other, "version": notes.version}

        return self._execute("update_gm_notes", command, command.actor_id, operation)

    def create_npc_note(
        self, command: CreateNpcNoteCommand, principal: LocalDevice
    ) -> CommandOutcome:
        self._ensure_gm(principal, command.room_id, command.actor_id)

        def operation(uow: LocalMultiplayerUnitOfWork) -> ResultData:
            name = command.name.strip()
            if not name:
                raise DomainValidationError("NPC name must not be blank.")
            now = self._clock()
            npc = NpcNote(self._id_factory(), command.room_id, name, "", 1, now, now)
            uow.add_npc_note(npc)
            uow.add_event(
                self._event(
                    event_type="NpcNoteCreated",
                    aggregate_type="npc_note",
                    aggregate_id=npc.id,
                    room_id=npc.room_id,
                    actor_id=command.actor_id,
                    command_id=command.command_id,
                    payload={"npc_id": npc.id, "name": npc.name},
                    visibility="gm",
                )
            )
            return self._npc_data(npc)

        return self._execute("create_npc_note", command, command.actor_id, operation)

    def update_npc_note(
        self, command: UpdateNpcNoteCommand, principal: LocalDevice
    ) -> CommandOutcome:
        self._ensure_gm(principal, command.room_id, command.actor_id)

        def operation(uow: LocalMultiplayerUnitOfWork) -> ResultData:
            npc = uow.get_npc_note(command.npc_id)
            if npc.room_id != command.room_id:
                raise PermissionDeniedError("NPC note does not belong to this room.")
            if npc.version != command.expected_version:
                raise StateConflictError("NPC note version is stale.")
            name = command.name.strip()
            if not name:
                raise DomainValidationError("NPC name must not be blank.")
            npc.name = name
            npc.details = command.details
            npc.version += 1
            npc.updated_at = self._clock()
            uow.save_npc_note(npc)
            uow.add_event(
                self._event(
                    event_type="NpcNoteUpdated",
                    aggregate_type="npc_note",
                    aggregate_id=npc.id,
                    room_id=npc.room_id,
                    actor_id=command.actor_id,
                    command_id=command.command_id,
                    payload={"npc_id": npc.id, "version": npc.version},
                    visibility="gm",
                )
            )
            return self._npc_data(npc)

        return self._execute("update_npc_note", command, command.actor_id, operation)

    def delete_npc_note(
        self, command: DeleteNpcNoteCommand, principal: LocalDevice
    ) -> CommandOutcome:
        self._ensure_gm(principal, command.room_id, command.actor_id)

        def operation(uow: LocalMultiplayerUnitOfWork) -> ResultData:
            npc = uow.get_npc_note(command.npc_id)
            if npc.room_id != command.room_id:
                raise PermissionDeniedError("NPC note does not belong to this room.")
            uow.delete_npc_note(npc.id)
            uow.add_event(
                self._event(
                    event_type="NpcNoteDeleted",
                    aggregate_type="npc_note",
                    aggregate_id=npc.id,
                    room_id=npc.room_id,
                    actor_id=command.actor_id,
                    command_id=command.command_id,
                    payload={"npc_id": npc.id},
                    visibility="gm",
                )
            )
            return {"npc_id": npc.id, "deleted": True}

        return self._execute("delete_npc_note", command, command.actor_id, operation)

    def get_player_notes(self, principal: LocalDevice) -> ResultData:
        if principal.player_id is None:
            raise PermissionDeniedError("Player profile is required.")
        with self._uow_factory() as uow:
            return {
                "nodes": [
                    self._player_note_data(node)
                    for node in uow.list_player_note_nodes(principal.player_id)
                ]
            }

    def create_player_note_node(
        self, command: CreatePlayerNoteNodeCommand, principal: LocalDevice
    ) -> CommandOutcome:
        self._ensure_player(principal, command.player_id)

        def operation(uow: LocalMultiplayerUnitOfWork) -> ResultData:
            kind = command.kind.strip().lower()
            name = command.name.strip()
            if kind not in {"folder", "note"} or not name or len(name) > 120:
                raise DomainValidationError("Player note node is invalid.")
            parent = None
            if command.parent_id is not None:
                parent = uow.get_player_note_node(command.parent_id)
                if parent.player_id != command.player_id or parent.kind != "folder":
                    raise PermissionDeniedError("Parent folder is unavailable.")
            depth = (
                (parent.depth + 1)
                if kind == "folder" and parent
                else (1 if kind == "folder" else 0)
            )
            if kind == "note" and parent:
                depth = parent.depth
            if kind == "folder" and depth > 3:
                raise DomainValidationError(
                    "Folder nesting is limited to three levels.", code="folder_depth_limit"
                )
            existing = uow.list_player_note_nodes(command.player_id)
            if (
                kind == "note"
                and sum(
                    node.kind == "note" and node.parent_id == command.parent_id for node in existing
                )
                >= 50
            ):
                raise DomainValidationError(
                    "A folder can contain at most 50 notes.", code="folder_note_limit"
                )
            now = self._clock()
            node = PlayerNoteNode(
                id=self._id_factory(),
                room_id=principal.room_id,
                player_id=command.player_id,
                parent_id=command.parent_id,
                kind=kind,
                name=name,
                body="",
                depth=depth,
                version=1,
                created_at=now,
                updated_at=now,
            )
            uow.add_player_note_node(node)
            uow.add_event(
                self._event(
                    event_type="PlayerNoteNodeCreated",
                    aggregate_type="player_note_node",
                    aggregate_id=node.id,
                    room_id=principal.room_id,
                    actor_id=command.player_id,
                    command_id=command.command_id,
                    payload={"node_id": node.id, "kind": node.kind},
                    visibility=f"player:{command.player_id}",
                )
            )
            return self._player_note_data(node)

        return self._execute("create_player_note_node", command, command.player_id, operation)

    def update_player_note_node(
        self, command: UpdatePlayerNoteNodeCommand, principal: LocalDevice
    ) -> CommandOutcome:
        self._ensure_player(principal, command.player_id)

        def operation(uow: LocalMultiplayerUnitOfWork) -> ResultData:
            node = uow.get_player_note_node(command.node_id)
            if node.player_id != command.player_id:
                raise PermissionDeniedError("Player note is unavailable.")
            node.edit(
                name=command.name,
                body=command.body,
                expected_version=command.expected_version,
                now=self._clock(),
            )
            uow.save_player_note_node(node)
            uow.add_event(
                self._event(
                    event_type="PlayerNoteNodeUpdated",
                    aggregate_type="player_note_node",
                    aggregate_id=node.id,
                    room_id=principal.room_id,
                    actor_id=command.player_id,
                    command_id=command.command_id,
                    payload={"node_id": node.id, "version": node.version},
                    visibility=f"player:{command.player_id}",
                )
            )
            return self._player_note_data(node)

        return self._execute("update_player_note_node", command, command.player_id, operation)

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
            all_devices = uow.list_local_devices(room.id)
            player_names = {player.id: player.display_name for player in players}
            actor_names = {
                device.id: (
                    "GM"
                    if device.role is DeviceRole.GM
                    else player_names.get(device.player_id or "", "Player")
                )
                for device in all_devices
            }
            visible_rolls = [
                {**self._roll_data(roll), "actor_name": actor_names.get(roll.actor_id, "Player")}
                for roll in uow.list_room_dice_rolls(room.id)
                if principal.role is DeviceRole.GM
                or roll.visibility is RollVisibility.PUBLIC
                or (roll.visibility is RollVisibility.DELAYED and roll.actor_id == principal.id)
                or (
                    roll.visibility is RollVisibility.PRIVATE
                    and (
                        roll.recipient_player_id == principal.player_id
                        or roll.actor_id == principal.id
                    )
                )
            ]
            if principal.role is DeviceRole.GM:
                characters = uow.list_characters_for_room(room.id)
                return {
                    "cursor": cursor,
                    "current_device_id": principal.id,
                    "device": self._device_data(principal),
                    "room": self._room_data(room),
                    "session": self._session_data(session) if session else None,
                    "players": [self._player_data(player) for player in players],
                    "devices": [self._device_data(device) for device in all_devices],
                    "characters": [
                        {
                            **self._character_summary(character),
                            "owner_id": character.owner_id,
                            "owner_name": player_names.get(character.owner_id, "Unknown player"),
                            "max_hp": character.max_hp,
                            "current_hp": character.current_hp,
                            "armor_class": character.armor_class,
                            "race_id": character.race_id,
                            "class_id": character.class_id,
                        }
                        for character in characters
                    ],
                    "dice_rolls": visible_rolls,
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
                    "dice_rolls": visible_rolls,
                }
            player = uow.get_local_player(principal.player_id)
            characters = uow.list_characters_for_player(player.id)
            archived = uow.list_archived_characters_for_player(player.id)
            own_devices = [
                device
                for device in all_devices
                if device.account_id == player.account_id or device.player_id == player.id
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
                "archived_characters": [self._character_summary(item) for item in archived],
                "devices": [self._device_data(device) for device in own_devices],
                "dice_rolls": visible_rolls,
            }

    def replay_events(
        self, principal: LocalDevice, cursor: int, limit: int = 500
    ) -> list[DomainEvent]:
        with self._uow_factory() as uow:
            events = uow.list_events_after(principal.room_id, cursor, limit)
            if principal.role is DeviceRole.GM:
                return events
            return [
                event
                for event in events
                if event.visibility in {"room", f"player:{principal.player_id}"}
                or (
                    event.visibility.startswith("players:")
                    and (principal.player_id or "")
                    in event.visibility.removeprefix("players:").split(",")
                )
            ]

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
            "account_id": player.account_id,
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
    def _roll_data(roll: DiceRoll) -> ResultData:
        return {
            "id": roll.id,
            "combat_id": roll.combat_id,
            "actor_id": roll.actor_id,
            "character_id": roll.character_id,
            "expression": roll.expression,
            "mode": roll.mode.value,
            "visibility": roll.visibility.value,
            "recipient_player_id": roll.recipient_player_id,
            "values": list(roll.values),
            "original_result": roll.original_result,
            "result": roll.result,
            "reason": roll.reason,
            "action_event_id": roll.action_event_id,
            "created_at": roll.created_at.isoformat(),
            "revealed_at": roll.revealed_at.isoformat() if roll.revealed_at else None,
            "selection": roll.selection.value,
            "attempts": [list(attempt) for attempt in roll.attempts],
            "attempt_totals": list(roll.attempt_totals),
            "selected_attempt": roll.selected_attempt,
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
            "race_id": character.race_id,
            "class_id": character.class_id,
            "max_hp": character.max_hp,
            "current_hp": character.current_hp,
            "armor_class": character.armor_class,
            "account_id": character.account_id,
            "archived_at": character.archived_at.isoformat() if character.archived_at else None,
            "level": character.level,
            "experience": character.experience,
            "temporary_hp": character.temporary_hp,
            "initiative": character.initiative,
            "proficiency_bonus": character.proficiency_bonus,
            "size": character.size,
            "speed": character.speed,
            "darkvision": character.darkvision,
            "species_choices": dict(character.species_choices),
            "persistent_conditions": list(character.persistent_conditions),
            "total_weight": str(character.total_weight),
        }

    @staticmethod
    def _ability_data(card: Any) -> ResultData:
        return {
            "id": card.id,
            "name": card.name,
            "description": card.description,
            "kind": card.kind,
            "properties": list(card.properties),
            "class_ids": sorted(card.class_ids),
            "required_stats": dict(card.required_stats),
            "required_ability_ids": sorted(card.required_ability_ids),
        }

    def _character_data(self, character: Any) -> ResultData:
        return {
            "id": character.id,
            "draft_id": character.draft_id,
            "room_id": character.room_id,
            "owner_id": character.owner_id,
            "name": character.name,
            "ruleset_version": character.ruleset_version,
            "race_id": character.race_id,
            "class_id": character.class_id,
            "stats": dict(character.stats),
            "max_hp": character.max_hp,
            "current_hp": character.current_hp,
            "armor_class": character.armor_class,
            "account_id": character.account_id,
            "archived_at": character.archived_at.isoformat() if character.archived_at else None,
            "level": character.level,
            "experience": character.experience,
            "temporary_hp": character.temporary_hp,
            "initiative": character.initiative,
            "proficiency_bonus": character.proficiency_bonus,
            "size": character.size,
            "speed": character.speed,
            "darkvision": character.darkvision,
            "species_choices": dict(character.species_choices),
            "persistent_conditions": list(character.persistent_conditions),
            "total_weight": str(character.total_weight),
            "abilities": [
                self._ability_data(self._ruleset.card(card_id)) for card_id in character.ability_ids
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
                    "unit_weight": str(item.unit_weight),
                    "slot_compatibility": item.slot_compatibility.value,
                    "equipment_slot": item.equipment_slot,
                }
                for item in character.inventory
            ],
            "version": character.version,
            "created_at": character.created_at.isoformat(),
        }

    @staticmethod
    def _npc_data(npc: NpcNote) -> ResultData:
        return {
            "id": npc.id,
            "room_id": npc.room_id,
            "name": npc.name,
            "details": npc.details,
            "version": npc.version,
            "created_at": npc.created_at.isoformat(),
            "updated_at": npc.updated_at.isoformat(),
        }

    @staticmethod
    def _player_note_data(node: PlayerNoteNode) -> ResultData:
        return {
            "id": node.id,
            "room_id": node.room_id,
            "player_id": node.player_id,
            "parent_id": node.parent_id,
            "kind": node.kind,
            "name": node.name,
            "body": node.body,
            "depth": node.depth,
            "version": node.version,
            "created_at": node.created_at.isoformat(),
            "updated_at": node.updated_at.isoformat(),
        }
