"""Add local multiplayer pairing, sessions, devices, and event cursors.

Revision ID: 0002_local_multiplayer
Revises: 0001_initial
Create Date: 2026-09-02
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "0002_local_multiplayer"
down_revision: str | None = "0001_initial"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    with op.batch_alter_table("rooms") as batch:
        batch.add_column(sa.Column("code", sa.String(8), nullable=True))
        batch.add_column(sa.Column("password_hash", sa.String(255), nullable=True))
    op.execute("UPDATE rooms SET code = upper(substr(replace(id, '-', ''), 1, 8))")
    with op.batch_alter_table("rooms") as batch:
        batch.alter_column("code", existing_type=sa.String(8), nullable=False)
        batch.create_index("uq_rooms_code", ["code"], unique=True)

    with op.batch_alter_table("local_players") as batch:
        batch.add_column(sa.Column("recovery_code_digest", sa.String(64), nullable=True))
        batch.add_column(sa.Column("selected_character_id", sa.String(36), nullable=True))
        batch.add_column(sa.Column("updated_at", sa.String(40), nullable=True))
    op.execute("UPDATE local_players SET updated_at = created_at")
    with op.batch_alter_table("local_players") as batch:
        batch.alter_column("updated_at", existing_type=sa.String(40), nullable=False)

    with op.batch_alter_table("game_events") as batch:
        batch.add_column(sa.Column("cursor", sa.Integer(), nullable=True))
        batch.add_column(sa.Column("session_id", sa.String(36), nullable=True))
    op.execute("UPDATE game_events SET cursor = rowid")
    with op.batch_alter_table("game_events") as batch:
        batch.alter_column("cursor", existing_type=sa.Integer(), nullable=False)
        batch.create_index("uq_game_events_cursor", ["cursor"], unique=True)

    op.create_table(
        "event_cursor_sequence",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("last_cursor", sa.Integer(), nullable=False),
        sa.CheckConstraint("id = 1", name="ck_event_cursor_singleton"),
    )
    op.execute(
        "INSERT INTO event_cursor_sequence(id, last_cursor) "
        "SELECT 1, COALESCE(MAX(cursor), 0) FROM game_events"
    )
    op.create_table(
        "pairing_invitations",
        sa.Column("id", sa.String(36), primary_key=True),
        sa.Column("room_id", sa.String(36), sa.ForeignKey("rooms.id"), nullable=False),
        sa.Column("role", sa.String(16), nullable=False),
        sa.Column("token_digest", sa.String(64), nullable=False, unique=True),
        sa.Column("short_code_digest", sa.String(64), nullable=False, unique=True),
        sa.Column("expires_at", sa.String(40), nullable=False),
        sa.Column("created_by", sa.String(36), nullable=False),
        sa.Column("created_at", sa.String(40), nullable=False),
        sa.Column("used_at", sa.String(40), nullable=True),
        sa.Column("revoked_at", sa.String(40), nullable=True),
    )
    op.create_index("ix_pairing_invitations_room_id", "pairing_invitations", ["room_id"])
    op.create_table(
        "room_invitations",
        sa.Column("id", sa.String(36), primary_key=True),
        sa.Column("room_id", sa.String(36), sa.ForeignKey("rooms.id"), nullable=False),
        sa.Column("token_digest", sa.String(64), nullable=False, unique=True),
        sa.Column("expires_at", sa.String(40), nullable=False),
        sa.Column("max_uses", sa.Integer(), nullable=False),
        sa.Column("use_count", sa.Integer(), nullable=False),
        sa.Column("created_at", sa.String(40), nullable=False),
        sa.Column("revoked_at", sa.String(40), nullable=True),
    )
    op.create_index("ix_room_invitations_room_id", "room_invitations", ["room_id"])
    op.create_table(
        "local_devices",
        sa.Column("id", sa.String(36), primary_key=True),
        sa.Column("room_id", sa.String(36), sa.ForeignKey("rooms.id"), nullable=False),
        sa.Column("player_id", sa.String(36), sa.ForeignKey("local_players.id"), nullable=True),
        sa.Column("label", sa.String(120), nullable=False),
        sa.Column("role", sa.String(16), nullable=False),
        sa.Column("credential_digest", sa.String(64), nullable=False, unique=True),
        sa.Column("status", sa.String(16), nullable=False),
        sa.Column("created_at", sa.String(40), nullable=False),
        sa.Column("last_seen_at", sa.String(40), nullable=False),
        sa.Column("expires_at", sa.String(40), nullable=False),
        sa.Column("revoked_at", sa.String(40), nullable=True),
    )
    op.create_index("ix_local_devices_room_id", "local_devices", ["room_id"])
    op.create_index("ix_local_devices_player_id", "local_devices", ["player_id"])
    op.create_table(
        "game_sessions",
        sa.Column("id", sa.String(36), primary_key=True),
        sa.Column("room_id", sa.String(36), sa.ForeignKey("rooms.id"), nullable=False),
        sa.Column("status", sa.String(20), nullable=False),
        sa.Column("version", sa.Integer(), nullable=False),
        sa.Column("created_at", sa.String(40), nullable=False),
        sa.Column("updated_at", sa.String(40), nullable=False),
        sa.Column("started_at", sa.String(40), nullable=True),
        sa.Column("paused_at", sa.String(40), nullable=True),
        sa.Column("completed_at", sa.String(40), nullable=True),
    )
    op.create_index("ix_game_sessions_room_id", "game_sessions", ["room_id"])
    op.create_index(
        "uq_game_sessions_room_unfinished",
        "game_sessions",
        ["room_id"],
        unique=True,
        sqlite_where=sa.text("status != 'COMPLETED'"),
    )


def downgrade() -> None:
    op.drop_index("uq_game_sessions_room_unfinished", table_name="game_sessions")
    op.drop_index("ix_game_sessions_room_id", table_name="game_sessions")
    op.drop_table("game_sessions")
    op.drop_index("ix_local_devices_player_id", table_name="local_devices")
    op.drop_index("ix_local_devices_room_id", table_name="local_devices")
    op.drop_table("local_devices")
    op.drop_index("ix_room_invitations_room_id", table_name="room_invitations")
    op.drop_table("room_invitations")
    op.drop_index("ix_pairing_invitations_room_id", table_name="pairing_invitations")
    op.drop_table("pairing_invitations")
    op.drop_table("event_cursor_sequence")
    with op.batch_alter_table("game_events") as batch:
        batch.drop_index("uq_game_events_cursor")
        batch.drop_column("session_id")
        batch.drop_column("cursor")
    with op.batch_alter_table("local_players") as batch:
        batch.drop_column("updated_at")
        batch.drop_column("selected_character_id")
        batch.drop_column("recovery_code_digest")
    with op.batch_alter_table("rooms") as batch:
        batch.drop_index("uq_rooms_code")
        batch.drop_column("password_hash")
        batch.drop_column("code")
