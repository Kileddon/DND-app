"""Add accounts, Character Creation V2, equipment, and prepared encounters.

Revision ID: 0007_character_overhaul
Revises: 0006_dice_roll_selection
Create Date: 2026-09-03
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "0007_character_overhaul"
down_revision: str | None = "0006_dice_roll_selection"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "accounts",
        sa.Column("id", sa.String(36), primary_key=True),
        sa.Column("display_name", sa.String(80), nullable=False),
        sa.Column("cloud_identity", sa.String(255), nullable=True, unique=True),
        sa.Column("version", sa.Integer(), nullable=False, server_default="1"),
        sa.Column("created_at", sa.String(40), nullable=False),
        sa.Column("updated_at", sa.String(40), nullable=False),
    )
    op.execute(
        """
        INSERT INTO accounts (id, display_name, cloud_identity, version, created_at, updated_at)
        SELECT id, display_name, NULL, 1, created_at, updated_at FROM local_players
        """
    )
    with op.batch_alter_table("local_players") as batch:
        batch.add_column(sa.Column("account_id", sa.String(36), nullable=True))
        batch.create_foreign_key("fk_local_players_account", "accounts", ["account_id"], ["id"])
        batch.create_unique_constraint("uq_membership_account_room", ["account_id", "room_id"])
    op.execute("UPDATE local_players SET account_id = id")

    with op.batch_alter_table("local_devices") as batch:
        batch.add_column(sa.Column("account_id", sa.String(36), nullable=True))
        batch.create_foreign_key("fk_local_devices_account", "accounts", ["account_id"], ["id"])
    op.execute(
        """
        UPDATE local_devices SET account_id = (
            SELECT account_id FROM local_players WHERE local_players.id = local_devices.player_id
        )
        """
    )

    with op.batch_alter_table("characters") as batch:
        batch.add_column(sa.Column("account_id", sa.String(36), nullable=True))
        batch.add_column(sa.Column("archived_at", sa.String(40), nullable=True))
        batch.add_column(sa.Column("level", sa.Integer(), nullable=False, server_default="1"))
        batch.add_column(sa.Column("experience", sa.Integer(), nullable=False, server_default="0"))
        batch.add_column(
            sa.Column("temporary_hp", sa.Integer(), nullable=False, server_default="0")
        )
        batch.add_column(sa.Column("initiative", sa.Integer(), nullable=False, server_default="0"))
        batch.add_column(
            sa.Column("proficiency_bonus", sa.Integer(), nullable=False, server_default="2")
        )
        batch.add_column(sa.Column("size", sa.String(16), nullable=False, server_default="medium"))
        batch.add_column(sa.Column("speed", sa.Integer(), nullable=False, server_default="30"))
        batch.add_column(sa.Column("darkvision", sa.Integer(), nullable=False, server_default="0"))
        batch.add_column(
            sa.Column("species_choices", sa.JSON(), nullable=False, server_default="{}")
        )
        batch.add_column(
            sa.Column("persistent_conditions", sa.JSON(), nullable=False, server_default="[]")
        )
        batch.create_foreign_key("fk_characters_account", "accounts", ["account_id"], ["id"])
    op.execute("UPDATE characters SET account_id = owner_id")

    op.create_table(
        "character_room_assignments",
        sa.Column("character_id", sa.String(36), sa.ForeignKey("characters.id"), primary_key=True),
        sa.Column("room_id", sa.String(36), sa.ForeignKey("rooms.id"), primary_key=True),
        sa.Column("assigned_at", sa.String(40), nullable=False),
    )
    op.execute(
        """
        INSERT INTO character_room_assignments (character_id, room_id, assigned_at)
        SELECT id, room_id, created_at FROM characters
        """
    )

    with op.batch_alter_table("character_drafts") as batch:
        batch.add_column(sa.Column("account_id", sa.String(36), nullable=True))
        batch.add_column(sa.Column("step", sa.String(32), nullable=False, server_default="name"))
        batch.add_column(
            sa.Column("species_choices", sa.JSON(), nullable=False, server_default="{}")
        )
        batch.add_column(sa.Column("stat_method", sa.String(20), nullable=True))
        batch.add_column(sa.Column("base_stats", sa.JSON(), nullable=False, server_default="{}"))
        batch.add_column(sa.Column("background", sa.JSON(), nullable=False, server_default="{}"))
        batch.add_column(sa.Column("random_rolls", sa.JSON(), nullable=False, server_default="[]"))
        batch.create_foreign_key("fk_character_drafts_account", "accounts", ["account_id"], ["id"])
    op.execute("UPDATE character_drafts SET account_id = owner_id")

    with op.batch_alter_table("item_definitions") as batch:
        batch.add_column(
            sa.Column("unit_weight", sa.Numeric(10, 3), nullable=False, server_default="0")
        )
        batch.add_column(
            sa.Column("slot_compatibility", sa.String(16), nullable=False, server_default="none")
        )
    with op.batch_alter_table("inventory_items") as batch:
        batch.add_column(sa.Column("equipment_slot", sa.String(16), nullable=True))
    op.execute("UPDATE inventory_items SET equipment_slot = 'other_1' WHERE equipped = 1")

    op.drop_index("uq_combats_session_unfinished", table_name="combats")
    with op.batch_alter_table("combats") as batch:
        batch.add_column(
            sa.Column("name", sa.String(120), nullable=False, server_default="Энкаунтер")
        )
    op.create_index(
        "uq_combats_room_active",
        "combats",
        ["room_id"],
        unique=True,
        sqlite_where=sa.text("status IN ('ACTIVE', 'PAUSED')"),
    )

    with op.batch_alter_table("monster_templates") as batch:
        batch.add_column(sa.Column("species", sa.String(120), nullable=False, server_default=""))
        batch.add_column(sa.Column("abilities", sa.String(4000), nullable=False, server_default=""))
        batch.add_column(sa.Column("damage", sa.String(1000), nullable=False, server_default=""))
        batch.add_column(sa.Column("items", sa.String(4000), nullable=False, server_default=""))


def downgrade() -> None:
    op.drop_index("uq_combats_room_active", table_name="combats")
    with op.batch_alter_table("monster_templates") as batch:
        for column in ("items", "damage", "abilities", "species"):
            batch.drop_column(column)
    with op.batch_alter_table("combats") as batch:
        batch.drop_column("name")
    op.create_index(
        "uq_combats_session_unfinished",
        "combats",
        ["session_id"],
        unique=True,
        sqlite_where=sa.text("status != 'COMPLETED'"),
    )
    with op.batch_alter_table("inventory_items") as batch:
        batch.drop_column("equipment_slot")
    with op.batch_alter_table("item_definitions") as batch:
        batch.drop_column("slot_compatibility")
        batch.drop_column("unit_weight")
    with op.batch_alter_table("character_drafts") as batch:
        batch.drop_constraint("fk_character_drafts_account", type_="foreignkey")
        for column in (
            "random_rolls",
            "background",
            "base_stats",
            "stat_method",
            "species_choices",
            "step",
            "account_id",
        ):
            batch.drop_column(column)
    op.drop_table("character_room_assignments")
    with op.batch_alter_table("characters") as batch:
        batch.drop_constraint("fk_characters_account", type_="foreignkey")
        for column in (
            "persistent_conditions",
            "species_choices",
            "darkvision",
            "speed",
            "size",
            "proficiency_bonus",
            "initiative",
            "temporary_hp",
            "experience",
            "level",
            "archived_at",
            "account_id",
        ):
            batch.drop_column(column)
    with op.batch_alter_table("local_devices") as batch:
        batch.drop_constraint("fk_local_devices_account", type_="foreignkey")
        batch.drop_column("account_id")
    with op.batch_alter_table("local_players") as batch:
        batch.drop_constraint("uq_membership_account_room", type_="unique")
        batch.drop_constraint("fk_local_players_account", type_="foreignkey")
        batch.drop_column("account_id")
    op.drop_table("accounts")
