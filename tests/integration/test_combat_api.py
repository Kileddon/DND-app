from __future__ import annotations

from io import BytesIO
from pathlib import Path
from typing import Any, cast

import pytest
from fastapi.testclient import TestClient
from PIL import Image
from starlette.websockets import WebSocketDisconnect

from tabletop_companion.api.app import create_app
from tabletop_companion.config import Settings
from tests.integration.conftest import first_cards
from tests.integration.test_local_multiplayer_api import (
    body,
    bootstrap,
    command,
    create_profile,
    pair_device,
)


def settings(database_url: str, tmp_path: Path) -> Settings:
    return Settings(
        database_url=database_url,
        log_level="WARNING",
        host_secret_path=tmp_path / "host-secret.key",
        frontend_dist=tmp_path / "missing-frontend",
        media_library=tmp_path / "media",
    )


def create_active_session(
    client: TestClient, room_id: str, gm_id: str, credential: str
) -> dict[str, Any]:
    session = body(
        client.post(
            f"/api/v2/rooms/{room_id}/sessions",
            headers={"Authorization": f"Bearer {credential}"},
            json=command(gm_id),
        ),
        201,
    )["data"]
    for target in ("LOBBY", "ACTIVE"):
        session = body(
            client.post(
                f"/api/v2/rooms/{room_id}/sessions/{session['id']}/transition",
                headers={"Authorization": f"Bearer {credential}"},
                json=command(
                    gm_id,
                    target_status=target,
                    expected_version=session["version"],
                ),
            )
        )["data"]
    return cast(dict[str, Any], session)


def create_character(client: TestClient, device_id: str, credential: str) -> dict[str, Any]:
    draft = body(
        client.post(
            "/api/v2/me/character-drafts",
            headers={"Authorization": f"Bearer {credential}"},
            json=command(device_id, name="Aria"),
        ),
        201,
    )["data"]
    for _ in range(4):
        draft = body(
            client.post(
                f"/api/v2/character-drafts/{draft['id']}/choices",
                headers={"Authorization": f"Bearer {credential}"},
                json=command(
                    device_id,
                    card_id=draft["offered_cards"][0]["id"],
                    expected_version=draft["version"],
                ),
            )
        )["data"]
    return cast(
        dict[str, Any],
        body(
            client.post(
                f"/api/v2/character-drafts/{draft['id']}/confirm",
                headers={"Authorization": f"Bearer {credential}"},
                json=command(device_id, expected_version=draft["version"]),
            ),
            201,
        )["data"],
    )


def test_combat_health_visibility_compensation_and_restart(
    database_url: str, tmp_path: Path
) -> None:
    app_settings = settings(database_url, tmp_path)
    with TestClient(create_app(app_settings, sampler=first_cards)) as client:
        room, gm_id, gm_credential = bootstrap(client)
        device, player_credential = pair_device(client, room["id"], gm_id, gm_credential)
        create_profile(client, device["id"], player_credential)
        character = create_character(client, device["id"], player_credential)
        session = create_active_session(client, room["id"], gm_id, gm_credential)

        combat = body(
            client.post(
                f"/api/v2/rooms/{room['id']}/sessions/{session['id']}/combats",
                headers={"Authorization": f"Bearer {gm_credential}"},
                json=command(gm_id),
            ),
            201,
        )["data"]
        combat = body(
            client.post(
                f"/api/v2/rooms/{room['id']}/combats/{combat['id']}/characters",
                headers={"Authorization": f"Bearer {gm_credential}"},
                json=command(
                    gm_id,
                    expected_version=combat["version"],
                    character_id=character["id"],
                    initiative=15,
                    max_hp=24,
                    current_hp=24,
                    armor_class=14,
                    late_join=False,
                ),
            ),
            201,
        )["data"]
        character_combatant = next(
            item for item in combat["combatants"] if item["kind"] == "character"
        )
        assert character_combatant["max_hp"] == character["max_hp"]
        assert character_combatant["current_hp"] == character["current_hp"]
        assert character_combatant["armor_class"] == character["armor_class"]
        image_stream = BytesIO()
        Image.new("RGB", (2, 2), "green").save(image_stream, format="PNG")
        image_url = body(
            client.post(
                f"/api/v2/rooms/{room['id']}/media",
                headers={
                    "Authorization": f"Bearer {gm_credential}",
                    "Content-Type": "image/png",
                    "X-Upload-Filename": "goblin.png",
                },
                content=image_stream.getvalue(),
            )
        )["url"]
        template = body(
            client.post(
                f"/api/v2/rooms/{room['id']}/monster-templates",
                headers={"Authorization": f"Bearer {gm_credential}"},
                json=command(
                    gm_id,
                    name="Goblin",
                    max_hp=10,
                    current_hp=10,
                    armor_class=13,
                    image_url=image_url,
                    species="Гоблиноид",
                    notes="",
                    conditions=["Frightened"],
                    actions=["Scimitar"],
                ),
            ),
            201,
        )["data"]
        assert template["species"] == "Гоблиноид"
        assert template["image_url"] == image_url
        combat = body(
            client.post(
                f"/api/v2/rooms/{room['id']}/combats/{combat['id']}/monsters",
                headers={"Authorization": f"Bearer {gm_credential}"},
                json=command(
                    gm_id,
                    expected_version=combat["version"],
                    template_id=template["id"],
                    initiative=12,
                    count=2,
                    grouped=True,
                ),
            ),
            201,
        )["data"]
        combat = body(
            client.post(
                f"/api/v2/rooms/{room['id']}/combats/{combat['id']}/transition",
                headers={"Authorization": f"Bearer {gm_credential}"},
                json=command(gm_id, expected_version=combat["version"], action="start"),
            )
        )["data"]
        monsters = [item for item in combat["combatants"] if item["kind"] == "monster"]
        health = body(
            client.post(
                f"/api/v2/rooms/{room['id']}/combats/{combat['id']}/health",
                headers={"Authorization": f"Bearer {gm_credential}"},
                json=command(
                    gm_id,
                    source_id=None,
                    targets=[
                        {"target_id": item["id"], "expected_version": item["version"]}
                        for item in monsters
                    ],
                    action="damage",
                    amount=7,
                    prevented=1,
                    critical=True,
                ),
            )
        )["data"]
        assert [item["current_hp"] for item in health["targets"]] == [4, 4]

        player_view = body(
            client.get(
                "/api/v2/me/combat",
                headers={"Authorization": f"Bearer {player_credential}"},
            )
        )
        player_monsters = [item for item in player_view["combatants"] if item["kind"] == "monster"]
        assert all("current_hp" not in item and "max_hp" not in item for item in player_monsters)
        assert {item["wound_state"] for item in player_monsters} == {"ранен"}

        with client.websocket_connect(
            f"/api/v2/realtime?cursor={player_view['journal'][-1]['cursor'] - 1}"
        ) as websocket:
            replay = websocket.receive_json()
            assert replay["event_type"] == "HealthChanged"
            assert all("current_hp" not in item for item in replay["payload"]["targets"])
            websocket.send_json({"type": "ack", "schema_version": 999, "cursor": replay["cursor"]})
            with pytest.raises(WebSocketDisconnect):
                websocket.receive_json()

        hidden_condition = body(
            client.post(
                f"/api/v2/rooms/{room['id']}/combats/{combat['id']}/combatants/{monsters[0]['id']}/conditions",
                headers={"Authorization": f"Bearer {gm_credential}"},
                json=command(
                    gm_id,
                    expected_version=health["targets"][0]["version"],
                    catalog_id=None,
                    name="Secret mark",
                    description="GM only",
                    source_id=None,
                    visible_to_players=False,
                ),
            )
        )["data"]
        assert hidden_condition["conditions"][0]["name"] == "Frightened"
        assert hidden_condition["conditions"][-1]["name"] == "Secret mark"
        hidden_player_view = body(
            client.get(
                "/api/v2/me/combat",
                headers={"Authorization": f"Bearer {player_credential}"},
            )
        )
        hidden_monster = next(
            item for item in hidden_player_view["combatants"] if item["id"] == monsters[0]["id"]
        )
        assert {item["name"] for item in hidden_monster["conditions"]} == {"Frightened"}
        assert "Secret mark" not in str(hidden_player_view["journal"])

        roll_payload = command(
            gm_id,
            actor_ids=[monsters[0]["id"]],
            expression="1d20+2",
            mode="digital",
            visibility="secret",
            recipient_player_id=None,
            physical_result=None,
            action_event_id=None,
        )
        first_roll = body(
            client.post(
                f"/api/v2/rooms/{room['id']}/combats/{combat['id']}/rolls",
                headers={"Authorization": f"Bearer {gm_credential}"},
                json=roll_payload,
            ),
            201,
        )
        replayed_roll = body(
            client.post(
                f"/api/v2/rooms/{room['id']}/combats/{combat['id']}/rolls",
                headers={"Authorization": f"Bearer {gm_credential}"},
                json=roll_payload,
            ),
            201,
        )
        assert replayed_roll["meta"]["replayed"] is True
        assert replayed_roll["data"] == first_roll["data"]
        secret_roll_id = first_roll["data"]["rolls"][0]["id"]
        player_after_roll = body(
            client.get(
                "/api/v2/me/combat",
                headers={"Authorization": f"Bearer {player_credential}"},
            )
        )
        assert secret_roll_id not in {item["id"] for item in player_after_roll["rolls"]}

        cancelled = body(
            client.post(
                f"/api/v2/rooms/{room['id']}/combats/{combat['id']}/events/{health['event_id']}/cancel",
                headers={"Authorization": f"Bearer {gm_credential}"},
                json=command(gm_id),
            )
        )["data"]
        assert cancelled["original_event_id"] == health["event_id"]
        repeated = client.post(
            f"/api/v2/rooms/{room['id']}/combats/{combat['id']}/events/{health['event_id']}/cancel",
            headers={"Authorization": f"Bearer {gm_credential}"},
            json=command(gm_id),
        )
        assert repeated.status_code == 409
        assert repeated.json()["error"]["code"] == "event_already_compensated"

        restored_combat = body(
            client.get(
                "/api/v2/me/combat",
                headers={"Authorization": f"Bearer {gm_credential}"},
            )
        )
        restored_template = next(
            item for item in restored_combat["monster_templates"] if item["id"] == template["id"]
        )
        assert restored_template["species"] == "Гоблиноид"
        assert restored_template["image_url"] == image_url
        assert client.get(image_url).status_code == 200
        target = next(item for item in restored_combat["combatants"] if item["kind"] == "monster")
        original = body(
            client.post(
                f"/api/v2/rooms/{room['id']}/combats/{combat['id']}/health",
                headers={"Authorization": f"Bearer {gm_credential}"},
                json=command(
                    gm_id,
                    source_id=None,
                    targets=[{"target_id": target["id"], "expected_version": target["version"]}],
                    action="damage",
                    amount=3,
                    prevented=0,
                    critical=False,
                ),
            )
        )["data"]
        corrected = body(
            client.post(
                f"/api/v2/rooms/{room['id']}/combats/{combat['id']}/events/{original['event_id']}/correct",
                headers={"Authorization": f"Bearer {gm_credential}"},
                json=command(
                    gm_id,
                    source_id=None,
                    targets=[
                        {
                            "target_id": target["id"],
                            "expected_version": original["targets"][0]["version"],
                        }
                    ],
                    action="damage",
                    amount=2,
                    prevented=0,
                    critical=False,
                ),
            )
        )["data"]
        assert corrected["replacement_event_id"]
        assert corrected["targets"][0]["current_hp"] == 8

    with TestClient(create_app(app_settings, sampler=first_cards)) as restarted:
        restored = body(
            restarted.get(
                "/api/v2/me/combat",
                headers={"Authorization": f"Bearer {gm_credential}"},
            )
        )
        assert restored["status"] == "ACTIVE"
        assert restored["round_number"] == 1
        restored_template = next(
            item for item in restored["monster_templates"] if item["id"] == template["id"]
        )
        assert restored_template["species"] == "Гоблиноид"
        assert restored_template["image_url"] == image_url
        assert restarted.get(image_url).status_code == 200
