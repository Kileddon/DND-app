export type ConnectionState =
  "connecting" | "online" | "reconnecting" | "offline";

export interface Room {
  id: string;
  name: string;
  code: string;
  access_mode: "open" | "password" | "invitation";
}

export interface Device {
  id: string;
  room_id: string;
  player_id: string | null;
  label: string;
  role: "gm" | "player";
  status: "active" | "revoked";
  last_seen_at: string;
  connection_state?: string;
  connection_count?: number;
}

export interface Player {
  id: string;
  room_id: string;
  display_name: string;
  selected_character_id: string | null;
  version: number;
}

export interface GameSession {
  id: string;
  room_id: string;
  status: "PREPARATION" | "LOBBY" | "ACTIVE" | "PAUSED" | "COMPLETED";
  version: number;
}

export interface AbilityCard {
  id: string;
  name: string;
  description: string;
  kind: string;
}

export interface CharacterDraft {
  id: string;
  name: string;
  offered_cards: AbilityCard[];
  chosen_cards: AbilityCard[];
  completed_rounds: number;
  required_rounds: number;
  ready_to_confirm: boolean;
  version: number;
}

export interface InventoryItem {
  id: string;
  name: string;
  quantity: number;
  consumable: boolean;
  locked: boolean;
}

export interface Character {
  id: string;
  name: string;
  owner_id: string;
  stats: Record<string, number>;
  abilities: AbilityCard[];
  inventory: InventoryItem[];
  version: number;
}

export interface CharacterSummary {
  id: string;
  name: string;
  version: number;
  selected: boolean;
}

export interface Snapshot {
  cursor: number;
  room: Room;
  session: GameSession | null;
  current_device_id: string;
  device?: Device;
  players?: Player[];
  devices?: Device[];
  player?: Player | null;
  characters?: CharacterSummary[];
}

export interface Diagnostics {
  hostname: string;
  addresses: string[];
  port: number;
  api_available: boolean;
  access_policy: string;
  websocket_connections: number;
  reconnecting_clients: number;
  players: number;
  devices: number;
  event_cursor: number;
  sqlite_bytes: number;
  sqlite_journal_mode: string;
  free_disk_bytes: number;
  uptime_seconds: number;
  backend_version: string;
  frontend_version: string;
  database_revision: string;
}

interface CommandResponse<T> {
  data: T;
  meta: { replayed: boolean };
}

interface ApiErrorBody {
  error?: {
    code?: string;
    message?: string;
    details?: Record<string, unknown>;
  };
}

export class ApiError extends Error {
  constructor(
    readonly status: number,
    readonly code: string,
    message: string,
    readonly details: Record<string, unknown>,
  ) {
    super(message);
  }
}

export function installationId(): string {
  const key = "ttc-device-installation";
  const stored = sessionStorage.getItem(key);
  if (stored) return stored;
  const value = crypto.randomUUID();
  sessionStorage.setItem(key, value);
  return value;
}

export function commandMeta(deviceId = installationId()) {
  return { command_id: crypto.randomUUID(), device_id: deviceId };
}

async function request<T>(path: string, init?: RequestInit): Promise<T> {
  const response = await fetch(path, {
    ...init,
    credentials: "same-origin",
    headers: { "Content-Type": "application/json", ...init?.headers },
  });
  if (!response.ok) {
    const body = (await response.json().catch(() => ({}))) as ApiErrorBody;
    throw new ApiError(
      response.status,
      body.error?.code ?? "request_failed",
      body.error?.message ?? "Сервер не смог выполнить запрос.",
      body.error?.details ?? {},
    );
  }
  return (await response.json()) as T;
}

export const api = {
  snapshot: () => request<Snapshot>("/api/v2/me/snapshot"),
  diagnostics: () => request<Diagnostics>("/api/v2/host/diagnostics"),
  bootstrap: (input: {
    name: string;
    accessMode: Room["access_mode"];
    password?: string;
  }) =>
    request<CommandResponse<{ room: Room; device: Device }>>(
      "/api/v2/host/rooms",
      {
        method: "POST",
        body: JSON.stringify({
          ...commandMeta(),
          gm_id: crypto.randomUUID(),
          name: input.name,
          access_mode: input.accessMode,
          password: input.password || null,
          device_label: "GM laptop",
        }),
      },
    ),
  createPairing: (
    roomId: string,
    deviceId: string,
    role: "player" | "gm" = "player",
  ) =>
    request<
      CommandResponse<{
        id: string;
        short_code: string;
        pair_url: string;
        qr_data_url: string;
        expires_at: string;
      }>
    >(`/api/v2/rooms/${roomId}/pairing`, {
      method: "POST",
      body: JSON.stringify({
        ...commandMeta(deviceId),
        ttl_seconds: 300,
        role,
      }),
    }),
  revokePairing: (roomId: string, invitationId: string, deviceId: string) =>
    request<CommandResponse<{ revoked: number }>>(
      `/api/v2/rooms/${roomId}/pairing/${invitationId}`,
      {
        method: "DELETE",
        body: JSON.stringify(commandMeta(deviceId)),
      },
    ),
  createRoomInvitation: (roomId: string, deviceId: string) =>
    request<CommandResponse<{ invitation_token: string; expires_at: string }>>(
      `/api/v2/rooms/${roomId}/invitations`,
      {
        method: "POST",
        body: JSON.stringify({
          ...commandMeta(deviceId),
          ttl_seconds: 3600,
          max_uses: 1,
        }),
      },
    ),
  revokeDevice: (roomId: string, targetDeviceId: string, deviceId: string) =>
    request<CommandResponse<Device>>(
      `/api/v2/rooms/${roomId}/devices/${targetDeviceId}`,
      {
        method: "DELETE",
        body: JSON.stringify(commandMeta(deviceId)),
      },
    ),
  exchangePairing: (input: { token?: string; shortCode?: string }) =>
    request<CommandResponse<{ device: Device }>>("/api/v2/pairing/exchange", {
      method: "POST",
      body: JSON.stringify({
        ...commandMeta(),
        token: input.token ?? null,
        short_code: input.shortCode ?? null,
        device_label: navigator.userAgent.includes("Mobile")
          ? "Mobile browser"
          : "Browser",
      }),
    }),
  createProfile: (
    deviceId: string,
    input: { displayName: string; password?: string; invitationToken?: string },
  ) =>
    request<
      CommandResponse<{ player: Player; device: Device; recovery_code: string }>
    >("/api/v2/me/profile", {
      method: "POST",
      body: JSON.stringify({
        ...commandMeta(deviceId),
        display_name: input.displayName,
        password: input.password || null,
        invitation_token: input.invitationToken || null,
      }),
    }),
  recoverProfile: (deviceId: string, playerId: string, recoveryCode: string) =>
    request<CommandResponse<{ player: Player; device: Device }>>(
      "/api/v2/me/profile/recover",
      {
        method: "POST",
        body: JSON.stringify({
          ...commandMeta(deviceId),
          player_id: playerId,
          recovery_code: recoveryCode,
        }),
      },
    ),
  createSession: (roomId: string, deviceId: string) =>
    request<CommandResponse<GameSession>>(`/api/v2/rooms/${roomId}/sessions`, {
      method: "POST",
      body: JSON.stringify(commandMeta(deviceId)),
    }),
  transitionSession: (
    roomId: string,
    session: GameSession,
    target: GameSession["status"],
    deviceId: string,
  ) =>
    request<CommandResponse<GameSession>>(
      `/api/v2/rooms/${roomId}/sessions/${session.id}/transition`,
      {
        method: "POST",
        body: JSON.stringify({
          ...commandMeta(deviceId),
          target_status: target,
          expected_version: session.version,
        }),
      },
    ),
  startDraft: (deviceId: string, name: string) =>
    request<CommandResponse<CharacterDraft>>("/api/v2/me/character-drafts", {
      method: "POST",
      body: JSON.stringify({ ...commandMeta(deviceId), name }),
    }),
  chooseCard: (deviceId: string, draft: CharacterDraft, cardId: string) =>
    request<CommandResponse<CharacterDraft>>(
      `/api/v2/character-drafts/${draft.id}/choices`,
      {
        method: "POST",
        body: JSON.stringify({
          ...commandMeta(deviceId),
          card_id: cardId,
          expected_version: draft.version,
        }),
      },
    ),
  confirmDraft: (deviceId: string, draft: CharacterDraft) =>
    request<CommandResponse<Character>>(
      `/api/v2/character-drafts/${draft.id}/confirm`,
      {
        method: "POST",
        body: JSON.stringify({
          ...commandMeta(deviceId),
          expected_version: draft.version,
        }),
      },
    ),
  selectCharacter: (deviceId: string, player: Player, characterId: string) =>
    request<CommandResponse<Player>>(
      `/api/v2/me/characters/${characterId}/select`,
      {
        method: "POST",
        body: JSON.stringify({
          ...commandMeta(deviceId),
          character_id: characterId,
          expected_version: player.version,
        }),
      },
    ),
  character: (id: string) => request<Character>(`/api/v2/characters/${id}`),
  addItem: (
    deviceId: string,
    playerId: string,
    character: Character,
    name: string,
  ) =>
    request<CommandResponse<Character>>(
      `/api/v2/characters/${character.id}/inventory`,
      {
        method: "POST",
        body: JSON.stringify({
          ...commandMeta(deviceId),
          actor_id: playerId,
          name,
          quantity: 1,
          consumable: false,
          locked: false,
          equipped: false,
          charges: null,
          expected_version: character.version,
        }),
      },
    ),
  discardItem: (
    deviceId: string,
    playerId: string,
    character: Character,
    item: InventoryItem,
  ) =>
    request<CommandResponse<Character>>(
      `/api/v2/characters/${character.id}/inventory/${item.id}/discard`,
      {
        method: "POST",
        body: JSON.stringify({
          ...commandMeta(deviceId),
          actor_id: playerId,
          quantity: 1,
          expected_version: character.version,
        }),
      },
    ),
};
