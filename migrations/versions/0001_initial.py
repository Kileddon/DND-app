"""Create local-first vertical slice tables.

Revision ID: 0001_initial
Revises:
Create Date: 2026-09-02
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "0001_initial"
down_revision: str | None = None
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "rooms",
        sa.Column("id", sa.String(36), primary_key=True),
        sa.Column("name", sa.String(120), nullable=False),
        sa.Column("gm_id", sa.String(36), nullable=False),
        sa.Column("access_mode", sa.String(24), nullable=False),
        sa.Column("ruleset_version", sa.String(64), nullable=False),
        sa.Column("version", sa.Integer(), nullable=False),
        sa.Column("created_at", sa.String(40), nullable=False),
    )
    op.create_table(
        "local_players",
        sa.Column("id", sa.String(36), primary_key=True),
        sa.Column("room_id", sa.String(36), sa.ForeignKey("rooms.id"), nullable=False),
        sa.Column("display_name", sa.String(80), nullable=False),
        sa.Column("version", sa.Integer(), nullable=False),
        sa.Column("created_at", sa.String(40), nullable=False),
    )
    op.create_index("ix_local_players_room_id", "local_players", ["room_id"])
    op.create_table(
        "character_drafts",
        sa.Column("id", sa.String(36), primary_key=True),
        sa.Column("room_id", sa.String(36), sa.ForeignKey("rooms.id"), nullable=False),
        sa.Column("owner_id", sa.String(36), sa.ForeignKey("local_players.id"), nullable=False),
        sa.Column("name", sa.String(80), nullable=False),
        sa.Column("ruleset_version", sa.String(64), nullable=False),
        sa.Column("stats", sa.JSON(), nullable=False),
        sa.Column("offered_card_ids", sa.JSON(), nullable=False),
        sa.Column("chosen_card_ids", sa.JSON(), nullable=False),
        sa.Column("generation", sa.Integer(), nullable=False),
        sa.Column("status", sa.String(24), nullable=False),
        sa.Column("version", sa.Integer(), nullable=False),
        sa.Column("created_at", sa.String(40), nullable=False),
        sa.Column("updated_at", sa.String(40), nullable=False),
    )
    op.create_index("ix_character_drafts_owner_id", "character_drafts", ["owner_id"])
    op.create_table(
        "characters",
        sa.Column("id", sa.String(36), primary_key=True),
        sa.Column("draft_id", sa.String(36), nullable=False, unique=True),
        sa.Column("room_id", sa.String(36), sa.ForeignKey("rooms.id"), nullable=False),
        sa.Column("owner_id", sa.String(36), sa.ForeignKey("local_players.id"), nullable=False),
        sa.Column("name", sa.String(80), nullable=False),
        sa.Column("ruleset_version", sa.String(64), nullable=False),
        sa.Column("stats", sa.JSON(), nullable=False),
        sa.Column("ability_ids", sa.JSON(), nullable=False),
        sa.Column("version", sa.Integer(), nullable=False),
        sa.Column("created_at", sa.String(40), nullable=False),
    )
    op.create_index("ix_characters_owner_id", "characters", ["owner_id"])
    op.create_table(
        "item_definitions",
        sa.Column("id", sa.String(36), primary_key=True),
        sa.Column("name", sa.String(120), nullable=False),
        sa.Column("consumable", sa.Boolean(), nullable=False),
        sa.Column("locked", sa.Boolean(), nullable=False),
    )
    op.create_table(
        "inventory_items",
        sa.Column("id", sa.String(36), primary_key=True),
        sa.Column(
            "definition_id",
            sa.String(36),
            sa.ForeignKey("item_definitions.id"),
            nullable=False,
        ),
        sa.Column("character_id", sa.String(36), sa.ForeignKey("characters.id"), nullable=False),
        sa.Column("quantity", sa.Integer(), nullable=False),
        sa.Column("equipped", sa.Boolean(), nullable=False),
        sa.Column("charges", sa.Integer(), nullable=True),
        sa.Column("created_at", sa.String(40), nullable=False),
        sa.CheckConstraint("quantity > 0", name="ck_inventory_items_positive_quantity"),
    )
    op.create_index("ix_inventory_items_character_id", "inventory_items", ["character_id"])
    op.create_table(
        "game_events",
        sa.Column("id", sa.String(36), primary_key=True),
        sa.Column("event_type", sa.String(80), nullable=False),
        sa.Column("aggregate_type", sa.String(40), nullable=False),
        sa.Column("aggregate_id", sa.String(36), nullable=False),
        sa.Column("room_id", sa.String(36), sa.ForeignKey("rooms.id"), nullable=False),
        sa.Column("actor_id", sa.String(36), nullable=False),
        sa.Column("source_id", sa.String(36), nullable=True),
        sa.Column("target_ids", sa.JSON(), nullable=False),
        sa.Column("payload", sa.JSON(), nullable=False),
        sa.Column("visibility", sa.String(24), nullable=False),
        sa.Column("schema_version", sa.Integer(), nullable=False),
        sa.Column("command_id", sa.String(36), nullable=False),
        sa.Column("occurred_at", sa.String(40), nullable=False),
    )
    op.create_index("ix_game_events_room_id", "game_events", ["room_id"])
    op.create_index("ix_game_events_aggregate", "game_events", ["aggregate_type", "aggregate_id"])
    op.create_index("ix_game_events_command_id", "game_events", ["command_id"])
    op.create_table(
        "processed_commands",
        sa.Column("command_id", sa.String(36), primary_key=True),
        sa.Column("command_type", sa.String(80), nullable=False),
        sa.Column("payload_hash", sa.String(64), nullable=False),
        sa.Column("actor_id", sa.String(36), nullable=False),
        sa.Column("device_id", sa.String(120), nullable=False),
        sa.Column("client_time", sa.String(40), nullable=True),
        sa.Column("host_time", sa.String(40), nullable=False),
        sa.Column("result", sa.JSON(), nullable=False),
    )


def downgrade() -> None:
    op.drop_table("processed_commands")
    op.drop_index("ix_game_events_command_id", table_name="game_events")
    op.drop_index("ix_game_events_aggregate", table_name="game_events")
    op.drop_index("ix_game_events_room_id", table_name="game_events")
    op.drop_table("game_events")
    op.drop_index("ix_inventory_items_character_id", table_name="inventory_items")
    op.drop_table("inventory_items")
    op.drop_table("item_definitions")
    op.drop_index("ix_characters_owner_id", table_name="characters")
    op.drop_table("characters")
    op.drop_index("ix_character_drafts_owner_id", table_name="character_drafts")
    op.drop_table("character_drafts")
    op.drop_index("ix_local_players_room_id", table_name="local_players")
    op.drop_table("local_players")
    op.drop_table("rooms")
