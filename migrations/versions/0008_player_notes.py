"""Add private hierarchical player notes.

Revision ID: 0008_player_notes
Revises: 0007_character_overhaul
Create Date: 2026-09-05
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "0008_player_notes"
down_revision: str | None = "0007_character_overhaul"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "player_note_nodes",
        sa.Column("id", sa.String(36), primary_key=True),
        sa.Column("room_id", sa.String(36), sa.ForeignKey("rooms.id"), nullable=False),
        sa.Column(
            "player_id",
            sa.String(36),
            sa.ForeignKey("local_players.id"),
            nullable=False,
        ),
        sa.Column(
            "parent_id",
            sa.String(36),
            sa.ForeignKey("player_note_nodes.id"),
            nullable=True,
        ),
        sa.Column("kind", sa.String(12), nullable=False),
        sa.Column("name", sa.String(120), nullable=False),
        sa.Column("body", sa.String(50000), nullable=False, server_default=""),
        sa.Column("depth", sa.Integer(), nullable=False),
        sa.Column("version", sa.Integer(), nullable=False),
        sa.Column("created_at", sa.String(40), nullable=False),
        sa.Column("updated_at", sa.String(40), nullable=False),
        sa.CheckConstraint("kind IN ('folder', 'note')", name="ck_player_note_kind"),
        sa.CheckConstraint("depth BETWEEN 0 AND 3", name="ck_player_note_depth"),
    )
    op.create_index(
        "ix_player_note_nodes_owner_parent",
        "player_note_nodes",
        ["player_id", "parent_id"],
    )


def downgrade() -> None:
    op.drop_index("ix_player_note_nodes_owner_parent", table_name="player_note_nodes")
    op.drop_table("player_note_nodes")
