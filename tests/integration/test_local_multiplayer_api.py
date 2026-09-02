from __future__ import annotations

from pathlib import Path
from typing import Any, cast
from uuid import uuid4

import pytest
from fastapi.testclient import TestClient
from starlette.websockets import WebSocketDisconnect

from tabletop_companion.api.app import create_app
from tabletop_companion.api.local_routes import DEVICE_COOKIE
from tabletop_companion.config import Settings
from tests.integration.conftest import first_cards


def command(device_id: str, **extra: object) -> dict[str, object]:
    return {"command_id": str(uuid4()), "device_id": device_id, **extra}


def body(response: Any, expected: int = 200) -> dict[str, Any]:
    assert response.status_code == expected, response.text
    return cast(dict[str, Any], response.json())


def settings(database_url: str, tmp_path: Path) -> Settings:
    return Settings(
        database_url=database_url,
        log_level="WARNING",
        host_secret_path=tmp_path / "host-secret.key",
        frontend_dist=tmp_path / "missing-frontend",
    )


def bootstrap(
    client: TestClient,
    *,
    access_mode: str = "open",
    password: str | None = None,
) -> tuple[dict[str, Any], str, str]:
    response = client.post(
        "/api/v2/host/rooms",
        json=command(
            "host-installation",
            gm_id=str(uuid4()),
            name=f"{access_mode.title()} room",
            access_mode=access_mode,
            password=password,
            device_label="GM laptop",
        ),
    )
    data = body(response, 201)["data"]
    credential = client.cookies.get(DEVICE_COOKIE)
    assert credential is not None
    return data["room"], data["device"]["id"], credential


def pair_device(
    client: TestClient,
    room_id: str,
    gm_device_id: str,
    gm_credential: str,
    *,
    label: str = "Player phone",
) -> tuple[dict[str, Any], str]:
    pairing = body(
        client.post(
            f"/api/v2/rooms/{room_id}/pairing",
            headers={"Authorization": f"Bearer {gm_credential}"},
            json=command(gm_device_id, ttl_seconds=300),
        ),
        201,
    )["data"]
    assert pairing["pair_url"].split("#", 1)[1].startswith("/pair/")
    assert pairing["qr_data_url"].startswith("data:image/png;base64,")
    token = pairing["pair_url"].rsplit("/", 1)[1]
    exchange = body(
        client.post(
            "/api/v2/pairing/exchange",
            json=command(
                "player-installation",
                token=token,
                short_code=None,
                device_label=label,
            ),
        ),
        201,
    )["data"]
    credential = client.cookies.get(DEVICE_COOKIE)
    assert credential is not None
    return exchange["device"], credential


def create_profile(
    client: TestClient,
    device_id: str,
    credential: str,
    **access: object,
) -> dict[str, Any]:
    result = body(
        client.post(
            "/api/v2/me/profile",
            headers={"Authorization": f"Bearer {credential}"},
            json=command(device_id, display_name="Mira", **access),
        ),
        201,
    )["data"]
    return cast(dict[str, Any], result)


def test_pairing_profile_recovery_snapshot_and_session_restart(
    database_url: str, tmp_path: Path
) -> None:
    app_settings = settings(database_url, tmp_path)
    with TestClient(create_app(app_settings, sampler=first_cards)) as client:
        room, gm_id, gm_credential = bootstrap(client)
        first_device, first_credential = pair_device(client, room["id"], gm_id, gm_credential)
        profile_result = create_profile(client, first_device["id"], first_credential)
        player = profile_result["player"]
        recovery_code = profile_result["recovery_code"]

        second_device, second_credential = pair_device(
            client,
            room["id"],
            gm_id,
            gm_credential,
            label="Player tablet",
        )
        recovered = body(
            client.post(
                "/api/v2/me/profile/recover",
                headers={"Authorization": f"Bearer {second_credential}"},
                json=command(
                    second_device["id"],
                    player_id=player["id"],
                    recovery_code=recovery_code,
                ),
            )
        )["data"]
        assert recovered["player"]["id"] == player["id"]

        session = body(
            client.post(
                f"/api/v2/rooms/{room['id']}/sessions",
                headers={"Authorization": f"Bearer {gm_credential}"},
                json=command(gm_id),
            ),
            201,
        )["data"]
        for target in ["LOBBY", "ACTIVE", "PAUSED", "ACTIVE", "COMPLETED"]:
            session = body(
                client.post(
                    f"/api/v2/rooms/{room['id']}/sessions/{session['id']}/transition",
                    headers={"Authorization": f"Bearer {gm_credential}"},
                    json=command(
                        gm_id,
                        target_status=target,
                        expected_version=session["version"],
                    ),
                )
            )["data"]
        assert session["status"] == "COMPLETED"

        snapshot = body(
            client.get(
                "/api/v2/me/snapshot",
                headers={"Authorization": f"Bearer {second_credential}"},
            )
        )
        serialized = str(snapshot)
        assert "credential_digest" not in serialized
        assert "recovery_code_digest" not in serialized
        assert "password_hash" not in serialized
        assert snapshot["player"]["id"] == player["id"]
        assert len(snapshot["devices"]) == 2

        refreshed = client.post(
            "/api/v2/me/credential/refresh",
            headers={"Authorization": f"Bearer {first_credential}"},
            json=command(first_device["id"]),
        )
        assert refreshed.status_code == 200
        refreshed_credential = client.cookies.get(DEVICE_COOKIE)
        assert refreshed_credential is not None
        assert refreshed_credential != first_credential
        assert (
            client.get(
                "/api/v2/me/snapshot",
                headers={"Authorization": f"Bearer {first_credential}"},
            ).status_code
            == 401
        )

    with TestClient(create_app(app_settings, sampler=first_cards)) as restarted:
        restored = body(
            restarted.get(
                "/api/v2/me/snapshot",
                headers={"Authorization": f"Bearer {second_credential}"},
            )
        )
        assert restored["session"] is None
        assert restored["player"]["id"] == player["id"]


@pytest.mark.parametrize(
    ("access_mode", "password"),
    [("open", None), ("password", "correct horse battery staple")],
)
def test_open_and_password_room_join(
    database_url: str, tmp_path: Path, access_mode: str, password: str | None
) -> None:
    with TestClient(create_app(settings(database_url, tmp_path), sampler=first_cards)) as client:
        room, gm_id, gm_credential = bootstrap(client, access_mode=access_mode, password=password)
        device, credential = pair_device(client, room["id"], gm_id, gm_credential)
        if password:
            denied = client.post(
                "/api/v2/me/profile",
                headers={"Authorization": f"Bearer {credential}"},
                json=command(device["id"], display_name="Mira", password="wrong password"),
            )
            assert denied.status_code == 403
        created = create_profile(client, device["id"], credential, password=password)
        assert created["player"]["display_name"] == "Mira"


def test_invitation_room_join_and_single_use(database_url: str, tmp_path: Path) -> None:
    with TestClient(create_app(settings(database_url, tmp_path), sampler=first_cards)) as client:
        room, gm_id, gm_credential = bootstrap(client, access_mode="invitation")
        invitation = body(
            client.post(
                f"/api/v2/rooms/{room['id']}/invitations",
                headers={"Authorization": f"Bearer {gm_credential}"},
                json=command(gm_id, ttl_seconds=600, max_uses=1),
            ),
            201,
        )["data"]
        device, credential = pair_device(client, room["id"], gm_id, gm_credential)
        created = create_profile(
            client,
            device["id"],
            credential,
            invitation_token=invitation["invitation_token"],
        )
        assert created["player"]["room_id"] == room["id"]

        other, other_credential = pair_device(client, room["id"], gm_id, gm_credential)
        denied = client.post(
            "/api/v2/me/profile",
            headers={"Authorization": f"Bearer {other_credential}"},
            json=command(
                other["id"],
                display_name="Other",
                invitation_token=invitation["invitation_token"],
            ),
        )
        assert denied.status_code == 403


def test_websocket_auth_replay_broadcast_and_revocation(database_url: str, tmp_path: Path) -> None:
    with TestClient(create_app(settings(database_url, tmp_path), sampler=first_cards)) as client:
        with (
            pytest.raises(WebSocketDisconnect) as unauthenticated,
            client.websocket_connect("/api/v2/realtime"),
        ):
            pass
        assert unauthenticated.value.code == 4401

        room, gm_id, gm_credential = bootstrap(client)
        device, player_credential = pair_device(client, room["id"], gm_id, gm_credential)
        create_profile(client, device["id"], player_credential)

        with client.websocket_connect("/api/v2/realtime?cursor=0") as invalid_socket:
            assert invalid_socket.receive_json()["type"] == "snapshot"
            invalid_socket.send_json({"type": "ack", "schema_version": 999, "cursor": 0})
            with pytest.raises(WebSocketDisconnect) as invalid_schema:
                invalid_socket.receive_json()
            assert invalid_schema.value.code == 4400

        with client.websocket_connect("/api/v2/realtime?cursor=0") as websocket:
            initial = websocket.receive_json()
            assert initial["type"] == "snapshot"
            assert initial["cursor"] >= 3

            session = body(
                client.post(
                    f"/api/v2/rooms/{room['id']}/sessions",
                    headers={"Authorization": f"Bearer {gm_credential}"},
                    json=command(gm_id),
                ),
                201,
            )["data"]
            event = websocket.receive_json()
            assert event["event_type"] == "GameSessionCreated"
            assert event["cursor"] > initial["cursor"]
            assert session["status"] == "PREPARATION"

            revoked = client.request(
                "DELETE",
                f"/api/v2/rooms/{room['id']}/devices/{device['id']}",
                headers={"Authorization": f"Bearer {gm_credential}"},
                json=command(gm_id),
            )
            assert revoked.status_code == 200
            with pytest.raises(WebSocketDisconnect) as disconnected:
                websocket.receive_json()
            assert disconnected.value.code == 4003

        rejected = client.get(
            "/api/v2/me/snapshot",
            headers={"Authorization": f"Bearer {player_credential}"},
        )
        assert rejected.status_code == 401
