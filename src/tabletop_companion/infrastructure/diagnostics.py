from __future__ import annotations

import shutil
import socket
import sqlite3
from pathlib import Path

from alembic.migration import MigrationContext
from sqlalchemy import create_engine
from sqlalchemy.engine import make_url


def local_addresses() -> list[str]:
    addresses = {"127.0.0.1"}
    try:
        for result in socket.getaddrinfo(socket.gethostname(), None, socket.AF_INET):
            addresses.add(str(result[4][0]))
    except OSError:
        pass
    return sorted(addresses, key=lambda value: (value.startswith("127."), value))


def database_diagnostics(database_url: str) -> dict[str, int | str]:
    url = make_url(database_url)
    if not url.drivername.startswith("sqlite") or not url.database:
        raise ValueError("Diagnostics require file-backed SQLite.")
    path = Path(url.database).expanduser().resolve()
    journal_mode = "unknown"
    if path.exists():
        with sqlite3.connect(path) as connection:
            value = connection.execute("PRAGMA journal_mode").fetchone()
            journal_mode = str(value[0]) if value else "unknown"
    engine = create_engine(database_url)
    try:
        with engine.connect() as connection:
            revision = MigrationContext.configure(connection).get_current_revision() or "none"
    finally:
        engine.dispose()
    return {
        "sqlite_bytes": path.stat().st_size if path.exists() else 0,
        "sqlite_journal_mode": journal_mode,
        "free_disk_bytes": shutil.disk_usage(path.parent).free,
        "database_revision": revision,
    }
