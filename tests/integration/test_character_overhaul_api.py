from pathlib import Path

from fastapi.testclient import TestClient

from tabletop_companion.api.app import create_app
from tests.integration.conftest import first_cards
from tests.integration.test_combat_api import create_active_session, create_character, settings
from tests.integration.test_local_multiplayer_api import (
    body,
    bootstrap,
    command,
    create_profile,
    pair_device,
)


def test_equipment_and_prepared_encounters_persist(database_url: str, tmp_path: Path) -> None:
    with TestClient(create_app(settings(database_url, tmp_path), sampler=first_cards)) as client:
        room, gm_id, gm_credential = bootstrap(client)
        device, credential = pair_device(client, room["id"], gm_id, gm_credential)
        player = create_profile(client, device["id"], credential)["player"]
        character = create_character(client, device["id"], credential)
        added = body(
            client.post(
                f"/api/v2/characters/{character['id']}/inventory",
                headers={"Authorization": f"Bearer {credential}"},
                json=command(
                    device["id"],
                    actor_id=player["id"],
                    name="Меч",
                    quantity=1,
                    unit_weight="1.500",
                    slot_compatibility="hand",
                    expected_version=character["version"],
                ),
            ),
            201,
        )["data"]
        item = added["inventory"][0]
        equipped = body(
            client.post(
                f"/api/v2/characters/{character['id']}/inventory/{item['id']}/equipment",
                headers={"Authorization": f"Bearer {credential}"},
                json=command(
                    device["id"],
                    actor_id=player["id"],
                    slot="left_hand",
                    expected_version=added["version"],
                ),
            )
        )["data"]
        assert equipped["inventory"][0]["equipment_slot"] == "left_hand"
        assert equipped["total_weight"] == "1.500"

        session = create_active_session(client, room["id"], gm_id, gm_credential)
        encounters = []
        for name in ("Засада", "Финал"):
            encounters.append(
                body(
                    client.post(
                        f"/api/v2/rooms/{room['id']}/sessions/{session['id']}/combats",
                        headers={"Authorization": f"Bearer {gm_credential}"},
                        json=command(gm_id, name=name),
                    ),
                    201,
                )["data"]
            )
        assert [item["name"] for item in encounters] == ["Засада", "Финал"]
        snapshot = body(
            client.get("/api/v2/me/snapshot", headers={"Authorization": f"Bearer {gm_credential}"})
        )
        assert {item["name"] for item in snapshot["encounters"]} == {"Засада", "Финал"}


def test_combat_health_updates_permanent_character(database_url: str, tmp_path: Path) -> None:
    with TestClient(create_app(settings(database_url, tmp_path), sampler=first_cards)) as client:
        room, gm_id, gm_credential = bootstrap(client)
        device, credential = pair_device(client, room["id"], gm_id, gm_credential)
        create_profile(client, device["id"], credential)
        character = create_character(client, device["id"], credential)
        session = create_active_session(client, room["id"], gm_id, gm_credential)
        combat = body(
            client.post(
                f"/api/v2/rooms/{room['id']}/sessions/{session['id']}/combats",
                headers={"Authorization": f"Bearer {gm_credential}"},
                json=command(gm_id, name="Проверка последствий"),
            ),
            201,
        )["data"]
        combat = body(
            client.post(
                f"/api/v2/rooms/{room['id']}/combats/{combat['id']}/characters",
                headers={"Authorization": f"Bearer {gm_credential}"},
                json=command(
                    gm_id,
                    character_id=character["id"],
                    initiative=10,
                    max_hp=999,
                    current_hp=999,
                    armor_class=10,
                    late_join=False,
                    expected_version=combat["version"],
                ),
            ),
            201,
        )["data"]
        target = combat["combatants"][0]
        body(
            client.post(
                f"/api/v2/rooms/{room['id']}/combats/{combat['id']}/health",
                headers={"Authorization": f"Bearer {gm_credential}"},
                json=command(
                    gm_id,
                    source_id=None,
                    targets=[{"target_id": target["id"], "expected_version": target["version"]}],
                    action="damage",
                    amount=2,
                    prevented=0,
                    critical=False,
                    roll_id=None,
                ),
            )
        )
        restored = body(
            client.get(
                f"/api/v2/characters/{character['id']}",
                headers={"Authorization": f"Bearer {credential}"},
            )
        )
        assert restored["current_hp"] == character["current_hp"] - 2


def test_room_roll_visibility_and_delayed_reveal(database_url: str, tmp_path: Path) -> None:
    with TestClient(create_app(settings(database_url, tmp_path), sampler=first_cards)) as client:
        room, gm_id, gm_credential = bootstrap(client)
        first_device, first_credential = pair_device(client, room["id"], gm_id, gm_credential)
        first_player = create_profile(client, first_device["id"], first_credential)["player"]
        second_device, second_credential = pair_device(client, room["id"], gm_id, gm_credential)
        create_profile(client, second_device["id"], second_credential)

        secret_attempt = client.post(
            f"/api/v2/rooms/{room['id']}/rolls",
            headers={"Authorization": f"Bearer {first_credential}"},
            json=command(
                first_device["id"], expression="1d20", visibility="secret", mode="digital"
            ),
        )
        assert secret_attempt.status_code == 403

        private_roll = body(
            client.post(
                f"/api/v2/rooms/{room['id']}/rolls",
                headers={"Authorization": f"Bearer {gm_credential}"},
                json=command(
                    gm_id,
                    expression="1d20",
                    visibility="private",
                    mode="digital",
                    recipient_player_id=first_player["id"],
                ),
            ),
            201,
        )["data"]["roll"]
        delayed_roll = body(
            client.post(
                f"/api/v2/rooms/{room['id']}/rolls",
                headers={"Authorization": f"Bearer {gm_credential}"},
                json=command(gm_id, expression="1d6", visibility="delayed", mode="digital"),
            ),
            201,
        )["data"]["roll"]

        first_snapshot = body(
            client.get(
                "/api/v2/me/snapshot", headers={"Authorization": f"Bearer {first_credential}"}
            )
        )
        second_snapshot = body(
            client.get(
                "/api/v2/me/snapshot", headers={"Authorization": f"Bearer {second_credential}"}
            )
        )
        assert private_roll["id"] in {item["id"] for item in first_snapshot["dice_rolls"]}
        assert private_roll["id"] not in {item["id"] for item in second_snapshot["dice_rolls"]}
        assert delayed_roll["id"] not in {item["id"] for item in first_snapshot["dice_rolls"]}

        body(
            client.post(
                f"/api/v2/rooms/{room['id']}/rolls/{delayed_roll['id']}/reveal",
                headers={"Authorization": f"Bearer {gm_credential}"},
                json=command(gm_id),
            )
        )
        revealed = body(
            client.get(
                "/api/v2/me/snapshot", headers={"Authorization": f"Bearer {second_credential}"}
            )
        )
        assert delayed_roll["id"] in {item["id"] for item in revealed["dice_rolls"]}


def test_character_archive_restore_and_active_encounter_guard(
    database_url: str, tmp_path: Path
) -> None:
    with TestClient(create_app(settings(database_url, tmp_path), sampler=first_cards)) as client:
        room, gm_id, gm_credential = bootstrap(client)
        device, credential = pair_device(client, room["id"], gm_id, gm_credential)
        create_profile(client, device["id"], credential)
        character = create_character(client, device["id"], credential)
        archived = body(
            client.post(
                f"/api/v2/me/characters/{character['id']}/lifecycle",
                headers={"Authorization": f"Bearer {credential}"},
                json=command(device["id"], expected_version=character["version"], action="archive"),
            )
        )["data"]
        snapshot = body(
            client.get("/api/v2/me/snapshot", headers={"Authorization": f"Bearer {credential}"})
        )
        assert character["id"] not in {item["id"] for item in snapshot["characters"]}
        assert character["id"] in {item["id"] for item in snapshot["archived_characters"]}
        body(
            client.post(
                f"/api/v2/me/characters/{character['id']}/lifecycle",
                headers={"Authorization": f"Bearer {credential}"},
                json=command(device["id"], expected_version=archived["version"], action="restore"),
            )
        )["data"]

        session = create_active_session(client, room["id"], gm_id, gm_credential)
        combat = body(
            client.post(
                f"/api/v2/rooms/{room['id']}/sessions/{session['id']}/combats",
                headers={"Authorization": f"Bearer {gm_credential}"},
                json=command(gm_id, name="Archive guard"),
            ),
            201,
        )["data"]
        combat = body(
            client.post(
                f"/api/v2/rooms/{room['id']}/combats/{combat['id']}/characters",
                headers={"Authorization": f"Bearer {gm_credential}"},
                json=command(
                    gm_id,
                    character_id=character["id"],
                    initiative=10,
                    max_hp=10,
                    current_hp=10,
                    armor_class=10,
                    late_join=False,
                    expected_version=combat["version"],
                ),
            ),
            201,
        )["data"]
        active = body(
            client.post(
                f"/api/v2/rooms/{room['id']}/combats/{combat['id']}/transition",
                headers={"Authorization": f"Bearer {gm_credential}"},
                json=command(gm_id, expected_version=combat["version"], action="start"),
            )
        )["data"]
        target = active["combatants"][0]
        body(
            client.post(
                f"/api/v2/rooms/{room['id']}/combats/{combat['id']}"
                f"/combatants/{target['id']}/conditions",
                headers={"Authorization": f"Bearer {gm_credential}"},
                json=command(
                    gm_id,
                    expected_version=target["version"],
                    name="Шрам",
                    description="Остаётся между боями",
                    visible_to_players=True,
                    persistent=True,
                ),
            )
        )
        with_condition = body(
            client.get(
                f"/api/v2/characters/{character['id']}",
                headers={"Authorization": f"Bearer {credential}"},
            )
        )
        assert with_condition["persistent_conditions"][0]["name"] == "Шрам"
        rejected = client.post(
            f"/api/v2/me/characters/{character['id']}/lifecycle",
            headers={"Authorization": f"Bearer {credential}"},
            json=command(
                device["id"], expected_version=with_condition["version"], action="archive"
            ),
        )
        assert rejected.status_code == 409
        assert rejected.json()["error"]["code"] == "character_in_active_encounter"
