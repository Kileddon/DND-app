from __future__ import annotations

from dataclasses import replace
from datetime import datetime
from types import TracebackType

from sqlalchemy import delete, func, select, update
from sqlalchemy.exc import SQLAlchemyError
from sqlalchemy.orm import Session, sessionmaker

from tabletop_companion.application.ports import ProcessedCommand
from tabletop_companion.domain.access import (
    DeviceRole,
    DeviceStatus,
    LocalDevice,
    PairingInvitation,
    RoomInvitation,
)
from tabletop_companion.domain.errors import (
    EntityNotFoundError,
    InfrastructureError,
    StateConflictError,
)
from tabletop_companion.domain.events import DomainEvent
from tabletop_companion.domain.models import (
    AccessMode,
    Character,
    CharacterDraft,
    DraftStatus,
    InventoryItem,
    ItemDefinition,
    LocalPlayer,
    Room,
)
from tabletop_companion.domain.sessions import GameSession, SessionStatus
from tabletop_companion.infrastructure.tables import (
    CharacterDraftRecord,
    CharacterRecord,
    EventCursorRecord,
    GameEventRecord,
    GameSessionRecord,
    InventoryItemRecord,
    ItemDefinitionRecord,
    LocalDeviceRecord,
    LocalPlayerRecord,
    PairingInvitationRecord,
    ProcessedCommandRecord,
    RoomInvitationRecord,
    RoomRecord,
)


class SqlAlchemyUnitOfWorkFactory:
    def __init__(self, session_factory: sessionmaker[Session]) -> None:
        self._session_factory = session_factory

    def __call__(self) -> SqlAlchemyUnitOfWork:
        return SqlAlchemyUnitOfWork(self._session_factory)


class SqlAlchemyUnitOfWork:
    def __init__(self, session_factory: sessionmaker[Session]) -> None:
        self._session = session_factory()
        self._committed = False

    def __enter__(self) -> SqlAlchemyUnitOfWork:
        return self

    def __exit__(
        self,
        exc_type: type[BaseException] | None,
        exc_value: BaseException | None,
        traceback: TracebackType | None,
    ) -> None:
        del exc_type, exc_value, traceback
        if not self._committed:
            self._session.rollback()
        self._session.close()

    def get_processed_command(self, command_id: str) -> ProcessedCommand | None:
        record = self._session.get(ProcessedCommandRecord, command_id)
        if record is None:
            return None
        return ProcessedCommand(
            command_id=record.command_id,
            command_type=record.command_type,
            payload_hash=record.payload_hash,
            actor_id=record.actor_id,
            device_id=record.device_id,
            client_time=record.client_time,
            host_time=record.host_time,
            result=dict(record.result),
        )

    def add_processed_command(self, command: ProcessedCommand) -> None:
        self._session.add(
            ProcessedCommandRecord(
                command_id=command.command_id,
                command_type=command.command_type,
                payload_hash=command.payload_hash,
                actor_id=command.actor_id,
                device_id=command.device_id,
                client_time=command.client_time,
                host_time=command.host_time,
                result=command.result,
            )
        )

    def add_room(self, room: Room) -> None:
        self._session.add(
            RoomRecord(
                id=room.id,
                name=room.name,
                gm_id=room.gm_id,
                access_mode=room.access_mode.value,
                ruleset_version=room.ruleset_version,
                version=room.version,
                created_at=room.created_at.isoformat(),
                code=room.code,
                password_hash=room.password_hash,
            )
        )
        self._flush_parent("room")

    def get_room(self, room_id: str) -> Room:
        record = self._session.get(RoomRecord, room_id)
        if record is None:
            raise EntityNotFoundError("Room was not found.", details={"room_id": room_id})
        return self._room(record)

    def get_room_by_code(self, room_code: str) -> Room:
        record = self._session.scalar(
            select(RoomRecord).where(RoomRecord.code == room_code.upper())
        )
        if record is None:
            raise EntityNotFoundError(
                "Room was not found.", details={"room_code": room_code.upper()}
            )
        return self._room(record)

    @staticmethod
    def _room(record: RoomRecord) -> Room:
        return Room(
            id=record.id,
            name=record.name,
            gm_id=record.gm_id,
            access_mode=AccessMode(record.access_mode),
            ruleset_version=record.ruleset_version,
            version=record.version,
            created_at=datetime.fromisoformat(record.created_at),
            code=record.code,
            password_hash=record.password_hash,
        )

    def add_local_player(self, player: LocalPlayer) -> None:
        self._session.add(
            LocalPlayerRecord(
                id=player.id,
                room_id=player.room_id,
                display_name=player.display_name,
                version=player.version,
                created_at=player.created_at.isoformat(),
                recovery_code_digest=player.recovery_code_digest,
                selected_character_id=player.selected_character_id,
                updated_at=(player.updated_at or player.created_at).isoformat(),
            )
        )
        self._flush_parent("local player")

    def get_local_player(self, player_id: str) -> LocalPlayer:
        record = self._session.get(LocalPlayerRecord, player_id)
        if record is None:
            raise EntityNotFoundError(
                "Local player was not found.", details={"player_id": player_id}
            )
        return LocalPlayer(
            id=record.id,
            room_id=record.room_id,
            display_name=record.display_name,
            version=record.version,
            created_at=datetime.fromisoformat(record.created_at),
            recovery_code_digest=record.recovery_code_digest,
            selected_character_id=record.selected_character_id,
            updated_at=datetime.fromisoformat(record.updated_at),
        )

    def save_local_player(self, player: LocalPlayer) -> None:
        updated_id = self._session.scalar(
            update(LocalPlayerRecord)
            .where(
                LocalPlayerRecord.id == player.id,
                LocalPlayerRecord.version == player.version - 1,
            )
            .values(
                display_name=player.display_name,
                version=player.version,
                recovery_code_digest=player.recovery_code_digest,
                selected_character_id=player.selected_character_id,
                updated_at=(player.updated_at or player.created_at).isoformat(),
            )
            .returning(LocalPlayerRecord.id)
        )
        if updated_id is None:
            raise StateConflictError("Local player changed concurrently.")

    def list_local_players(self, room_id: str) -> list[LocalPlayer]:
        records = self._session.scalars(
            select(LocalPlayerRecord)
            .where(LocalPlayerRecord.room_id == room_id)
            .order_by(LocalPlayerRecord.created_at, LocalPlayerRecord.id)
        ).all()
        return [
            LocalPlayer(
                id=record.id,
                room_id=record.room_id,
                display_name=record.display_name,
                version=record.version,
                created_at=datetime.fromisoformat(record.created_at),
                recovery_code_digest=record.recovery_code_digest,
                selected_character_id=record.selected_character_id,
                updated_at=datetime.fromisoformat(record.updated_at),
            )
            for record in records
        ]

    def add_character_draft(self, draft: CharacterDraft) -> None:
        self._session.add(self._draft_record(draft))

    def get_character_draft(self, draft_id: str) -> CharacterDraft:
        record = self._session.get(CharacterDraftRecord, draft_id)
        if record is None:
            raise EntityNotFoundError(
                "Character draft was not found.", details={"draft_id": draft_id}
            )
        return self._draft(record)

    def save_character_draft(self, draft: CharacterDraft) -> None:
        updated_id = self._session.scalar(
            update(CharacterDraftRecord)
            .where(
                CharacterDraftRecord.id == draft.id,
                CharacterDraftRecord.version == draft.version - 1,
            )
            .values(
                stats=dict(draft.stats),
                offered_card_ids=list(draft.offered_card_ids),
                chosen_card_ids=list(draft.chosen_card_ids),
                generation=draft.generation,
                status=draft.status.value,
                version=draft.version,
                updated_at=draft.updated_at.isoformat(),
            )
            .returning(CharacterDraftRecord.id)
        )
        if updated_id is None:
            raise StateConflictError("Character draft changed concurrently.")

    def add_character(self, character: Character) -> None:
        self._session.add(
            CharacterRecord(
                id=character.id,
                draft_id=character.draft_id,
                room_id=character.room_id,
                owner_id=character.owner_id,
                name=character.name,
                ruleset_version=character.ruleset_version,
                stats=dict(character.stats),
                ability_ids=list(character.ability_ids),
                version=character.version,
                created_at=character.created_at.isoformat(),
            )
        )

    def get_character(self, character_id: str) -> Character:
        record = self._session.get(CharacterRecord, character_id)
        if record is None:
            raise EntityNotFoundError(
                "Character was not found.", details={"character_id": character_id}
            )
        item_rows = self._session.execute(
            select(InventoryItemRecord, ItemDefinitionRecord)
            .join(
                ItemDefinitionRecord,
                ItemDefinitionRecord.id == InventoryItemRecord.definition_id,
            )
            .where(InventoryItemRecord.character_id == character_id)
            .order_by(InventoryItemRecord.created_at, InventoryItemRecord.id)
        ).all()
        inventory = [
            InventoryItem(
                id=item.id,
                definition_id=definition.id,
                name=definition.name,
                consumable=definition.consumable,
                locked=definition.locked,
                quantity=item.quantity,
                equipped=item.equipped,
                charges=item.charges,
                created_at=datetime.fromisoformat(item.created_at),
            )
            for item, definition in item_rows
        ]
        return Character(
            id=record.id,
            draft_id=record.draft_id,
            room_id=record.room_id,
            owner_id=record.owner_id,
            name=record.name,
            ruleset_version=record.ruleset_version,
            stats=dict(record.stats),
            ability_ids=list(record.ability_ids),
            version=record.version,
            created_at=datetime.fromisoformat(record.created_at),
            inventory=inventory,
        )

    def list_characters_for_player(self, player_id: str) -> list[Character]:
        character_ids = self._session.scalars(
            select(CharacterRecord.id)
            .where(CharacterRecord.owner_id == player_id)
            .order_by(CharacterRecord.created_at, CharacterRecord.id)
        ).all()
        return [self.get_character(character_id) for character_id in character_ids]

    def add_pairing_invitation(self, invitation: PairingInvitation) -> None:
        self._session.add(
            PairingInvitationRecord(
                id=invitation.id,
                room_id=invitation.room_id,
                role=invitation.role.value,
                token_digest=invitation.token_digest,
                short_code_digest=invitation.short_code_digest,
                expires_at=invitation.expires_at.isoformat(),
                created_by=invitation.created_by,
                created_at=invitation.created_at.isoformat(),
                used_at=invitation.used_at.isoformat() if invitation.used_at else None,
                revoked_at=invitation.revoked_at.isoformat() if invitation.revoked_at else None,
            )
        )

    def get_pairing_by_token_digest(self, digest: str) -> PairingInvitation:
        record = self._session.scalar(
            select(PairingInvitationRecord).where(PairingInvitationRecord.token_digest == digest)
        )
        if record is None:
            raise EntityNotFoundError("Pairing invitation was not found.")
        return self._pairing_invitation(record)

    def get_pairing(self, invitation_id: str) -> PairingInvitation:
        record = self._session.get(PairingInvitationRecord, invitation_id)
        if record is None:
            raise EntityNotFoundError("Pairing invitation was not found.")
        return self._pairing_invitation(record)

    def get_pairing_by_short_code_digest(self, digest: str) -> PairingInvitation:
        record = self._session.scalar(
            select(PairingInvitationRecord).where(
                PairingInvitationRecord.short_code_digest == digest
            )
        )
        if record is None:
            raise EntityNotFoundError("Pairing invitation was not found.")
        return self._pairing_invitation(record)

    def save_pairing_invitation(self, invitation: PairingInvitation) -> None:
        record = self._session.get(PairingInvitationRecord, invitation.id)
        if record is None:
            raise EntityNotFoundError("Pairing invitation was not found.")
        record.used_at = invitation.used_at.isoformat() if invitation.used_at else None
        record.revoked_at = invitation.revoked_at.isoformat() if invitation.revoked_at else None

    def revoke_pairing_invitations(self, room_id: str, revoked_at: str) -> int:
        result = self._session.execute(
            update(PairingInvitationRecord)
            .where(
                PairingInvitationRecord.room_id == room_id,
                PairingInvitationRecord.used_at.is_(None),
                PairingInvitationRecord.revoked_at.is_(None),
            )
            .values(revoked_at=revoked_at)
        )
        return result.rowcount  # type: ignore[attr-defined,no-any-return]

    def add_room_invitation(self, invitation: RoomInvitation) -> None:
        self._session.add(
            RoomInvitationRecord(
                id=invitation.id,
                room_id=invitation.room_id,
                token_digest=invitation.token_digest,
                expires_at=invitation.expires_at.isoformat(),
                max_uses=invitation.max_uses,
                use_count=invitation.use_count,
                created_at=invitation.created_at.isoformat(),
                revoked_at=invitation.revoked_at.isoformat() if invitation.revoked_at else None,
            )
        )

    def get_room_invitation_by_digest(self, digest: str) -> RoomInvitation:
        record = self._session.scalar(
            select(RoomInvitationRecord).where(RoomInvitationRecord.token_digest == digest)
        )
        if record is None:
            raise EntityNotFoundError("Room invitation was not found.")
        return self._room_invitation(record)

    def get_room_invitation(self, invitation_id: str) -> RoomInvitation:
        record = self._session.get(RoomInvitationRecord, invitation_id)
        if record is None:
            raise EntityNotFoundError("Room invitation was not found.")
        return self._room_invitation(record)

    def save_room_invitation(self, invitation: RoomInvitation) -> None:
        record = self._session.get(RoomInvitationRecord, invitation.id)
        if record is None:
            raise EntityNotFoundError("Room invitation was not found.")
        record.use_count = invitation.use_count
        record.revoked_at = invitation.revoked_at.isoformat() if invitation.revoked_at else None

    def add_local_device(self, device: LocalDevice) -> None:
        self._session.add(
            LocalDeviceRecord(
                id=device.id,
                room_id=device.room_id,
                player_id=device.player_id,
                label=device.label,
                role=device.role.value,
                credential_digest=device.credential_digest,
                status=device.status.value,
                created_at=device.created_at.isoformat(),
                last_seen_at=device.last_seen_at.isoformat(),
                expires_at=device.expires_at.isoformat(),
                revoked_at=device.revoked_at.isoformat() if device.revoked_at else None,
            )
        )

    def get_device(self, device_id: str) -> LocalDevice:
        record = self._session.get(LocalDeviceRecord, device_id)
        if record is None:
            raise EntityNotFoundError("Local device was not found.")
        return self._local_device(record)

    def get_device_by_credential_digest(self, digest: str) -> LocalDevice:
        record = self._session.scalar(
            select(LocalDeviceRecord).where(LocalDeviceRecord.credential_digest == digest)
        )
        if record is None:
            raise EntityNotFoundError("Device credential was not found.")
        return self._local_device(record)

    def save_local_device(self, device: LocalDevice) -> None:
        record = self._session.get(LocalDeviceRecord, device.id)
        if record is None:
            raise EntityNotFoundError("Local device was not found.")
        record.player_id = device.player_id
        record.credential_digest = device.credential_digest
        record.status = device.status.value
        record.last_seen_at = device.last_seen_at.isoformat()
        record.expires_at = device.expires_at.isoformat()
        record.revoked_at = device.revoked_at.isoformat() if device.revoked_at else None

    def list_local_devices(self, room_id: str) -> list[LocalDevice]:
        records = self._session.scalars(
            select(LocalDeviceRecord)
            .where(LocalDeviceRecord.room_id == room_id)
            .order_by(LocalDeviceRecord.created_at, LocalDeviceRecord.id)
        ).all()
        return [self._local_device(record) for record in records]

    def add_game_session(self, session: GameSession) -> None:
        self._session.add(self._session_record(session))

    def get_game_session(self, session_id: str) -> GameSession:
        record = self._session.get(GameSessionRecord, session_id)
        if record is None:
            raise EntityNotFoundError(
                "Game session was not found.", details={"session_id": session_id}
            )
        return self._game_session(record)

    def get_unfinished_session(self, room_id: str) -> GameSession | None:
        record = self._session.scalar(
            select(GameSessionRecord).where(
                GameSessionRecord.room_id == room_id,
                GameSessionRecord.status != SessionStatus.COMPLETED.value,
            )
        )
        return self._game_session(record) if record else None

    def save_game_session(self, session: GameSession) -> None:
        updated_id = self._session.scalar(
            update(GameSessionRecord)
            .where(
                GameSessionRecord.id == session.id,
                GameSessionRecord.version == session.version - 1,
            )
            .values(
                status=session.status.value,
                version=session.version,
                updated_at=session.updated_at.isoformat(),
                started_at=session.started_at.isoformat() if session.started_at else None,
                paused_at=session.paused_at.isoformat() if session.paused_at else None,
                completed_at=session.completed_at.isoformat() if session.completed_at else None,
            )
            .returning(GameSessionRecord.id)
        )
        if updated_id is None:
            raise StateConflictError("Game session changed concurrently.")

    def add_item_definition(self, definition: ItemDefinition) -> None:
        self._session.add(
            ItemDefinitionRecord(
                id=definition.id,
                name=definition.name,
                consumable=definition.consumable,
                locked=definition.locked,
            )
        )
        try:
            self._session.flush()
        except SQLAlchemyError as error:
            self._session.rollback()
            raise InfrastructureError("Could not persist item definition.") from error

    def save_character(self, character: Character) -> None:
        updated_id = self._session.scalar(
            update(CharacterRecord)
            .where(
                CharacterRecord.id == character.id,
                CharacterRecord.version == character.version - 1,
            )
            .values(version=character.version)
            .returning(CharacterRecord.id)
        )
        if updated_id is None:
            raise StateConflictError("Character changed concurrently.")
        current_records = {
            item.id: item
            for item in self._session.scalars(
                select(InventoryItemRecord).where(InventoryItemRecord.character_id == character.id)
            )
        }
        domain_ids = {item.id for item in character.inventory}
        for item_id in current_records.keys() - domain_ids:
            self._session.execute(
                delete(InventoryItemRecord).where(InventoryItemRecord.id == item_id)
            )
        for item in character.inventory:
            item_record = current_records.get(item.id)
            if item_record is None:
                self._session.add(
                    InventoryItemRecord(
                        id=item.id,
                        definition_id=item.definition_id,
                        character_id=character.id,
                        quantity=item.quantity,
                        equipped=item.equipped,
                        charges=item.charges,
                        created_at=item.created_at.isoformat(),
                    )
                )
            else:
                item_record.quantity = item.quantity
                item_record.equipped = item.equipped
                item_record.charges = item.charges

    def add_event(self, event: DomainEvent) -> DomainEvent:
        try:
            self._session.flush()
        except SQLAlchemyError as error:
            self._session.rollback()
            raise InfrastructureError("Could not persist command state.") from error
        cursor = self._session.scalar(
            update(EventCursorRecord)
            .where(EventCursorRecord.id == 1)
            .values(last_cursor=EventCursorRecord.last_cursor + 1)
            .returning(EventCursorRecord.last_cursor)
        )
        if cursor is None:
            raise InfrastructureError("Event cursor sequence is not initialized.")
        self._session.add(
            GameEventRecord(
                id=event.id,
                event_type=event.event_type,
                aggregate_type=event.aggregate_type,
                aggregate_id=event.aggregate_id,
                room_id=event.room_id,
                actor_id=event.actor_id,
                source_id=event.source_id,
                target_ids=list(event.target_ids),
                payload=event.payload,
                visibility=event.visibility,
                schema_version=event.schema_version,
                command_id=event.command_id,
                occurred_at=event.occurred_at.isoformat(),
                cursor=cursor,
                session_id=event.session_id,
            )
        )
        return replace(event, cursor=cursor)

    def list_events(self, room_id: str) -> list[DomainEvent]:
        records = self._session.scalars(
            select(GameEventRecord)
            .where(GameEventRecord.room_id == room_id)
            .order_by(GameEventRecord.occurred_at, GameEventRecord.id)
        ).all()
        return [self._event(record) for record in records]

    def list_events_after(self, room_id: str, cursor: int, limit: int) -> list[DomainEvent]:
        records = self._session.scalars(
            select(GameEventRecord)
            .where(GameEventRecord.room_id == room_id, GameEventRecord.cursor > cursor)
            .order_by(GameEventRecord.cursor)
            .limit(limit)
        ).all()
        return [self._event(record) for record in records]

    def list_events_by_command(self, command_id: str) -> list[DomainEvent]:
        records = self._session.scalars(
            select(GameEventRecord)
            .where(GameEventRecord.command_id == command_id)
            .order_by(GameEventRecord.cursor)
        ).all()
        return [self._event(record) for record in records]

    def event_cursor_bounds(self, room_id: str) -> tuple[int | None, int]:
        minimum, maximum = self._session.execute(
            select(func.min(GameEventRecord.cursor), func.max(GameEventRecord.cursor)).where(
                GameEventRecord.room_id == room_id
            )
        ).one()
        return minimum, maximum or 0

    def commit(self) -> None:
        try:
            self._session.commit()
            self._committed = True
        except SQLAlchemyError as error:
            self._session.rollback()
            raise InfrastructureError("Database transaction failed.") from error

    def rollback(self) -> None:
        self._session.rollback()

    def _flush_parent(self, entity_name: str) -> None:
        try:
            self._session.flush()
        except SQLAlchemyError as error:
            self._session.rollback()
            raise InfrastructureError(f"Could not persist {entity_name}.") from error

    @staticmethod
    def _draft_record(draft: CharacterDraft) -> CharacterDraftRecord:
        return CharacterDraftRecord(
            id=draft.id,
            room_id=draft.room_id,
            owner_id=draft.owner_id,
            name=draft.name,
            ruleset_version=draft.ruleset_version,
            stats=dict(draft.stats),
            offered_card_ids=list(draft.offered_card_ids),
            chosen_card_ids=list(draft.chosen_card_ids),
            generation=draft.generation,
            status=draft.status.value,
            version=draft.version,
            created_at=draft.created_at.isoformat(),
            updated_at=draft.updated_at.isoformat(),
        )

    @staticmethod
    def _draft(record: CharacterDraftRecord) -> CharacterDraft:
        return CharacterDraft(
            id=record.id,
            room_id=record.room_id,
            owner_id=record.owner_id,
            name=record.name,
            ruleset_version=record.ruleset_version,
            stats=dict(record.stats),
            offered_card_ids=list(record.offered_card_ids),
            chosen_card_ids=list(record.chosen_card_ids),
            generation=record.generation,
            status=DraftStatus(record.status),
            version=record.version,
            created_at=datetime.fromisoformat(record.created_at),
            updated_at=datetime.fromisoformat(record.updated_at),
        )

    @staticmethod
    def _pairing_invitation(record: PairingInvitationRecord) -> PairingInvitation:
        return PairingInvitation(
            id=record.id,
            room_id=record.room_id,
            role=DeviceRole(record.role),
            token_digest=record.token_digest,
            short_code_digest=record.short_code_digest,
            expires_at=datetime.fromisoformat(record.expires_at),
            created_by=record.created_by,
            created_at=datetime.fromisoformat(record.created_at),
            used_at=datetime.fromisoformat(record.used_at) if record.used_at else None,
            revoked_at=datetime.fromisoformat(record.revoked_at) if record.revoked_at else None,
        )

    @staticmethod
    def _room_invitation(record: RoomInvitationRecord) -> RoomInvitation:
        return RoomInvitation(
            id=record.id,
            room_id=record.room_id,
            token_digest=record.token_digest,
            expires_at=datetime.fromisoformat(record.expires_at),
            max_uses=record.max_uses,
            use_count=record.use_count,
            created_at=datetime.fromisoformat(record.created_at),
            revoked_at=datetime.fromisoformat(record.revoked_at) if record.revoked_at else None,
        )

    @staticmethod
    def _local_device(record: LocalDeviceRecord) -> LocalDevice:
        return LocalDevice(
            id=record.id,
            room_id=record.room_id,
            player_id=record.player_id,
            label=record.label,
            role=DeviceRole(record.role),
            credential_digest=record.credential_digest,
            status=DeviceStatus(record.status),
            created_at=datetime.fromisoformat(record.created_at),
            last_seen_at=datetime.fromisoformat(record.last_seen_at),
            expires_at=datetime.fromisoformat(record.expires_at),
            revoked_at=datetime.fromisoformat(record.revoked_at) if record.revoked_at else None,
        )

    @staticmethod
    def _session_record(session: GameSession) -> GameSessionRecord:
        return GameSessionRecord(
            id=session.id,
            room_id=session.room_id,
            status=session.status.value,
            version=session.version,
            created_at=session.created_at.isoformat(),
            updated_at=session.updated_at.isoformat(),
            started_at=session.started_at.isoformat() if session.started_at else None,
            paused_at=session.paused_at.isoformat() if session.paused_at else None,
            completed_at=session.completed_at.isoformat() if session.completed_at else None,
        )

    @staticmethod
    def _game_session(record: GameSessionRecord) -> GameSession:
        return GameSession(
            id=record.id,
            room_id=record.room_id,
            status=SessionStatus(record.status),
            version=record.version,
            created_at=datetime.fromisoformat(record.created_at),
            updated_at=datetime.fromisoformat(record.updated_at),
            started_at=datetime.fromisoformat(record.started_at) if record.started_at else None,
            paused_at=datetime.fromisoformat(record.paused_at) if record.paused_at else None,
            completed_at=(
                datetime.fromisoformat(record.completed_at) if record.completed_at else None
            ),
        )

    @staticmethod
    def _event(record: GameEventRecord) -> DomainEvent:
        return DomainEvent(
            id=record.id,
            event_type=record.event_type,
            aggregate_type=record.aggregate_type,
            aggregate_id=record.aggregate_id,
            room_id=record.room_id,
            actor_id=record.actor_id,
            source_id=record.source_id,
            target_ids=tuple(record.target_ids),
            payload=dict(record.payload),
            visibility=record.visibility,
            schema_version=record.schema_version,
            command_id=record.command_id,
            occurred_at=datetime.fromisoformat(record.occurred_at),
            cursor=record.cursor,
            session_id=record.session_id,
        )
