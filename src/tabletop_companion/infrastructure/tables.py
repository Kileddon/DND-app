from __future__ import annotations

from typing import Any

from sqlalchemy import (
    JSON,
    Boolean,
    CheckConstraint,
    ForeignKey,
    Index,
    Integer,
    Numeric,
    String,
    UniqueConstraint,
    text,
)
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


class AccountRecord(Base):
    __tablename__ = "accounts"

    id: Mapped[str] = mapped_column(String(36), primary_key=True)
    display_name: Mapped[str] = mapped_column(String(80))
    cloud_identity: Mapped[str | None] = mapped_column(String(255), nullable=True, unique=True)
    version: Mapped[int] = mapped_column(Integer)
    created_at: Mapped[str] = mapped_column(String(40))
    updated_at: Mapped[str] = mapped_column(String(40))


class LocalPlayerRecord(Base):
    __tablename__ = "local_players"
    __table_args__ = (UniqueConstraint("account_id", "room_id", name="uq_membership_account_room"),)

    id: Mapped[str] = mapped_column(String(36), primary_key=True)
    room_id: Mapped[str] = mapped_column(ForeignKey("rooms.id"), index=True)
    display_name: Mapped[str] = mapped_column(String(80))
    version: Mapped[int] = mapped_column(Integer)
    created_at: Mapped[str] = mapped_column(String(40))
    selected_character_id: Mapped[str | None] = mapped_column(String(36), nullable=True)
    updated_at: Mapped[str] = mapped_column(String(40))
    removed_at: Mapped[str | None] = mapped_column(String(40), nullable=True)
    account_id: Mapped[str | None] = mapped_column(
        ForeignKey("accounts.id"), nullable=True, index=True
    )


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
    race_id: Mapped[str] = mapped_column(String(40))
    class_id: Mapped[str] = mapped_column(String(40))
    account_id: Mapped[str | None] = mapped_column(ForeignKey("accounts.id"), nullable=True)
    step: Mapped[str] = mapped_column(String(32), default="name")
    species_choices: Mapped[dict[str, str]] = mapped_column(JSON, default=dict)
    stat_method: Mapped[str | None] = mapped_column(String(20), nullable=True)
    base_stats: Mapped[dict[str, int]] = mapped_column(JSON, default=dict)
    background: Mapped[dict[str, Any]] = mapped_column(JSON, default=dict)
    random_rolls: Mapped[list[dict[str, Any]]] = mapped_column(JSON, default=list)


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
    race_id: Mapped[str] = mapped_column(String(40))
    class_id: Mapped[str] = mapped_column(String(40))
    max_hp: Mapped[int] = mapped_column(Integer)
    current_hp: Mapped[int] = mapped_column(Integer)
    armor_class: Mapped[int] = mapped_column(Integer)
    account_id: Mapped[str | None] = mapped_column(
        ForeignKey("accounts.id"), nullable=True, index=True
    )
    archived_at: Mapped[str | None] = mapped_column(String(40), nullable=True)
    level: Mapped[int] = mapped_column(Integer, default=1)
    experience: Mapped[int] = mapped_column(Integer, default=0)
    temporary_hp: Mapped[int] = mapped_column(Integer, default=0)
    initiative: Mapped[int] = mapped_column(Integer, default=0)
    proficiency_bonus: Mapped[int] = mapped_column(Integer, default=2)
    size: Mapped[str] = mapped_column(String(16), default="medium")
    speed: Mapped[int] = mapped_column(Integer, default=30)
    darkvision: Mapped[int] = mapped_column(Integer, default=0)
    species_choices: Mapped[dict[str, str]] = mapped_column(JSON, default=dict)
    persistent_conditions: Mapped[list[dict[str, Any]]] = mapped_column(JSON, default=list)


class CharacterRoomAssignmentRecord(Base):
    __tablename__ = "character_room_assignments"

    character_id: Mapped[str] = mapped_column(ForeignKey("characters.id"), primary_key=True)
    room_id: Mapped[str] = mapped_column(ForeignKey("rooms.id"), primary_key=True)
    assigned_at: Mapped[str] = mapped_column(String(40))


class GmNotesRecord(Base):
    __tablename__ = "gm_notes"

    room_id: Mapped[str] = mapped_column(ForeignKey("rooms.id"), primary_key=True)
    campaign: Mapped[str] = mapped_column(String(20000))
    other: Mapped[str] = mapped_column(String(20000))
    version: Mapped[int] = mapped_column(Integer)
    updated_at: Mapped[str] = mapped_column(String(40))


class NpcNoteRecord(Base):
    __tablename__ = "npc_notes"

    id: Mapped[str] = mapped_column(String(36), primary_key=True)
    room_id: Mapped[str] = mapped_column(ForeignKey("rooms.id"), index=True)
    name: Mapped[str] = mapped_column(String(120))
    details: Mapped[str] = mapped_column(String(20000))
    version: Mapped[int] = mapped_column(Integer)
    created_at: Mapped[str] = mapped_column(String(40))
    updated_at: Mapped[str] = mapped_column(String(40))


class ItemDefinitionRecord(Base):
    __tablename__ = "item_definitions"

    id: Mapped[str] = mapped_column(String(36), primary_key=True)
    name: Mapped[str] = mapped_column(String(120))
    consumable: Mapped[bool] = mapped_column(Boolean)
    locked: Mapped[bool] = mapped_column(Boolean)
    unit_weight: Mapped[Any] = mapped_column(Numeric(10, 3), default=0)
    slot_compatibility: Mapped[str] = mapped_column(String(16), default="none")


class InventoryItemRecord(Base):
    __tablename__ = "inventory_items"

    id: Mapped[str] = mapped_column(String(36), primary_key=True)
    definition_id: Mapped[str] = mapped_column(ForeignKey("item_definitions.id"))
    character_id: Mapped[str] = mapped_column(ForeignKey("characters.id"), index=True)
    quantity: Mapped[int] = mapped_column(Integer)
    equipped: Mapped[bool] = mapped_column(Boolean)
    charges: Mapped[int | None] = mapped_column(Integer, nullable=True)
    created_at: Mapped[str] = mapped_column(String(40))
    equipment_slot: Mapped[str | None] = mapped_column(String(16), nullable=True)


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
    visibility: Mapped[str] = mapped_column(String(64))
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
    account_id: Mapped[str | None] = mapped_column(
        ForeignKey("accounts.id"), nullable=True, index=True
    )


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


class CombatRecord(Base):
    __tablename__ = "combats"
    __table_args__ = (
        Index(
            "uq_combats_room_active",
            "room_id",
            unique=True,
            sqlite_where=text("status IN ('ACTIVE', 'PAUSED')"),
        ),
    )

    id: Mapped[str] = mapped_column(String(36), primary_key=True)
    room_id: Mapped[str] = mapped_column(ForeignKey("rooms.id"), index=True)
    session_id: Mapped[str] = mapped_column(ForeignKey("game_sessions.id"), index=True)
    status: Mapped[str] = mapped_column(String(20))
    round_number: Mapped[int] = mapped_column(Integer)
    current_entry_id: Mapped[str | None] = mapped_column(String(36), nullable=True)
    entries: Mapped[list[dict[str, Any]]] = mapped_column(JSON)
    version: Mapped[int] = mapped_column(Integer)
    created_at: Mapped[str] = mapped_column(String(40))
    updated_at: Mapped[str] = mapped_column(String(40))
    started_at: Mapped[str | None] = mapped_column(String(40), nullable=True)
    completed_at: Mapped[str | None] = mapped_column(String(40), nullable=True)
    name: Mapped[str] = mapped_column(String(120), default="Энкаунтер")


class MonsterTemplateRecord(Base):
    __tablename__ = "monster_templates"

    id: Mapped[str] = mapped_column(String(36), primary_key=True)
    room_id: Mapped[str] = mapped_column(ForeignKey("rooms.id"), index=True)
    name: Mapped[str] = mapped_column(String(120))
    image_url: Mapped[str | None] = mapped_column(String(500), nullable=True)
    max_hp: Mapped[int] = mapped_column(Integer)
    current_hp: Mapped[int] = mapped_column(Integer)
    armor_class: Mapped[int] = mapped_column(Integer)
    notes: Mapped[str] = mapped_column(String(2000))
    conditions: Mapped[list[str]] = mapped_column(JSON)
    actions: Mapped[list[str]] = mapped_column(JSON)
    created_at: Mapped[str] = mapped_column(String(40))
    species: Mapped[str] = mapped_column(String(120), default="")
    abilities: Mapped[str] = mapped_column(String(4000), default="")
    damage: Mapped[str] = mapped_column(String(1000), default="")
    items: Mapped[str] = mapped_column(String(4000), default="")


class CombatantRecord(Base):
    __tablename__ = "combatants"

    id: Mapped[str] = mapped_column(String(36), primary_key=True)
    combat_id: Mapped[str] = mapped_column(ForeignKey("combats.id"), index=True)
    entry_id: Mapped[str] = mapped_column(String(36), index=True)
    kind: Mapped[str] = mapped_column(String(20))
    reference_id: Mapped[str | None] = mapped_column(String(36), nullable=True, index=True)
    name: Mapped[str] = mapped_column(String(120))
    max_hp: Mapped[int] = mapped_column(Integer)
    current_hp: Mapped[int] = mapped_column(Integer)
    temporary_hp: Mapped[int] = mapped_column(Integer)
    armor_class: Mapped[int] = mapped_column(Integer)
    conditions: Mapped[list[dict[str, Any]]] = mapped_column(JSON)
    show_wound_state: Mapped[bool] = mapped_column(Boolean)
    wound_override: Mapped[str | None] = mapped_column(String(120), nullable=True)
    version: Mapped[int] = mapped_column(Integer)
    created_at: Mapped[str] = mapped_column(String(40))


class DiceRollRecord(Base):
    __tablename__ = "dice_rolls"

    id: Mapped[str] = mapped_column(String(36), primary_key=True)
    combat_id: Mapped[str | None] = mapped_column(
        ForeignKey("combats.id"), index=True, nullable=True
    )
    room_id: Mapped[str] = mapped_column(ForeignKey("rooms.id"), index=True)
    actor_id: Mapped[str] = mapped_column(String(36))
    character_id: Mapped[str | None] = mapped_column(String(36), nullable=True)
    expression: Mapped[str] = mapped_column(String(32))
    mode: Mapped[str] = mapped_column(String(16))
    visibility: Mapped[str] = mapped_column(String(16))
    recipient_player_id: Mapped[str | None] = mapped_column(String(36), nullable=True)
    values: Mapped[list[int]] = mapped_column(JSON)
    original_result: Mapped[int] = mapped_column(Integer)
    result: Mapped[int] = mapped_column(Integer)
    reason: Mapped[str | None] = mapped_column(String(500), nullable=True)
    action_event_id: Mapped[str | None] = mapped_column(String(36), nullable=True)
    created_at: Mapped[str] = mapped_column(String(40))
    revealed_at: Mapped[str | None] = mapped_column(String(40), nullable=True)
    selection: Mapped[str] = mapped_column(String(16), default="neutral")
    attempts: Mapped[list[list[int]]] = mapped_column(JSON, default=list)
    attempt_totals: Mapped[list[int]] = mapped_column(JSON, default=list)
    selected_attempt: Mapped[int] = mapped_column(Integer, default=0)


class EventCompensationRecord(Base):
    __tablename__ = "event_compensations"

    original_event_id: Mapped[str] = mapped_column(ForeignKey("game_events.id"), primary_key=True)
    compensation_event_id: Mapped[str] = mapped_column(ForeignKey("game_events.id"), unique=True)
    replacement_event_id: Mapped[str | None] = mapped_column(
        ForeignKey("game_events.id"), nullable=True
    )
    created_at: Mapped[str] = mapped_column(String(40))


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
