"""Add initial conditions to monster templates.

Revision ID: 0004_monster_template_conditions
Revises: 0003_playable_combat
Create Date: 2026-09-03
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "0004_monster_template_conditions"
down_revision: str | None = "0003_playable_combat"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    with op.batch_alter_table("monster_templates") as batch:
        batch.add_column(sa.Column("conditions", sa.JSON(), nullable=False, server_default="[]"))


def downgrade() -> None:
    with op.batch_alter_table("monster_templates") as batch:
        batch.drop_column("conditions")
