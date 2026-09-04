from __future__ import annotations

from pathlib import Path

from fastapi.testclient import TestClient

from tabletop_companion.api.app import create_app
from tests.integration.conftest import first_cards
from tests.integration.test_local_multiplayer_api import (
    body,
    bootstrap,
    command,
    create_profile,
    pair_device,
    settings,
)


def test_character_card_notes_and_lobby_kick(database_url: str, tmp_path: Path) -> None:
    with TestClient(create_app(settings(database_url, tmp_path), sampler=first_cards)) as client:
        room, gm_id, gm_credential = bootstrap(client)
        device, player_credential = pair_device(client, room["id"], gm_id, gm_credential)
        profile = create_profile(client, device["id"], player_credential)
        player = profile["player"]

        options = body(
            client.get(
                "/api/v2/character-options",
                headers={"Authorization": f"Bearer {player_credential}"},
            )
        )
        assert {item["id"] for item in options["races"]} >= {"human", "elf", "dwarf"}
        assert {item["id"] for item in options["classes"]} >= {
            "fighter",
            "wizard",
            "rogue",
        }

        draft = body(
            client.post(
                "/api/v2/me/character-drafts",
                headers={"Authorization": f"Bearer {player_credential}"},
                json=command(device["id"], name="Nim", race_id="dwarf", class_id="rogue"),
            ),
            201,
        )["data"]
        for _ in range(draft["required_rounds"]):
            assert all("rogue" in card["class_ids"] for card in draft["offered_cards"])
            draft = body(
                client.post(
                    f"/api/v2/character-drafts/{draft['id']}/choices",
                    headers={"Authorization": f"Bearer {player_credential}"},
                    json=command(
                        device["id"],
                        card_id=draft["offered_cards"][0]["id"],
                        expected_version=draft["version"],
                    ),
                )
            )["data"]
        character = body(
            client.post(
                f"/api/v2/character-drafts/{draft['id']}/confirm",
                headers={"Authorization": f"Bearer {player_credential}"},
                json=command(device["id"], expected_version=draft["version"]),
            ),
            201,
        )["data"]
        assert (character["race_id"], character["class_id"]) == ("dwarf", "rogue")
        assert character["current_hp"] == character["max_hp"] == 11
        assert character["armor_class"] == 13

        gm_snapshot = body(
            client.get(
                "/api/v2/me/snapshot",
                headers={"Authorization": f"Bearer {gm_credential}"},
            )
        )
        summary = gm_snapshot["characters"][0]
        assert summary["owner_name"] == "Mira"
        assert summary["max_hp"] == 11

        edited = body(
            client.put(
                f"/api/v2/rooms/{room['id']}/characters/{character['id']}",
                headers={"Authorization": f"Bearer {gm_credential}"},
                json=command(
                    gm_id,
                    name="Nimble",
                    race_id="dwarf",
                    class_id="rogue",
                    stats=character["stats"],
                    ability_ids=[ability["id"] for ability in character["abilities"]],
                    max_hp=15,
                    current_hp=12,
                    armor_class=16,
                    expected_version=character["version"],
                ),
            )
        )["data"]
        assert (edited["name"], edited["current_hp"], edited["armor_class"]) == (
            "Nimble",
            12,
            16,
        )
        with_item = body(
            client.post(
                f"/api/v2/rooms/{room['id']}/characters/{character['id']}/inventory",
                headers={"Authorization": f"Bearer {gm_credential}"},
                json=command(
                    gm_id,
                    actor_id=gm_id,
                    name="Grappling hook",
                    quantity=1,
                    consumable=False,
                    locked=False,
                    equipped=False,
                    charges=None,
                    expected_version=edited["version"],
                ),
            ),
            201,
        )["data"]
        assert with_item["inventory"][0]["name"] == "Grappling hook"
        without_item = body(
            client.post(
                f"/api/v2/rooms/{room['id']}/characters/{character['id']}"
                f"/inventory/{with_item['inventory'][0]['id']}/discard",
                headers={"Authorization": f"Bearer {gm_credential}"},
                json=command(
                    gm_id,
                    actor_id=gm_id,
                    quantity=1,
                    expected_version=with_item["version"],
                ),
            )
        )["data"]
        assert without_item["inventory"] == []

        notes = body(
            client.get(
                f"/api/v2/rooms/{room['id']}/notes",
                headers={"Authorization": f"Bearer {gm_credential}"},
            )
        )
        saved_notes = body(
            client.put(
                f"/api/v2/rooms/{room['id']}/notes",
                headers={"Authorization": f"Bearer {gm_credential}"},
                json=command(
                    gm_id,
                    campaign="The old road",
                    other="Remember the weather",
                    expected_version=notes["version"],
                ),
            )
        )["data"]
        npc = body(
            client.post(
                f"/api/v2/rooms/{room['id']}/notes/npcs",
                headers={"Authorization": f"Bearer {gm_credential}"},
                json=command(gm_id, name="Innkeeper"),
            ),
            201,
        )["data"]
        body(
            client.put(
                f"/api/v2/rooms/{room['id']}/notes/npcs/{npc['id']}",
                headers={"Authorization": f"Bearer {gm_credential}"},
                json=command(
                    gm_id,
                    name="Mara",
                    details="Knows the northern trail.",
                    expected_version=npc["version"],
                ),
            )
        )
        loaded_notes = body(
            client.get(
                f"/api/v2/rooms/{room['id']}/notes",
                headers={"Authorization": f"Bearer {gm_credential}"},
            )
        )
        assert loaded_notes["campaign"] == saved_notes["campaign"]
        assert loaded_notes["npcs"][0]["details"] == "Knows the northern trail."

        kicked = body(
            client.request(
                "DELETE",
                f"/api/v2/rooms/{room['id']}/players/{player['id']}",
                headers={"Authorization": f"Bearer {gm_credential}"},
                json=command(gm_id),
            )
        )["data"]
        assert kicked["player_id"] == player["id"]
        assert (
            client.get(
                "/api/v2/me/snapshot",
                headers={"Authorization": f"Bearer {player_credential}"},
            ).status_code
            == 401
        )


def test_room_roll_with_advantage_is_public_and_persisted(
    database_url: str, tmp_path: Path
) -> None:
    app_settings = settings(database_url, tmp_path)
    with TestClient(create_app(app_settings, sampler=first_cards)) as client:
        room, gm_id, gm_credential = bootstrap(client)
        device, player_credential = pair_device(client, room["id"], gm_id, gm_credential)
        create_profile(client, device["id"], player_credential)

        payload = command(gm_id, expression="2d20+3", selection="advantage")
        response = body(
            client.post(
                f"/api/v2/rooms/{room['id']}/rolls",
                headers={"Authorization": f"Bearer {gm_credential}"},
                json=payload,
            ),
            201,
        )
        roll = response["data"]["roll"]
        assert roll["selection"] == "advantage"
        assert len(roll["attempts"]) == 2
        assert roll["result"] == max(roll["attempt_totals"])

        replay = body(
            client.post(
                f"/api/v2/rooms/{room['id']}/rolls",
                headers={"Authorization": f"Bearer {gm_credential}"},
                json=payload,
            ),
            201,
        )
        assert replay["meta"]["replayed"] is True
        assert replay["data"] == response["data"]

        player_snapshot = body(
            client.get(
                "/api/v2/me/snapshot",
                headers={"Authorization": f"Bearer {player_credential}"},
            )
        )
        assert player_snapshot["dice_rolls"][0]["id"] == roll["id"]

    with TestClient(create_app(app_settings, sampler=first_cards)) as restarted:
        restored = body(
            restarted.get(
                "/api/v2/me/snapshot",
                headers={"Authorization": f"Bearer {player_credential}"},
            )
        )
        assert restored["dice_rolls"][0]["id"] == roll["id"]
