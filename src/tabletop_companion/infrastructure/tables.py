from __future__ import annotations

from typing import Any

from sqlalchemy import JSON, Boolean, CheckConstraint, ForeignKey, Index, Integer, String, text
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column


class Base(DeclarativeBase):
    pass


class RoomRecord(Base):
    __tablename__ = "rooms"

    id: Mapped[str] = mapped_column(String(36), primary_key=True)
    name: Mapped[str] = mapped_column(String(120))
    gm_id: Mapped[str] = mapped_column(String(36))
    access_mode: Mapped[str] = mapped_column(String(24))
    ruleset_version: Mapped[str] = mapped_column(String(64))
    version: Mapped[int] = mapped_column(Integer)
    created_at: Mapped[str] = mapped_column(String(40))
    code: Mapped[str] = mapped_column(String(8), unique=True)
    password_hash: Mapped[str | None] = mapped_column(String(255), nullable=True)


class LocalPlayerRecord(Base):
    __tablename__ = "local_players"

    id: Mapped[str] = mapped_column(String(36), primary_key=True)
    room_id: Mapped[str] = mapped_column(ForeignKey("rooms.id"), index=True)
    display_name: Mapped[str] = mapped_column(String(80))
    version: Mapped[int] = mapped_column(Integer)
    created_at: Mapped[str] = mapped_column(String(40))
    recovery_code_digest: Mapped[str | None] = mapped_column(String(64), nullable=True)
    selected_character_id: Mapped[str | None] = mapped_column(String(36), nullable=True)
    updated_at: Mapped[str] = mapped_column(String(40))


class CharacterDraftRecord(Base):
    __tablename__ = "character_drafts"

    id: Mapped[str] = mapped_column(String(36), primary_key=True)
    room_id: Mapped[str] = mapped_column(ForeignKey("rooms.id"))
    owner_id: Mapped[str] = mapped_column(ForeignKey("local_players.id"), index=True)
    name: Mapped[str] = mapped_column(String(80))
    ruleset_version: Mapped[str] = mapped_column(String(64))
    stats: Mapped[dict[str, int]] = mapped_column(JSON)
    offered_card_ids: Mapped[list[str]] = mapped_column(JSON)
    chosen_card_ids: Mapped[list[str]] = mapped_column(JSON)
    generation: Mapped[int] = mapped_column(Integer)
    status: Mapped[str] = mapped_column(String(24))
    version: Mapped[int] = mapped_column(Integer)
    created_at: Mapped[str] = mapped_column(String(40))
    updated_at: Mapped[str] = mapped_column(String(40))


class CharacterRecord(Base):
    __tablename__ = "characters"

    id: Mapped[str] = mapped_column(String(36), primary_key=True)
    draft_id: Mapped[str] = mapped_column(String(36), unique=True)
    room_id: Mapped[str] = mapped_column(ForeignKey("rooms.id"))
    owner_id: Mapped[str] = mapped_column(ForeignKey("local_players.id"), index=True)
    name: Mapped[str] = mapped_column(String(80))
    ruleset_version: Mapped[str] = mapped_column(String(64))
    stats: Mapped[dict[str, int]] = mapped_column(JSON)
    ability_ids: Mapped[list[str]] = mapped_column(JSON)
    version: Mapped[int] = mapped_column(Integer)
    created_at: Mapped[str] = mapped_column(String(40))


class ItemDefinitionRecord(Base):
    __tablename__ = "item_definitions"

    id: Mapped[str] = mapped_column(String(36), primary_key=True)
    name: Mapped[str] = mapped_column(String(120))
    consumable: Mapped[bool] = mapped_column(Boolean)
    locked: Mapped[bool] = mapped_column(Boolean)


class InventoryItemRecord(Base):
    __tablename__ = "inventory_items"

    id: Mapped[str] = mapped_column(String(36), primary_key=True)
    definition_id: Mapped[str] = mapped_column(ForeignKey("item_definitions.id"))
    character_id: Mapped[str] = mapped_column(ForeignKey("characters.id"), index=True)
    quantity: Mapped[int] = mapped_column(Integer)
    equipped: Mapped[bool] = mapped_column(Boolean)
    charges: Mapped[int | None] = mapped_column(Integer, nullable=True)
    created_at: Mapped[str] = mapped_column(String(40))


class GameEventRecord(Base):
    __tablename__ = "game_events"
    __table_args__ = (
        Index("ix_game_events_aggregate", "aggregate_type", "aggregate_id"),
        Index("ix_game_events_command_id", "command_id"),
        Index("uq_game_events_cursor", "cursor", unique=True),
    )

    id: Mapped[str] = mapped_column(String(36), primary_key=True)
    event_type: Mapped[str] = mapped_column(String(80))
    aggregate_type: Mapped[str] = mapped_column(String(40))
    aggregate_id: Mapped[str] = mapped_column(String(36))
    room_id: Mapped[str] = mapped_column(ForeignKey("rooms.id"), index=True)
    actor_id: Mapped[str] = mapped_column(String(36))
    source_id: Mapped[str | None] = mapped_column(String(36), nullable=True)
    target_ids: Mapped[list[str]] = mapped_column(JSON)
    payload: Mapped[dict[str, Any]] = mapped_column(JSON)
    visibility: Mapped[str] = mapped_column(String(24))
    schema_version: Mapped[int] = mapped_column(Integer)
    command_id: Mapped[str] = mapped_column(String(36))
    occurred_at: Mapped[str] = mapped_column(String(40))
    cursor: Mapped[int] = mapped_column(Integer)
    session_id: Mapped[str | None] = mapped_column(String(36), nullable=True)


class EventCursorRecord(Base):
    __tablename__ = "event_cursor_sequence"
    __table_args__ = (CheckConstraint("id = 1", name="ck_event_cursor_singleton"),)

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    last_cursor: Mapped[int] = mapped_column(Integer)


class PairingInvitationRecord(Base):
    __tablename__ = "pairing_invitations"

    id: Mapped[str] = mapped_column(String(36), primary_key=True)
    room_id: Mapped[str] = mapped_column(ForeignKey("rooms.id"), index=True)
    role: Mapped[str] = mapped_column(String(16))
    token_digest: Mapped[str] = mapped_column(String(64), unique=True)
    short_code_digest: Mapped[str] = mapped_column(String(64), unique=True)
    expires_at: Mapped[str] = mapped_column(String(40))
    created_by: Mapped[str] = mapped_column(String(36))
    created_at: Mapped[str] = mapped_column(String(40))
    used_at: Mapped[str | None] = mapped_column(String(40), nullable=True)
    revoked_at: Mapped[str | None] = mapped_column(String(40), nullable=True)


class RoomInvitationRecord(Base):
    __tablename__ = "room_invitations"

    id: Mapped[str] = mapped_column(String(36), primary_key=True)
    room_id: Mapped[str] = mapped_column(ForeignKey("rooms.id"), index=True)
    token_digest: Mapped[str] = mapped_column(String(64), unique=True)
    expires_at: Mapped[str] = mapped_column(String(40))
    max_uses: Mapped[int] = mapped_column(Integer)
    use_count: Mapped[int] = mapped_column(Integer)
    created_at: Mapped[str] = mapped_column(String(40))
    revoked_at: Mapped[str | None] = mapped_column(String(40), nullable=True)


class LocalDeviceRecord(Base):
    __tablename__ = "local_devices"

    id: Mapped[str] = mapped_column(String(36), primary_key=True)
    room_id: Mapped[str] = mapped_column(ForeignKey("rooms.id"), index=True)
    player_id: Mapped[str | None] = mapped_column(
        ForeignKey("local_players.id"), nullable=True, index=True
    )
    label: Mapped[str] = mapped_column(String(120))
    role: Mapped[str] = mapped_column(String(16))
    credential_digest: Mapped[str] = mapped_column(String(64), unique=True)
    status: Mapped[str] = mapped_column(String(16))
    created_at: Mapped[str] = mapped_column(String(40))
    last_seen_at: Mapped[str] = mapped_column(String(40))
    expires_at: Mapped[str] = mapped_column(String(40))
    revoked_at: Mapped[str | None] = mapped_column(String(40), nullable=True)


class GameSessionRecord(Base):
    __tablename__ = "game_sessions"
    __table_args__ = (
        Index(
            "uq_game_sessions_room_unfinished",
            "room_id",
            unique=True,
            sqlite_where=text("status != 'COMPLETED'"),
        ),
    )

    id: Mapped[str] = mapped_column(String(36), primary_key=True)
    room_id: Mapped[str] = mapped_column(ForeignKey("rooms.id"), index=True)
    status: Mapped[str] = mapped_column(String(20))
    version: Mapped[int] = mapped_column(Integer)
    created_at: Mapped[str] = mapped_column(String(40))
    updated_at: Mapped[str] = mapped_column(String(40))
    started_at: Mapped[str | None] = mapped_column(String(40), nullable=True)
    paused_at: Mapped[str | None] = mapped_column(String(40), nullable=True)
    completed_at: Mapped[str | None] = mapped_column(String(40), nullable=True)


class ProcessedCommandRecord(Base):
    __tablename__ = "processed_commands"

    command_id: Mapped[str] = mapped_column(String(36), primary_key=True)
    command_type: Mapped[str] = mapped_column(String(80))
    payload_hash: Mapped[str] = mapped_column(String(64))
    actor_id: Mapped[str] = mapped_column(String(36))
    device_id: Mapped[str] = mapped_column(String(120))
    client_time: Mapped[str | None] = mapped_column(String(40), nullable=True)
    host_time: Mapped[str] = mapped_column(String(40))
    result: Mapped[dict[str, Any]] = mapped_column(JSON)
