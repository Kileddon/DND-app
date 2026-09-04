from pathlib import Path
from typing import Any, cast

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


def test_private_player_note_tree_persists_and_enforces_depth(
    database_url: str, tmp_path: Path
) -> None:
    app_settings = settings(database_url, tmp_path)
    with TestClient(create_app(app_settings, sampler=first_cards)) as client:
        room, gm_id, gm_credential = bootstrap(client)
        device, credential = pair_device(client, room["id"], gm_id, gm_credential)
        create_profile(client, device["id"], credential)

        def create(kind: str, name: str, parent_id: str | None = None) -> dict[str, Any]:
            return cast(
                dict[str, Any],
                body(
                    client.post(
                        "/api/v2/me/notes",
                        headers={"Authorization": f"Bearer {credential}"},
                        json=command(device["id"], kind=kind, name=name, parent_id=parent_id),
                    ),
                    201,
                )["data"],
            )

        first = create("folder", "Кампания")
        second = create("folder", "Города", str(first["id"]))
        third = create("folder", "Столица", str(second["id"]))
        rejected = client.post(
            "/api/v2/me/notes",
            headers={"Authorization": f"Bearer {credential}"},
            json=command(
                device["id"], kind="folder", name="Слишком глубоко", parent_id=third["id"]
            ),
        )
        assert rejected.status_code == 422, rejected.text
        assert rejected.json()["error"]["code"] == "folder_depth_limit"

        note = create("note", "Зацепки", str(third["id"]))
        edited = body(
            client.put(
                f"/api/v2/me/notes/{note['id']}",
                headers={"Authorization": f"Bearer {credential}"},
                json=command(
                    device["id"],
                    name="Главные зацепки",
                    body="След ведёт в башню.",
                    expected_version=note["version"],
                ),
            )
        )["data"]
        assert edited["body"] == "След ведёт в башню."

        for index in range(50):
            create("note", f"Корневая заметка {index + 1}")
        limit = client.post(
            "/api/v2/me/notes",
            headers={"Authorization": f"Bearer {credential}"},
            json=command(device["id"], kind="note", name="Лишняя", parent_id=None),
        )
        assert limit.status_code == 422
        assert limit.json()["error"]["code"] == "folder_note_limit"

        other_device, other_credential = pair_device(
            client, room["id"], gm_id, gm_credential, label="Second player"
        )
        create_profile(client, other_device["id"], other_credential)
        assert (
            body(
                client.get(
                    "/api/v2/me/notes",
                    headers={"Authorization": f"Bearer {other_credential}"},
                )
            )["nodes"]
            == []
        )

    with TestClient(create_app(app_settings, sampler=first_cards)) as restarted:
        restored = body(
            restarted.get(
                "/api/v2/me/notes",
                headers={"Authorization": f"Bearer {credential}"},
            )
        )["nodes"]
        restored_note = next(node for node in restored if node["id"] == note["id"])
        assert restored_note["name"] == "Главные зацепки"
        assert restored_note["body"] == "След ведёт в башню."
