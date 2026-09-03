"""Add playable combat loop state.

Revision ID: 0003_playable_combat
Revises: 0002_local_multiplayer
Create Date: 2026-09-03
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "0003_playable_combat"
down_revision: str | None = "0002_local_multiplayer"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    with op.batch_alter_table("game_events") as batch:
        batch.alter_column("visibility", existing_type=sa.String(24), type_=sa.String(64))
    op.create_table(
        "combats",
        sa.Column("id", sa.String(36), primary_key=True),
        sa.Column("room_id", sa.String(36), sa.ForeignKey("rooms.id"), nullable=False),
        sa.Column("session_id", sa.String(36), sa.ForeignKey("game_sessions.id"), nullable=False),
        sa.Column("status", sa.String(20), nullable=False),
        sa.Column("round_number", sa.Integer(), nullable=False),
        sa.Column("current_entry_id", sa.String(36), nullable=True),
        sa.Column("entries", sa.JSON(), nullable=False),
        sa.Column("version", sa.Integer(), nullable=False),
        sa.Column("created_at", sa.String(40), nullable=False),
        sa.Column("updated_at", sa.String(40), nullable=False),
        sa.Column("started_at", sa.String(40), nullable=True),
        sa.Column("completed_at", sa.String(40), nullable=True),
    )
    op.create_index("ix_combats_room_id", "combats", ["room_id"])
    op.create_index("ix_combats_session_id", "combats", ["session_id"])
    op.create_index(
        "uq_combats_session_unfinished",
        "combats",
        ["session_id"],
        unique=True,
        sqlite_where=sa.text("status != 'COMPLETED'"),
    )
    op.create_table(
        "monster_templates",
        sa.Column("id", sa.String(36), primary_key=True),
        sa.Column("room_id", sa.String(36), sa.ForeignKey("rooms.id"), nullable=False),
        sa.Column("name", sa.String(120), nullable=False),
        sa.Column("image_url", sa.String(500), nullable=True),
        sa.Column("max_hp", sa.Integer(), nullable=False),
        sa.Column("current_hp", sa.Integer(), nullable=False),
        sa.Column("armor_class", sa.Integer(), nullable=False),
        sa.Column("notes", sa.String(2000), nullable=False),
        sa.Column("actions", sa.JSON(), nullable=False),
        sa.Column("created_at", sa.String(40), nullable=False),
    )
    op.create_index("ix_monster_templates_room_id", "monster_templates", ["room_id"])
    op.create_table(
        "combatants",
        sa.Column("id", sa.String(36), primary_key=True),
        sa.Column("combat_id", sa.String(36), sa.ForeignKey("combats.id"), nullable=False),
        sa.Column("entry_id", sa.String(36), nullable=False),
        sa.Column("kind", sa.String(20), nullable=False),
        sa.Column("reference_id", sa.String(36), nullable=True),
        sa.Column("name", sa.String(120), nullable=False),
        sa.Column("max_hp", sa.Integer(), nullable=False),
        sa.Column("current_hp", sa.Integer(), nullable=False),
        sa.Column("temporary_hp", sa.Integer(), nullable=False),
        sa.Column("armor_class", sa.Integer(), nullable=False),
        sa.Column("conditions", sa.JSON(), nullable=False),
        sa.Column("show_wound_state", sa.Boolean(), nullable=False),
        sa.Column("wound_override", sa.String(120), nullable=True),
        sa.Column("version", sa.Integer(), nullable=False),
        sa.Column("created_at", sa.String(40), nullable=False),
    )
    op.create_index("ix_combatants_combat_id", "combatants", ["combat_id"])
    op.create_index("ix_combatants_entry_id", "combatants", ["entry_id"])
    op.create_index("ix_combatants_reference_id", "combatants", ["reference_id"])
    op.create_table(
        "dice_rolls",
        sa.Column("id", sa.String(36), primary_key=True),
        sa.Column("combat_id", sa.String(36), sa.ForeignKey("combats.id"), nullable=False),
        sa.Column("room_id", sa.String(36), sa.ForeignKey("rooms.id"), nullable=False),
        sa.Column("actor_id", sa.String(36), nullable=False),
        sa.Column("character_id", sa.String(36), nullable=True),
        sa.Column("expression", sa.String(32), nullable=False),
        sa.Column("mode", sa.String(16), nullable=False),
        sa.Column("visibility", sa.String(16), nullable=False),
        sa.Column("recipient_player_id", sa.String(36), nullable=True),
        sa.Column("values", sa.JSON(), nullable=False),
        sa.Column("original_result", sa.Integer(), nullable=False),
        sa.Column("result", sa.Integer(), nullable=False),
        sa.Column("reason", sa.String(500), nullable=True),
        sa.Column("action_event_id", sa.String(36), nullable=True),
        sa.Column("created_at", sa.String(40), nullable=False),
        sa.Column("revealed_at", sa.String(40), nullable=True),
    )
    op.create_index("ix_dice_rolls_combat_id", "dice_rolls", ["combat_id"])
    op.create_index("ix_dice_rolls_room_id", "dice_rolls", ["room_id"])
    op.create_table(
        "event_compensations",
        sa.Column(
            "original_event_id", sa.String(36), sa.ForeignKey("game_events.id"), primary_key=True
        ),
        sa.Column(
            "compensation_event_id",
            sa.String(36),
            sa.ForeignKey("game_events.id"),
            nullable=False,
            unique=True,
        ),
        sa.Column(
            "replacement_event_id", sa.String(36), sa.ForeignKey("game_events.id"), nullable=True
        ),
        sa.Column("created_at", sa.String(40), nullable=False),
    )


def downgrade() -> None:
    op.drop_table("event_compensations")
    op.drop_index("ix_dice_rolls_room_id", table_name="dice_rolls")
    op.drop_index("ix_dice_rolls_combat_id", table_name="dice_rolls")
    op.drop_table("dice_rolls")
    op.drop_index("ix_combatants_reference_id", table_name="combatants")
    op.drop_index("ix_combatants_entry_id", table_name="combatants")
    op.drop_index("ix_combatants_combat_id", table_name="combatants")
    op.drop_table("combatants")
    op.drop_index("ix_monster_templates_room_id", table_name="monster_templates")
    op.drop_table("monster_templates")
    op.drop_index("uq_combats_session_unfinished", table_name="combats")
    op.drop_index("ix_combats_session_id", table_name="combats")
    op.drop_index("ix_combats_room_id", table_name="combats")
    op.drop_table("combats")
    with op.batch_alter_table("game_events") as batch:
        batch.alter_column("visibility", existing_type=sa.String(64), type_=sa.String(24))
