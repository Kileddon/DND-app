"""Add character identity, lobby removal, and GM notes.

Revision ID: 0005_player_cards_and_gm_notes
Revises: 0004_monster_template_conditions
Create Date: 2026-09-03
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "0005_player_cards_and_gm_notes"
down_revision: str | None = "0004_monster_template_conditions"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    with op.batch_alter_table("local_players") as batch:
        batch.add_column(sa.Column("removed_at", sa.String(40), nullable=True))
        batch.drop_column("recovery_code_digest")
    with op.batch_alter_table("character_drafts") as batch:
        batch.add_column(
            sa.Column("race_id", sa.String(40), nullable=False, server_default="human")
        )
        batch.add_column(
            sa.Column("class_id", sa.String(40), nullable=False, server_default="fighter")
        )
    with op.batch_alter_table("characters") as batch:
        batch.add_column(
            sa.Column("race_id", sa.String(40), nullable=False, server_default="human")
        )
        batch.add_column(
            sa.Column("class_id", sa.String(40), nullable=False, server_default="fighter")
        )
        batch.add_column(sa.Column("max_hp", sa.Integer(), nullable=False, server_default="10"))
        batch.add_column(sa.Column("current_hp", sa.Integer(), nullable=False, server_default="10"))
        batch.add_column(
            sa.Column("armor_class", sa.Integer(), nullable=False, server_default="10")
        )
    op.create_table(
        "gm_notes",
        sa.Column("room_id", sa.String(36), sa.ForeignKey("rooms.id"), primary_key=True),
        sa.Column("campaign", sa.String(20000), nullable=False, server_default=""),
        sa.Column("other", sa.String(20000), nullable=False, server_default=""),
        sa.Column("version", sa.Integer(), nullable=False),
        sa.Column("updated_at", sa.String(40), nullable=False),
    )
    op.create_table(
        "npc_notes",
        sa.Column("id", sa.String(36), primary_key=True),
        sa.Column("room_id", sa.String(36), sa.ForeignKey("rooms.id"), nullable=False),
        sa.Column("name", sa.String(120), nullable=False),
        sa.Column("details", sa.String(20000), nullable=False, server_default=""),
        sa.Column("version", sa.Integer(), nullable=False),
        sa.Column("created_at", sa.String(40), nullable=False),
        sa.Column("updated_at", sa.String(40), nullable=False),
    )
    op.create_index("ix_npc_notes_room_id", "npc_notes", ["room_id"])


def downgrade() -> None:
    op.drop_index("ix_npc_notes_room_id", table_name="npc_notes")
    op.drop_table("npc_notes")
    op.drop_table("gm_notes")
    with op.batch_alter_table("characters") as batch:
        batch.drop_column("armor_class")
        batch.drop_column("current_hp")
        batch.drop_column("max_hp")
        batch.drop_column("class_id")
        batch.drop_column("race_id")
    with op.batch_alter_table("character_drafts") as batch:
        batch.drop_column("class_id")
        batch.drop_column("race_id")
    with op.batch_alter_table("local_players") as batch:
        batch.add_column(sa.Column("recovery_code_digest", sa.String(64), nullable=True))
        batch.drop_column("removed_at")
