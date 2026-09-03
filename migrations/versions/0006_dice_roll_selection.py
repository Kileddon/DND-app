"""Persist advantage and disadvantage roll attempts.

Revision ID: 0006_dice_roll_selection
Revises: 0005_player_cards_and_gm_notes
Create Date: 2026-09-03
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "0006_dice_roll_selection"
down_revision: str | None = "0005_player_cards_and_gm_notes"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    with op.batch_alter_table("dice_rolls") as batch:
        batch.alter_column("combat_id", existing_type=sa.String(36), nullable=True)
        batch.add_column(
            sa.Column("selection", sa.String(16), nullable=False, server_default="neutral")
        )
        batch.add_column(sa.Column("attempts", sa.JSON(), nullable=False, server_default="[]"))
        batch.add_column(
            sa.Column("attempt_totals", sa.JSON(), nullable=False, server_default="[]")
        )
        batch.add_column(
            sa.Column("selected_attempt", sa.Integer(), nullable=False, server_default="0")
        )


def downgrade() -> None:
    with op.batch_alter_table("dice_rolls") as batch:
        batch.drop_column("selected_attempt")
        batch.drop_column("attempt_totals")
        batch.drop_column("attempts")
        batch.drop_column("selection")
        batch.alter_column("combat_id", existing_type=sa.String(36), nullable=False)
