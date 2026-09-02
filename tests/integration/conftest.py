from __future__ import annotations

from collections.abc import Iterator, Sequence
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from tabletop_companion.api.app import create_app
from tabletop_companion.config import Settings


def first_cards(population: Sequence[str], count: int) -> Sequence[str]:
    return list(population)[:count]


@pytest.fixture
def database_url(tmp_path: Path) -> str:
    return f"sqlite:///{(tmp_path / 'tabletop.sqlite3').as_posix()}"


@pytest.fixture
def client(database_url: str) -> Iterator[TestClient]:
    app = create_app(Settings(database_url=database_url, log_level="WARNING"), sampler=first_cards)
    with TestClient(app) as test_client:
        yield test_client
