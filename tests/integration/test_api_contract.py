from __future__ import annotations

from typing import Any, cast
from uuid import uuid4

from fastapi.testclient import TestClient


def command_payload(**extra: object) -> dict[str, object]:
    return {
        "command_id": str(uuid4()),
        "device_id": "test-device",
        **extra,
    }


def json_object(response: Any) -> dict[str, Any]:
    return cast(dict[str, Any], response.json())


def test_api_returns_stable_not_found_and_validation_errors(client: TestClient) -> None:
    missing = client.get(f"/api/v1/rooms/{uuid4()}")
    invalid = client.post(
        "/api/v1/rooms",
        json=command_payload(gm_id=str(uuid4()), name=""),
    )

    assert missing.status_code == 404
    assert json_object(missing)["error"]["code"] == "entity_not_found"
    assert invalid.status_code == 422
    assert json_object(invalid)["error"]["code"] == "validation_error"


def test_command_id_is_idempotent_and_rejects_changed_payload(client: TestClient) -> None:
    command_id = str(uuid4())
    gm_id = str(uuid4())
    payload = {
        "command_id": command_id,
        "device_id": "gm-laptop",
        "gm_id": gm_id,
        "name": "The Amber Road",
    }

    first = client.post("/api/v1/rooms", json=payload)
    replay = client.post("/api/v1/rooms", json=payload)
    changed = client.post("/api/v1/rooms", json={**payload, "name": "Changed"})

    assert first.status_code == 201
    assert replay.status_code == 201
    assert json_object(first)["data"] == json_object(replay)["data"]
    assert json_object(first)["meta"] == {"replayed": False}
    assert json_object(replay)["meta"] == {"replayed": True}
    assert changed.status_code == 409
    assert json_object(changed)["error"]["code"] == "idempotency_conflict"

    changed_type = client.post(
        f"/api/v1/rooms/{json_object(first)['data']['id']}/players",
        json={"command_id": command_id, "device_id": "test-device", "display_name": "Mira"},
    )
    assert changed_type.status_code == 409
    assert json_object(changed_type)["error"]["code"] == "idempotency_conflict"


def test_incomplete_draft_returns_stable_conflict(client: TestClient) -> None:
    gm_id = str(uuid4())
    room = json_object(
        client.post(
            "/api/v1/rooms",
            json=command_payload(gm_id=gm_id, name="Room"),
        )
    )["data"]
    player = json_object(
        client.post(
            f"/api/v1/rooms/{room['id']}/players",
            json=command_payload(display_name="Mira"),
        )
    )["data"]
    draft = json_object(
        client.post(
            f"/api/v1/rooms/{room['id']}/players/{player['id']}/character-drafts",
            json=command_payload(name="Aria"),
        )
    )["data"]

    response = client.post(
        f"/api/v1/character-drafts/{draft['id']}/players/{player['id']}/confirm",
        json=command_payload(expected_version=draft["version"]),
    )

    assert response.status_code == 409
    assert json_object(response)["error"]["code"] == "draft_incomplete"


def test_confirm_replay_does_not_create_second_character(client: TestClient) -> None:
    room = json_object(
        client.post(
            "/api/v1/rooms",
            json=command_payload(gm_id=str(uuid4()), name="Room"),
        )
    )["data"]
    player = json_object(
        client.post(
            f"/api/v1/rooms/{room['id']}/players",
            json=command_payload(display_name="Mira"),
        )
    )["data"]
    draft = json_object(
        client.post(
            f"/api/v1/rooms/{room['id']}/players/{player['id']}/character-drafts",
            json=command_payload(name="Aria"),
        )
    )["data"]
    for _ in range(4):
        draft = json_object(
            client.post(
                f"/api/v1/character-drafts/{draft['id']}/players/{player['id']}/choices",
                json=command_payload(
                    card_id=draft["offered_cards"][0]["id"],
                    expected_version=draft["version"],
                ),
            )
        )["data"]
    confirm_payload = command_payload(expected_version=draft["version"])
    url = f"/api/v1/character-drafts/{draft['id']}/players/{player['id']}/confirm"

    first = client.post(url, json=confirm_payload)
    replay = client.post(url, json=confirm_payload)

    assert first.status_code == 201
    assert replay.status_code == 201
    assert json_object(first)["data"]["id"] == json_object(replay)["data"]["id"]
    assert json_object(replay)["meta"]["replayed"] is True
