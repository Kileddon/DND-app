import { render, screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { afterEach, describe, expect, it, vi } from "vitest";

import { ApiError, api, type Character, type Snapshot } from "./api";
import { ConnectionBadge } from "./components/ConnectionBadge";
import { WelcomeScreen } from "./components/EntryScreens";
import { ErrorNotice } from "./components/ErrorNotice";
import { HostDashboard } from "./components/HostDashboard";
import { PlayerDashboard } from "./components/PlayerDashboard";

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
  stats: { might: 2, mind: 3 },
  abilities: [],
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

afterEach(() => vi.restoreAllMocks());

describe("local multiplayer interface", () => {
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
    vi.spyOn(api, "character").mockResolvedValue(character);
    vi.spyOn(api, "discardItem").mockResolvedValue({
      data: { ...character, inventory: [], version: 3 },
      meta: { replayed: false },
    });
    render(<PlayerDashboard snapshot={playerSnapshot} refresh={vi.fn()} />);
    await screen.findByText("Rope");
    await userEvent.click(screen.getByRole("button", { name: "Удалить 1" }));
    await waitFor(() =>
      expect(screen.getByText("Инвентарь пуст.")).toBeInTheDocument(),
    );
  });

  it("starts the simple character flow", async () => {
    const withoutCharacter = {
      ...playerSnapshot,
      player: { ...playerSnapshot.player!, selected_character_id: null },
      characters: [],
    };
    vi.spyOn(api, "startDraft").mockResolvedValue({
      data: {
        id: "draft",
        name: "Aria",
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
    await userEvent.type(
      screen.getByLabelText(/имя нового персонажа/i),
      "Aria",
    );
    await userEvent.click(
      screen.getByRole("button", { name: /начать простой конструктор/i }),
    );
    expect(await screen.findByText("Swift")).toBeInTheDocument();
  });
});
