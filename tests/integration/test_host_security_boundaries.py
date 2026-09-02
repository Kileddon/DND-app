from __future__ import annotations

from pathlib import Path
from unittest.mock import patch
from uuid import uuid4

from fastapi.testclient import TestClient

from tabletop_companion.api.app import create_app
from tabletop_companion.config import Settings
from tests.integration.conftest import first_cards
from tests.integration.test_local_multiplayer_api import body, bootstrap, command


def settings(database_url: str, tmp_path: Path) -> Settings:
    return Settings(
        database_url=database_url,
        log_level="WARNING",
        host_secret_path=tmp_path / "host-secret.key",
        frontend_dist=tmp_path / "missing-frontend",
    )


def test_legacy_api_is_rejected_for_lan_client(database_url: str, tmp_path: Path) -> None:
    app = create_app(settings(database_url, tmp_path), sampler=first_cards)
    with TestClient(app, client=("192.168.1.25", 50000)) as client:
        response = client.get(f"/api/v1/rooms/{uuid4()}")

    assert response.status_code == 403
    assert response.json()["error"]["code"] == "permission_denied"


def test_loopback_qr_uses_lan_address_and_diagnostics_are_allowlisted(
    database_url: str, tmp_path: Path
) -> None:
    app = create_app(settings(database_url, tmp_path), sampler=first_cards)
    with (
        patch(
            "tabletop_companion.api.local_routes.local_addresses",
            return_value=["192.168.1.50", "127.0.0.1"],
        ),
        TestClient(app, base_url="http://127.0.0.1:8000") as client,
    ):
        room, gm_device_id, gm_credential = bootstrap(client)
        pairing = body(
            client.post(
                f"/api/v2/rooms/{room['id']}/pairing",
                headers={"Authorization": f"Bearer {gm_credential}"},
                json=command(gm_device_id, ttl_seconds=300),
            ),
            201,
        )["data"]
        assert pairing["pair_url"].startswith("http://192.168.1.50:8000/#/pair/")

        app.state.safe_errors.record("infrastructure_failure")
        report = body(
            client.get(
                "/api/v2/host/diagnostics",
                headers={"Authorization": f"Bearer {gm_credential}"},
            )
        )
        assert report["last_errors"][0]["code"] == "infrastructure_failure"
        assert set(report["last_errors"][0]) == {"occurred_at", "code"}
        serialized = str(report)
        assert "credential" not in serialized
        assert "password" not in serialized
        assert "token" not in serialized
