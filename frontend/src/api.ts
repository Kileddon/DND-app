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

export interface CombatCondition {
  id: string;
  name: string;
  description: string;
  visible_to_players: boolean;
}

export interface Combatant {
  id: string;
  entry_id: string;
  kind: "character" | "monster";
  reference_id: string | null;
  name: string;
  version: number;
  max_hp?: number;
  current_hp?: number;
  temporary_hp?: number;
  armor_class?: number;
  wound_state?: string | null;
  conditions: CombatCondition[];
}

export interface InitiativeEntry {
  id: string;
  name: string;
  initiative: number;
  position: number;
  combatant_ids: string[];
}

export interface CombatEvent {
  id: string;
  event_type: string;
  occurred_at: string;
  payload: Record<string, unknown>;
}

export interface DiceRoll {
  id: string;
  actor_id: string;
  expression: string;
  result: number;
  original_result: number;
  visibility: "public" | "private" | "secret" | "delayed";
  reason: string | null;
}

export interface MonsterTemplate {
  id: string;
  name: string;
  max_hp: number;
  current_hp: number;
  armor_class: number;
  conditions: string[];
  actions: string[];
}

export interface CombatState {
  id: string;
  room_id: string;
  session_id: string;
  status: "PREPARATION" | "ACTIVE" | "PAUSED" | "COMPLETED";
  round_number: number;
  current_entry_id: string | null;
  version: number;
  entries: InitiativeEntry[];
  combatants: Combatant[];
  monster_templates: MonsterTemplate[];
  rolls: DiceRoll[];
  journal: CombatEvent[];
  report: Record<string, unknown> | null;
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
  combat?: CombatState | null;
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
  createCombat: (roomId: string, sessionId: string, deviceId: string) =>
    request<CommandResponse<CombatState>>(
      `/api/v2/rooms/${roomId}/sessions/${sessionId}/combats`,
      { method: "POST", body: JSON.stringify(commandMeta(deviceId)) },
    ),
  addCombatCharacter: (
    combat: CombatState,
    characterId: string,
    deviceId: string,
    lateJoin = false,
  ) =>
    request<CommandResponse<CombatState>>(
      `/api/v2/rooms/${combat.room_id}/combats/${combat.id}/characters`,
      {
        method: "POST",
        body: JSON.stringify({
          ...commandMeta(deviceId),
          expected_version: combat.version,
          character_id: characterId,
          initiative: 10,
          max_hp: 20,
          current_hp: 20,
          armor_class: 10,
          late_join: lateJoin,
        }),
      },
    ),
  createMonsterTemplate: (
    roomId: string,
    deviceId: string,
    input: { name: string; hp: number; armorClass: number },
  ) =>
    request<CommandResponse<MonsterTemplate>>(
      `/api/v2/rooms/${roomId}/monster-templates`,
      {
        method: "POST",
        body: JSON.stringify({
          ...commandMeta(deviceId),
          name: input.name,
          image_url: null,
          max_hp: input.hp,
          current_hp: input.hp,
          armor_class: input.armorClass,
          notes: "",
          conditions: [],
          actions: [],
        }),
      },
    ),
  addMonsters: (
    combat: CombatState,
    templateId: string,
    deviceId: string,
    count = 1,
  ) =>
    request<CommandResponse<CombatState>>(
      `/api/v2/rooms/${combat.room_id}/combats/${combat.id}/monsters`,
      {
        method: "POST",
        body: JSON.stringify({
          ...commandMeta(deviceId),
          expected_version: combat.version,
          template_id: templateId,
          initiative: 8,
          count,
          grouped: count > 1,
        }),
      },
    ),
  removeCombatEntry: (combat: CombatState, entryId: string, deviceId: string) =>
    request<CommandResponse<CombatState>>(
      `/api/v2/rooms/${combat.room_id}/combats/${combat.id}/entries/${entryId}`,
      {
        method: "DELETE",
        body: JSON.stringify({
          ...commandMeta(deviceId),
          expected_version: combat.version,
        }),
      },
    ),
  reorderCombat: (combat: CombatState, entryIds: string[], deviceId: string) =>
    request<CommandResponse<CombatState>>(
      `/api/v2/rooms/${combat.room_id}/combats/${combat.id}/reorder`,
      {
        method: "POST",
        body: JSON.stringify({
          ...commandMeta(deviceId),
          expected_version: combat.version,
          entry_ids: entryIds,
        }),
      },
    ),
  transitionCombat: (
    combat: CombatState,
    deviceId: string,
    action: "start" | "pause" | "resume" | "complete",
  ) =>
    request<CommandResponse<CombatState>>(
      `/api/v2/rooms/${combat.room_id}/combats/${combat.id}/transition`,
      {
        method: "POST",
        body: JSON.stringify({
          ...commandMeta(deviceId),
          expected_version: combat.version,
          action,
        }),
      },
    ),
  moveTurn: (combat: CombatState, deviceId: string, direction: -1 | 1) =>
    request<CommandResponse<CombatState>>(
      `/api/v2/rooms/${combat.room_id}/combats/${combat.id}/turn`,
      {
        method: "POST",
        body: JSON.stringify({
          ...commandMeta(deviceId),
          expected_version: combat.version,
          direction,
        }),
      },
    ),
  applyHealth: (
    combat: CombatState,
    deviceId: string,
    targetIds: string[],
    action: "damage" | "healing" | "temporary_hp" | "prevention",
    amount: number,
    critical = false,
  ) =>
    request<CommandResponse<{ event_id: string }>>(
      `/api/v2/rooms/${combat.room_id}/combats/${combat.id}/health`,
      {
        method: "POST",
        body: JSON.stringify({
          ...commandMeta(deviceId),
          source_id: null,
          targets: targetIds.map((id) => ({
            target_id: id,
            expected_version: combat.combatants.find((item) => item.id === id)!
              .version,
          })),
          action,
          amount,
          prevented: 0,
          critical,
          roll_id: null,
        }),
      },
    ),
  addCondition: (
    combat: CombatState,
    target: Combatant,
    deviceId: string,
    name: string,
  ) =>
    request<CommandResponse<Combatant>>(
      `/api/v2/rooms/${combat.room_id}/combats/${combat.id}/combatants/${target.id}/conditions`,
      {
        method: "POST",
        body: JSON.stringify({
          ...commandMeta(deviceId),
          expected_version: target.version,
          catalog_id: null,
          name,
          description: "",
          source_id: null,
          visible_to_players: true,
        }),
      },
    ),
  rollCombat: (
    combat: CombatState,
    deviceId: string,
    actorIds: string[],
    expression: string,
    visibility: DiceRoll["visibility"] = "public",
  ) =>
    request<CommandResponse<{ rolls: DiceRoll[] }>>(
      `/api/v2/rooms/${combat.room_id}/combats/${combat.id}/rolls`,
      {
        method: "POST",
        body: JSON.stringify({
          ...commandMeta(deviceId),
          actor_ids: actorIds,
          expression,
          mode: "digital",
          visibility,
          recipient_player_id: null,
          physical_result: null,
          action_event_id: null,
        }),
      },
    ),
  support: (
    combat: CombatState,
    deviceId: string,
    characterId: string,
    description: string,
  ) =>
    request<CommandResponse<{ event_id: string }>>(
      `/api/v2/rooms/${combat.room_id}/combats/${combat.id}/support`,
      {
        method: "POST",
        body: JSON.stringify({
          ...commandMeta(deviceId),
          character_id: characterId,
          description,
          roll_id: null,
        }),
      },
    ),
  cancelCombatEvent: (combat: CombatState, deviceId: string, eventId: string) =>
    request<CommandResponse<Record<string, unknown>>>(
      `/api/v2/rooms/${combat.room_id}/combats/${combat.id}/events/${eventId}/cancel`,
      { method: "POST", body: JSON.stringify(commandMeta(deviceId)) },
    ),
  correctCombatEvent: (
    combat: CombatState,
    deviceId: string,
    eventId: string,
    targetIds: string[],
    action: "damage" | "healing" | "temporary_hp" | "prevention",
    amount: number,
    critical = false,
  ) =>
    request<CommandResponse<Record<string, unknown>>>(
      `/api/v2/rooms/${combat.room_id}/combats/${combat.id}/events/${eventId}/correct`,
      {
        method: "POST",
        body: JSON.stringify({
          ...commandMeta(deviceId),
          source_id: null,
          targets: targetIds.map((id) => ({
            target_id: id,
            expected_version: combat.combatants.find((item) => item.id === id)!
              .version,
          })),
          action,
          amount,
          prevented: 0,
          critical,
          roll_id: null,
        }),
      },
    ),
};
