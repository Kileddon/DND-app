from __future__ import annotations

import sqlite3
from datetime import UTC, datetime
from pathlib import Path

from alembic import command
from alembic.config import Config
from alembic.migration import MigrationContext
from alembic.script import ScriptDirectory
from sqlalchemy import create_engine
from sqlalchemy.engine import make_url

from tabletop_companion.infrastructure.database import ensure_sqlite_directory


def _alembic_config(database_url: str) -> Config:
    project_root = Path(__file__).resolve().parents[3]
    config = Config(str(project_root / "alembic.ini"))
    config.attributes["skip_logging_config"] = True
    config.set_main_option("script_location", str(project_root / "migrations"))
    config.set_main_option("sqlalchemy.url", database_url.replace("%", "%%"))
    return config


def _sqlite_path(database_url: str) -> Path | None:
    url = make_url(database_url)
    if not url.drivername.startswith("sqlite") or not url.database or url.database == ":memory:":
        return None
    return Path(url.database).expanduser().resolve()


def _current_revision(database_url: str) -> str | None:
    engine = create_engine(database_url)
    try:
        with engine.connect() as connection:
            return MigrationContext.configure(connection).get_current_revision()
    finally:
        engine.dispose()


def run_migrations(database_url: str, target: str = "head") -> Path | None:
    """Upgrade to head and back up a non-empty SQLite database before a real upgrade."""

    ensure_sqlite_directory(database_url)
    config = _alembic_config(database_url)
    database_path = _sqlite_path(database_url)
    current_revision = _current_revision(database_url)
    script = ScriptDirectory.from_config(config)
    target_revision = (
        script.get_current_head() if target == "head" else script.get_revision(target).revision
    )
    backup_path: Path | None = None

    if (
        database_path is not None
        and database_path.exists()
        and database_path.stat().st_size > 0
        and current_revision != target_revision
    ):
        timestamp = datetime.now(UTC).strftime("%Y%m%dT%H%M%SZ")
        backup_path = database_path.with_name(f"{database_path.name}.backup.{timestamp}.sqlite3")
        with (
            sqlite3.connect(database_path) as source,
            sqlite3.connect(backup_path) as backup,
        ):
            source.backup(backup)

    command.upgrade(config, target)
    return backup_path


def restore_sqlite_backup(backup_path: Path, database_url: str) -> None:
    destination = _sqlite_path(database_url)
    if destination is None:
        raise ValueError("Backup restore requires a file-backed SQLite database.")
    if not backup_path.is_file():
        raise FileNotFoundError(backup_path)
    ensure_sqlite_directory(database_url)
    with sqlite3.connect(backup_path) as source, sqlite3.connect(destination) as target:
        source.backup(target)
