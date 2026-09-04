from __future__ import annotations

from contextlib import AbstractContextManager
from typing import Any, cast
from uuid import uuid4

from fastapi.testclient import TestClient

from tabletop_companion.api.app import create_app
from tabletop_companion.config import Settings
from tests.integration.conftest import first_cards


def payload(**extra: object) -> dict[str, object]:
    return {
        "command_id": str(uuid4()),
        "device_id": "acceptance-device",
        **extra,
    }


def body(response: Any) -> dict[str, Any]:
    assert response.status_code in {200, 201}, response.text
    return cast(dict[str, Any], response.json())


def client_context(database_url: str) -> AbstractContextManager[TestClient]:
    settings = Settings(database_url=database_url, log_level="WARNING")
    return TestClient(create_app(settings, sampler=first_cards))


def test_full_slice_survives_restart_and_preserves_event_log(database_url: str) -> None:
    gm_id = str(uuid4())
    with client_context(database_url) as client:
        room = body(
            client.post(
                "/api/v1/rooms",
                json=payload(gm_id=gm_id, name="The Amber Road"),
            )
        )["data"]
        player = body(
            client.post(
                f"/api/v1/rooms/{room['id']}/players",
                json=payload(display_name="Mira"),
            )
        )["data"]
        draft = body(
            client.post(
                f"/api/v1/rooms/{room['id']}/players/{player['id']}/character-drafts",
                json=payload(name="Aria"),
            )
        )["data"]

        for _ in range(4):
            draft = body(
                client.post(
                    f"/api/v1/character-drafts/{draft['id']}/players/{player['id']}/choices",
                    json=payload(
                        card_id=draft["offered_cards"][0]["id"],
                        expected_version=draft["version"],
                    ),
                )
            )["data"]

        character = body(
            client.post(
                f"/api/v1/character-drafts/{draft['id']}/players/{player['id']}/confirm",
                json=payload(expected_version=draft["version"]),
            )
        )["data"]
        assert len(character["abilities"]) == 4

        character = body(
            client.post(
                f"/api/v1/characters/{character['id']}/inventory",
                json=payload(
                    actor_id=player["id"],
                    name="Rope",
                    quantity=1,
                    consumable=False,
                    expected_version=character["version"],
                ),
            )
        )["data"]
        rope_id = character["inventory"][0]["id"]
        character = body(
            client.post(
                f"/api/v1/characters/{character['id']}/inventory",
                json=payload(
                    actor_id=player["id"],
                    name="Healing Potion",
                    quantity=5,
                    consumable=True,
                    charges=1,
                    expected_version=character["version"],
                ),
            )
        )["data"]
        potion_id = next(
            item["id"] for item in character["inventory"] if item["name"] == "Healing Potion"
        )
        discard_command = payload(
            actor_id=player["id"],
            quantity=2,
            expected_version=character["version"],
        )
        discarded = body(
            client.post(
                f"/api/v1/characters/{character['id']}/inventory/{potion_id}/discard",
                json=discard_command,
            )
        )
        replayed = body(
            client.post(
                f"/api/v1/characters/{character['id']}/inventory/{potion_id}/discard",
                json=discard_command,
            )
        )
        assert discarded["data"] == replayed["data"]
        assert replayed["meta"]["replayed"] is True
        character = discarded["data"]
        character = body(
            client.post(
                f"/api/v1/characters/{character['id']}/inventory/{rope_id}/discard",
                json=payload(
                    actor_id=player["id"],
                    quantity=1,
                    expected_version=character["version"],
                ),
            )
        )["data"]
        character_id = character["id"]
        room_id = room["id"]

    with client_context(database_url) as restarted_client:
        restored = body(restarted_client.get(f"/api/v1/characters/{character_id}"))
        events = body(restarted_client.get(f"/api/v1/rooms/{room_id}/events"))

    assert restored["inventory"] == [
        {
            "id": potion_id,
            "definition_id": restored["inventory"][0]["definition_id"],
            "name": "Healing Potion",
            "consumable": True,
            "locked": False,
            "quantity": 3,
            "equipped": False,
            "charges": 1,
            "created_at": restored["inventory"][0]["created_at"],
            "unit_weight": "0.000",
            "slot_compatibility": "none",
            "equipment_slot": None,
        }
    ]
    assert len(restored["abilities"]) == 4
    discarded_events = [event for event in events["data"] if event["event_type"] == "ItemDiscarded"]
    assert len(discarded_events) == 2
    assert discarded_events[0]["payload"]["effect_applied"] is False
