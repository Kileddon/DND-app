import { cleanup, render, screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { afterEach, describe, expect, it, vi } from "vitest";

import {
  ApiError,
  api,
  type Character,
  type CombatState,
  type Snapshot,
} from "./api";
import { HostCombatPanel, PlayerCombatPanel } from "./components/CombatPanel";
import { ConnectionBadge } from "./components/ConnectionBadge";
import { App } from "./App";
import { WelcomeScreen } from "./components/EntryScreens";
import { ErrorNotice } from "./components/ErrorNotice";
import { HostDashboard } from "./components/HostDashboard";
import { PlayerDashboard } from "./components/PlayerDashboard";
import { HostCharactersPanel } from "./components/HostCharactersPanel";
import { CharacterSheet } from "./components/CharacterSheet";

const gmSnapshot: Snapshot = {
  cursor: 10,
  current_device_id: "gm-device",
  room: { id: "room", name: "Amber Road", code: "AMBER1", access_mode: "open" },
  session: { id: "session", room_id: "room", status: "LOBBY", version: 2 },
  players: [
    {
      id: "player",
      room_id: "room",
      display_name: "Mira",
      selected_character_id: null,
      version: 1,
    },
  ],
  devices: [],
};

const character: Character = {
  id: "character",
  name: "Aria",
  owner_id: "player",
  race_id: "human",
  class_id: "fighter",
  max_hp: 20,
  current_hp: 20,
  armor_class: 15,
  stats: {
    strength: 16,
    dexterity: 12,
    constitution: 14,
    intelligence: 10,
    wisdom: 8,
    charisma: 13,
  },
  abilities: [
    { id: "swift", name: "Swift", description: "Fast", kind: "talent" },
  ],
  inventory: [
    { id: "rope", name: "Rope", quantity: 1, consumable: false, locked: false },
  ],
  version: 2,
};

const playerSnapshot: Snapshot = {
  cursor: 11,
  current_device_id: "player-device",
  room: { id: "room", name: "Amber Road", code: "AMBER1", access_mode: "open" },
  session: gmSnapshot.session,
  player: {
    id: "player",
    room_id: "room",
    display_name: "Mira",
    selected_character_id: "character",
    version: 2,
  },
  characters: [{ id: "character", name: "Aria", version: 2, selected: true }],
};

const combat: CombatState = {
  id: "combat",
  room_id: "room",
  session_id: "session",
  status: "ACTIVE",
  round_number: 2,
  current_entry_id: "monster-entry",
  version: 4,
  entries: [
    {
      id: "monster-entry",
      name: "Гоблины",
      initiative: 12,
      position: 0,
      combatant_ids: ["goblin"],
    },
  ],
  combatants: [
    {
      id: "hero-combatant",
      entry_id: "hero-entry",
      kind: "character",
      reference_id: "character",
      name: "Aria",
      version: 2,
      max_hp: 20,
      current_hp: 15,
      temporary_hp: 3,
      conditions: [],
    },
    {
      id: "goblin",
      entry_id: "monster-entry",
      kind: "monster",
      reference_id: "template",
      name: "Гоблин 1",
      version: 2,
      wound_state: "ранен",
      conditions: [],
    },
  ],
  monster_templates: [],
  rolls: [],
  journal: [
    {
      id: "health-event",
      event_type: "HealthChanged",
      occurred_at: "2026-09-03T10:00:00Z",
      payload: {},
    },
  ],
  report: null,
};

afterEach(() => {
  cleanup();
  vi.restoreAllMocks();
});

describe("local multiplayer interface", () => {
  it("opens host setup when the create-room hash link is clicked", async () => {
    location.hash = "";
    vi.spyOn(api, "snapshot").mockRejectedValue(
      new ApiError(401, "authentication_required", "Not authenticated", {}),
    );
    render(<App />);
    await userEvent.click(
      await screen.findByRole("link", { name: "Создать комнату" }),
    );
    expect(
      await screen.findByRole("heading", { name: "Создать комнату" }),
    ).toBeInTheDocument();
  });

  it("exchanges a short pairing code", async () => {
    location.hash = "";
    vi.spyOn(api, "exchangePairing").mockResolvedValue({
      data: { device: { id: "device" } as never },
      meta: { replayed: false },
    });
    const ready = vi.fn();
    render(<WelcomeScreen onReady={ready} />);
    await userEvent.type(screen.getByLabelText(/короткий код/i), "ABCD23");
    await userEvent.click(
      screen.getByRole("button", { name: /подключиться как игрок/i }),
    );
    await waitFor(() => expect(ready).toHaveBeenCalled());
  });

  it("renders lobby participants and session controls", async () => {
    vi.spyOn(api, "diagnostics").mockRejectedValue(new Error("not needed"));
    vi.spyOn(api, "transitionSession").mockResolvedValue({
      data: { ...gmSnapshot.session!, status: "ACTIVE", version: 3 },
      meta: { replayed: false },
    });
    render(<HostDashboard snapshot={gmSnapshot} refresh={vi.fn()} />);
    expect(screen.getByText("Mira")).toBeInTheDocument();
    await userEvent.click(screen.getByRole("button", { name: "Начать игру" }));
    expect(api.transitionSession).toHaveBeenCalled();
  });

  it("lets the GM kick a player from the lobby", async () => {
    vi.spyOn(api, "diagnostics").mockRejectedValue(new Error("offline"));
    vi.spyOn(api, "kickPlayer").mockResolvedValue({
      data: { player_id: "player", device_ids: ["player-device"] },
      meta: { replayed: false },
    });
    render(<HostDashboard snapshot={gmSnapshot} refresh={vi.fn()} />);

    await userEvent.click(screen.getByRole("button", { name: "Выгнать" }));

    await waitFor(() =>
      expect(api.kickPlayer).toHaveBeenCalledWith(
        "room",
        "player",
        "gm-device",
      ),
    );
  });

  it("opens the GM notes section", async () => {
    vi.spyOn(api, "diagnostics").mockRejectedValue(new Error("offline"));
    vi.spyOn(api, "gmNotes").mockResolvedValue({
      campaign: "Amber road mystery",
      other: "",
      version: 1,
      npcs: [],
    });
    render(<HostDashboard snapshot={gmSnapshot} refresh={vi.fn()} />);

    await userEvent.click(screen.getByRole("button", { name: "Заметки" }));

    expect(
      await screen.findByDisplayValue("Amber road mystery"),
    ).toBeInTheDocument();
  });

  it("shows reconnect state without relying on color", () => {
    render(<ConnectionBadge state="reconnecting" />);
    expect(screen.getByRole("status")).toHaveTextContent("Переподключение");
  });

  it("shows a useful conflict message", () => {
    render(
      <ErrorNotice
        error={new ApiError(409, "state_conflict", "Stale version", {})}
      />,
    );
    expect(screen.getByRole("alert")).toHaveTextContent("Данные изменились");
    expect(screen.getByRole("alert")).toHaveTextContent("Обновите состояние");
  });

  it("discards inventory only after server acknowledgement", async () => {
    vi.spyOn(api, "characterOptions").mockResolvedValue({
      races: [],
      classes: [],
      abilities: [],
    });
    vi.spyOn(api, "character").mockResolvedValue(character);
    vi.spyOn(api, "discardItem").mockResolvedValue({
      data: { ...character, inventory: [], version: 3 },
      meta: { replayed: false },
    });
    render(<PlayerDashboard snapshot={playerSnapshot} refresh={vi.fn()} />);
    await userEvent.click(screen.getByRole("button", { name: "Персонаж" }));
    await screen.findByText("Rope");
    await userEvent.click(screen.getByRole("button", { name: "Удалить 1" }));
    await waitFor(() =>
      expect(screen.getByText("Инвентарь пуст.")).toBeInTheDocument(),
    );
  });

  it("shows Russian stats and editable abilities without a checkbox table", async () => {
    vi.spyOn(api, "characterOptions").mockResolvedValue({
      races: [{ id: "human", name: "Человек", description: "", hp_bonus: 0 }],
      classes: [
        {
          id: "fighter",
          name: "Воин",
          description: "",
          base_hp: 10,
          base_armor_class: 14,
        },
      ],
      abilities: character.abilities,
    });
    vi.spyOn(api, "character").mockResolvedValue(character);
    render(
      <HostCharactersPanel
        snapshot={{
          ...gmSnapshot,
          characters: [{ ...character, owner_name: "Mira", selected: true }],
        }}
        refresh={vi.fn()}
      />,
    );

    await userEvent.click(screen.getByRole("button", { name: /Aria/ }));
    expect(await screen.findByText("Сила")).toBeInTheDocument();
    expect(screen.getByText("Харизма")).toBeInTheDocument();
    expect(screen.queryByRole("checkbox")).not.toBeInTheDocument();
    expect(screen.getAllByRole("button", { name: "Удалить" })).not.toHaveLength(
      0,
    );
    expect(
      screen.getByRole("button", { name: "Добавить способность" }),
    ).toBeInTheDocument();
    expect(screen.queryByText("Бонус владения")).not.toBeInTheDocument();
    expect(screen.queryByText("Тёмное зрение")).not.toBeInTheDocument();
  });

  it("renders the character preview with the ready sheet structure", () => {
    render(
      <CharacterSheet
        snapshot={playerSnapshot}
        initial={character}
        options={{
          races: [
            {
              id: "human",
              name: "Человек",
              description: "Люди приспосабливаются к любым условиям.",
              hp_bonus: 0,
            },
          ],
          classes: [],
          abilities: [],
        }}
        onRefresh={vi.fn()}
        preview
        onConfirm={vi.fn()}
      />,
    );
    expect(screen.getByText("Сила")).toBeInTheDocument();
    expect(screen.getByText("Харизма")).toBeInTheDocument();
    expect(screen.getByRole("button", { name: "Человек" })).toBeInTheDocument();
    expect(
      screen.getByRole("button", { name: "Подтвердить персонажа" }),
    ).toBeInTheDocument();
    expect(screen.queryByText("Бонус владения")).not.toBeInTheDocument();
    expect(screen.queryByText("Тёмное зрение")).not.toBeInTheDocument();
  });

  it("updates the character view immediately after archiving", async () => {
    const refresh = vi.fn();
    vi.spyOn(api, "characterOptions").mockResolvedValue({
      races: [],
      classes: [],
      abilities: [],
    });
    vi.spyOn(api, "character").mockResolvedValue(character);
    vi.spyOn(api, "changeCharacterLifecycle").mockResolvedValue({
      data: { ...character, archived_at: "2026-09-05T00:00:00Z", version: 3 },
      meta: { replayed: false },
    });
    render(<PlayerDashboard snapshot={playerSnapshot} refresh={refresh} />);
    await userEvent.click(screen.getByRole("button", { name: "Персонаж" }));
    await screen.findByRole("heading", { name: "Aria" });
    await userEvent.click(
      screen.getByRole("button", { name: "Архивировать персонажа" }),
    );
    await userEvent.click(screen.getByRole("button", { name: "Архивировать" }));

    await waitFor(() =>
      expect(api.changeCharacterLifecycle).toHaveBeenCalled(),
    );
    expect(refresh).toHaveBeenCalled();
    expect(document.querySelector(".character-sheet")).not.toBeInTheDocument();
  });

  it("clears the active character before opening the creation flow", async () => {
    vi.spyOn(api, "characterOptions").mockResolvedValue({
      races: [{ id: "human", name: "Человек", description: "", hp_bonus: 0 }],
      classes: [
        {
          id: "fighter",
          name: "Воин",
          description: "",
          base_hp: 10,
          base_armor_class: 14,
        },
      ],
      abilities: [],
    });
    vi.spyOn(api, "character").mockResolvedValue(character);
    vi.spyOn(api, "clearCharacterSelection").mockResolvedValue({
      data: {
        ...playerSnapshot.player!,
        selected_character_id: null,
        version: 3,
      },
      meta: { replayed: false },
    });
    render(<PlayerDashboard snapshot={playerSnapshot} refresh={vi.fn()} />);
    await userEvent.click(screen.getByRole("button", { name: "Персонаж" }));
    await screen.findByRole("heading", { name: "Aria" });
    await userEvent.click(
      screen.getByRole("button", { name: "Личный кабинет" }),
    );
    await userEvent.click(
      screen.getByRole("button", { name: "Создать нового" }),
    );

    await waitFor(() => expect(api.clearCharacterSelection).toHaveBeenCalled());
    expect(screen.getByLabelText("Имя нового персонажа")).toBeInTheDocument();
    expect(document.querySelector(".character-sheet")).not.toBeInTheDocument();
    expect(screen.queryByText("Персонаж не выбран")).not.toBeInTheDocument();
  });

  it("lets a player save current and temporary HP", async () => {
    vi.spyOn(api, "updateOwnCharacterHealth").mockResolvedValue({
      data: { ...character, current_hp: 7, temporary_hp: 3, version: 3 },
      meta: { replayed: false },
    });
    render(
      <CharacterSheet
        snapshot={playerSnapshot}
        initial={character}
        onRefresh={vi.fn()}
      />,
    );
    await userEvent.clear(screen.getByLabelText("Текущие HP"));
    await userEvent.type(screen.getByLabelText("Текущие HP"), "7");
    await userEvent.clear(screen.getByLabelText("Временные HP"));
    await userEvent.type(screen.getByLabelText("Временные HP"), "3");
    await userEvent.click(screen.getByRole("button", { name: "Сохранить HP" }));

    await waitFor(() =>
      expect(api.updateOwnCharacterHealth).toHaveBeenCalledWith(
        "player-device",
        character,
        7,
        3,
      ),
    );
    expect(screen.getByText("7/20 HP")).toBeInTheDocument();
    expect(screen.getByText("Временные HP 3")).toBeInTheDocument();
  });

  it("lets a player organize and edit private notes", async () => {
    vi.spyOn(api, "characterOptions").mockResolvedValue({
      races: [],
      classes: [],
      abilities: [],
    });
    vi.spyOn(api, "playerNotes").mockResolvedValue({ nodes: [] });
    let version = 1;
    vi.spyOn(api, "createPlayerNoteNode").mockImplementation(
      async (_deviceId, kind, name, parentId) => ({
        data: {
          id: `${kind}-${name}`,
          room_id: "room",
          player_id: "player",
          parent_id: parentId,
          kind,
          name,
          body: "",
          depth: parentId ? 1 : 0,
          version: version++,
        },
        meta: { replayed: false },
      }),
    );
    vi.spyOn(api, "updatePlayerNoteNode").mockImplementation(
      async (_deviceId, node) => ({
        data: { ...node, version: node.version + 1 },
        meta: { replayed: false },
      }),
    );
    render(<PlayerDashboard snapshot={playerSnapshot} refresh={vi.fn()} />);
    await userEvent.click(screen.getByRole("button", { name: "Заметки" }));
    expect(
      await screen.findByRole("heading", { name: "Личные заметки" }),
    ).toBeVisible();

    await userEvent.click(screen.getByText("Настройки"));
    await userEvent.click(screen.getByLabelText("Скрыть создание каталогов"));
    expect(
      screen.queryByRole("button", { name: "Создать каталог" }),
    ).not.toBeInTheDocument();
    await userEvent.click(screen.getByLabelText("Скрыть создание каталогов"));

    await userEvent.click(
      screen.getByRole("button", { name: "Создать каталог" }),
    );
    await userEvent.type(
      screen.getByLabelText("Название каталога"),
      "Кампания",
    );
    await userEvent.click(screen.getByRole("button", { name: /^Создать$/ }));
    expect(await screen.findByText("Кампания")).toBeInTheDocument();

    await userEvent.click(
      screen.getAllByRole("button", { name: "Создать заметку" })[0],
    );
    await userEvent.type(screen.getByLabelText("Название заметки"), "Зацепки");
    await userEvent.click(screen.getByRole("button", { name: /^Создать$/ }));
    await userEvent.click(
      screen.getByRole("button", { name: "Редактировать" }),
    );
    await userEvent.type(
      screen.getByLabelText("Текст заметки"),
      "След ведёт в башню.",
    );
    await userEvent.click(screen.getByRole("button", { name: "Сохранить" }));
    await userEvent.click(screen.getByRole("button", { name: /Зацепки/ }));
    expect(await screen.findByText("След ведёт в башню.")).toBeInTheDocument();
  });

  it("starts the simple character flow", async () => {
    const withoutCharacter = {
      ...playerSnapshot,
      player: { ...playerSnapshot.player!, selected_character_id: null },
      characters: [],
    };
    vi.spyOn(api, "characterOptions").mockResolvedValue({
      races: [
        { id: "human", name: "Human", description: "Adaptable", hp_bonus: 0 },
      ],
      classes: [
        {
          id: "fighter",
          name: "Fighter",
          description: "Martial",
          base_hp: 10,
          base_armor_class: 14,
        },
      ],
      abilities: [],
    });
    vi.spyOn(api, "startDraft").mockResolvedValue({
      data: {
        id: "draft",
        name: "Aria",
        race_id: "human",
        class_id: "fighter",
        offered_cards: [
          { id: "swift", name: "Swift", description: "Fast", kind: "talent" },
        ],
        chosen_cards: [],
        completed_rounds: 0,
        required_rounds: 4,
        ready_to_confirm: false,
        version: 1,
      },
      meta: { replayed: false },
    });
    render(<PlayerDashboard snapshot={withoutCharacter} refresh={vi.fn()} />);
    await userEvent.click(
      screen.getByRole("button", { name: "Личный кабинет" }),
    );
    await userEvent.type(
      screen.getByLabelText(/имя нового персонажа/i),
      "Aria",
    );
    await userEvent.click(
      screen.getByRole("button", { name: /перейти к способностям/i }),
    );
    expect(await screen.findByText("Swift")).toBeInTheDocument();
  });

  it("lets the GM resolve damage against selected combatants", async () => {
    vi.spyOn(api, "applyHealth").mockResolvedValue({
      data: { event_id: "event" },
      meta: { replayed: false },
    });
    render(
      <HostCombatPanel
        snapshot={{ ...gmSnapshot, combat }}
        refresh={vi.fn()}
      />,
    );
    await userEvent.click(document.querySelector(".initiative")!);
    await userEvent.clear(screen.getByLabelText("Величина эффекта"));
    await userEvent.type(screen.getByLabelText("Величина эффекта"), "4");
    await userEvent.click(screen.getByRole("button", { name: "Нанести урон" }));
    await waitFor(() =>
      expect(api.applyHealth).toHaveBeenCalledWith(
        combat,
        "gm-device",
        ["goblin"],
        "damage",
        4,
        false,
      ),
    );
  });

  it("finishes adding selected characters when there is nothing new to add", async () => {
    const refresh = vi.fn();
    render(
      <HostCombatPanel
        snapshot={{ ...gmSnapshot, combat }}
        refresh={refresh}
      />,
    );

    await userEvent.click(document.querySelector(".combat-setup > button")!);

    await waitFor(() => expect(refresh).toHaveBeenCalled());
    expect(
      screen.queryByText(/Cannot read properties/),
    ).not.toBeInTheDocument();
  });

  it("shows a player exact own HP but only a monster wound category", () => {
    render(
      <PlayerCombatPanel
        snapshot={{ ...playerSnapshot, combat }}
        refresh={vi.fn()}
      />,
    );
    expect(screen.getByText("15/20 HP + 3 временных")).toBeInTheDocument();
    expect(screen.getByText("ранен")).toBeInTheDocument();
    expect(screen.queryByText("?/ ? HP")).not.toBeInTheDocument();
  });
});
