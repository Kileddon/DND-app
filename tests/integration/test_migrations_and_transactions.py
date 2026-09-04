from __future__ import annotations

from dataclasses import replace
from datetime import UTC, datetime
from pathlib import Path
from uuid import uuid4

import pytest
from alembic.migration import MigrationContext
from sqlalchemy import func, inspect, select

from tabletop_companion.application.commands import CreateRoomCommand
from tabletop_companion.application.service import CompanionService
from tabletop_companion.domain.errors import StateConflictError
from tabletop_companion.domain.events import DomainEvent
from tabletop_companion.domain.models import AccessMode, LocalPlayer, Room
from tabletop_companion.domain.rules import DEFAULT_RULESET
from tabletop_companion.infrastructure.database import (
    create_database_engine,
    create_session_factory,
)
from tabletop_companion.infrastructure.migrations import restore_sqlite_backup, run_migrations
from tabletop_companion.infrastructure.tables import GameEventRecord, RoomRecord
from tabletop_companion.infrastructure.uow import SqlAlchemyUnitOfWorkFactory
from tests.integration.conftest import first_cards


def test_migrations_apply_to_empty_database(database_url: str) -> None:
    run_migrations(database_url)
    engine = create_database_engine(database_url)
    try:
        table_names = set(inspect(engine).get_table_names())
        assert {
            "alembic_version",
            "rooms",
            "local_players",
            "character_drafts",
            "characters",
            "item_definitions",
            "inventory_items",
            "game_events",
            "processed_commands",
            "local_devices",
            "pairing_invitations",
            "room_invitations",
            "game_sessions",
            "event_cursor_sequence",
            "combats",
            "combatants",
            "monster_templates",
            "dice_rolls",
            "event_compensations",
            "gm_notes",
            "npc_notes",
        } <= table_names
        with engine.connect() as connection:
            assert (
                MigrationContext.configure(connection).get_current_revision()
                == "0007_character_overhaul"
            )
    finally:
        engine.dispose()


def test_state_event_and_command_result_commit_together(database_url: str) -> None:
    run_migrations(database_url)
    engine = create_database_engine(database_url)
    session_factory = create_session_factory(engine)
    service = CompanionService(
        uow_factory=SqlAlchemyUnitOfWorkFactory(session_factory),
        rulesets={DEFAULT_RULESET.version: DEFAULT_RULESET},
        sampler=first_cards,
    )
    command_id = str(uuid4())

    service.create_room(
        CreateRoomCommand(
            command_id=command_id,
            device_id="gm-laptop",
            client_time=None,
            gm_id=str(uuid4()),
            name="The Amber Road",
            access_mode=AccessMode.OPEN,
        )
    )

    with session_factory() as session:
        assert session.scalar(select(func.count()).select_from(RoomRecord)) == 1
        assert session.scalar(select(func.count()).select_from(GameEventRecord)) == 1
        event = session.scalar(select(GameEventRecord))
        assert event is not None
        assert event.command_id == command_id
    engine.dispose()


def test_rollback_leaves_no_partial_state(database_url: str) -> None:
    run_migrations(database_url)
    engine = create_database_engine(database_url)
    session_factory = create_session_factory(engine)
    factory = SqlAlchemyUnitOfWorkFactory(session_factory)
    room_id = str(uuid4())
    command_id = str(uuid4())
    now = datetime.now(UTC)

    with pytest.raises(RuntimeError, match="forced rollback"), factory() as uow:
        uow.add_room(
            Room(
                id=room_id,
                name="Rollback Room",
                gm_id=str(uuid4()),
                access_mode=AccessMode.OPEN,
                ruleset_version=DEFAULT_RULESET.version,
                version=1,
                created_at=now,
            )
        )
        uow.add_event(
            DomainEvent(
                id=str(uuid4()),
                event_type="RoomCreated",
                aggregate_type="room",
                aggregate_id=room_id,
                room_id=room_id,
                actor_id=str(uuid4()),
                source_id=None,
                target_ids=(room_id,),
                payload={},
                visibility="room",
                schema_version=1,
                command_id=command_id,
                occurred_at=now,
            )
        )
        raise RuntimeError("forced rollback")

    with session_factory() as session:
        assert session.scalar(select(func.count()).select_from(RoomRecord)) == 0
        assert session.scalar(select(func.count()).select_from(GameEventRecord)) == 0
    engine.dispose()


def test_existing_unversioned_database_is_backed_up_before_migration(
    database_url: str, tmp_path: Path
) -> None:
    engine = create_database_engine(database_url)
    with engine.begin() as connection:
        connection.exec_driver_sql("CREATE TABLE legacy_data (value TEXT NOT NULL)")
        connection.exec_driver_sql("INSERT INTO legacy_data(value) VALUES ('keep me')")
    engine.dispose()

    backup_path = run_migrations(database_url)

    assert backup_path is not None
    assert backup_path.exists()
    assert backup_path.parent == tmp_path


def test_previous_revision_upgrades_and_wal_backup_restores(
    database_url: str, tmp_path: Path
) -> None:
    run_migrations(database_url, "0001_initial")
    engine = create_database_engine(database_url)
    with engine.begin() as connection:
        connection.exec_driver_sql(
            "INSERT INTO rooms(id, name, gm_id, access_mode, ruleset_version, version, created_at) "
            "VALUES (?, ?, ?, ?, ?, ?, ?)",
            (
                str(uuid4()),
                "Migrated room",
                str(uuid4()),
                "open",
                DEFAULT_RULESET.version,
                1,
                datetime.now(UTC).isoformat(),
            ),
        )
    engine.dispose()

    backup_path = run_migrations(database_url)

    assert backup_path is not None
    upgraded = create_database_engine(database_url)
    with upgraded.connect() as connection:
        assert connection.exec_driver_sql("SELECT name FROM rooms").scalar_one() == "Migrated room"
        assert connection.exec_driver_sql("PRAGMA journal_mode").scalar_one().lower() == "wal"
    upgraded.dispose()

    restored_url = f"sqlite:///{(tmp_path / 'restored.sqlite3').as_posix()}"
    restore_sqlite_backup(backup_path, restored_url)
    run_migrations(restored_url)
    restored = create_database_engine(restored_url)
    with restored.connect() as connection:
        assert connection.exec_driver_sql("SELECT name FROM rooms").scalar_one() == "Migrated room"
    restored.dispose()


def test_character_overhaul_backfills_accounts_and_room_assignments(
    database_url: str,
) -> None:
    run_migrations(database_url, "0006_dice_roll_selection")
    engine = create_database_engine(database_url)
    room_id, player_id, character_id = (str(uuid4()) for _ in range(3))
    now = datetime.now(UTC).isoformat()
    with engine.begin() as connection:
        connection.exec_driver_sql(
            "INSERT INTO rooms "
            "(id, name, gm_id, access_mode, ruleset_version, version, created_at, code) "
            "VALUES (?, ?, ?, ?, ?, ?, ?, ?)",
            (room_id, "Legacy", str(uuid4()), "open", "simple-v1", 1, now, "LEGACY01"),
        )
        connection.exec_driver_sql(
            "INSERT INTO local_players "
            "(id, room_id, display_name, version, created_at, selected_character_id, "
            "updated_at, removed_at) VALUES (?, ?, ?, ?, ?, ?, ?, ?)",
            (player_id, room_id, "Legacy player", 1, now, character_id, now, None),
        )
        connection.exec_driver_sql(
            "INSERT INTO characters "
            "(id, draft_id, room_id, owner_id, name, ruleset_version, stats, ability_ids, "
            "version, created_at, race_id, class_id, max_hp, current_hp, armor_class) "
            "VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)",
            (
                character_id,
                str(uuid4()),
                room_id,
                player_id,
                "Legacy hero",
                "simple-v1",
                '{"might": 2, "mind": 3}',
                "[]",
                1,
                now,
                "human",
                "fighter",
                10,
                10,
                10,
            ),
        )
    engine.dispose()

    run_migrations(database_url)

    upgraded = create_database_engine(database_url)
    with upgraded.connect() as connection:
        account = connection.exec_driver_sql(
            "SELECT id, display_name FROM accounts WHERE id = ?", (player_id,)
        ).one()
        assignment = connection.exec_driver_sql(
            "SELECT room_id FROM character_room_assignments WHERE character_id = ?",
            (character_id,),
        ).scalar_one()
        character_account = connection.exec_driver_sql(
            "SELECT account_id FROM characters WHERE id = ?", (character_id,)
        ).scalar_one()
    upgraded.dispose()
    assert account == (player_id, "Legacy player")
    assert assignment == room_id
    assert character_account == player_id


def test_optimistic_locking_rejects_concurrent_profile_update(database_url: str) -> None:
    run_migrations(database_url)
    engine = create_database_engine(database_url)
    factory = SqlAlchemyUnitOfWorkFactory(create_session_factory(engine))
    now = datetime.now(UTC)
    room_id = str(uuid4())
    player_id = str(uuid4())
    with factory() as setup:
        setup.add_room(
            Room(
                id=room_id,
                name="Concurrency",
                gm_id=str(uuid4()),
                access_mode=AccessMode.OPEN,
                ruleset_version=DEFAULT_RULESET.version,
                version=1,
                created_at=now,
                code="LOCK01",
            )
        )
        setup.add_local_player(
            LocalPlayer(
                id=player_id,
                room_id=room_id,
                display_name="Original",
                version=1,
                created_at=now,
                updated_at=now,
            )
        )
        setup.commit()

    with factory() as first, factory() as second:
        first_value = first.get_local_player(player_id)
        second_value = second.get_local_player(player_id)
        first.save_local_player(
            replace(first_value, display_name="First", version=2, updated_at=now)
        )
        first.commit()
        with pytest.raises(StateConflictError):
            second.save_local_player(
                replace(second_value, display_name="Second", version=2, updated_at=now)
            )
    engine.dispose()
