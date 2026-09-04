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
  persistent?: boolean;
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
  values: number[];
  selection: "neutral" | "advantage" | "disadvantage";
  attempts: number[][];
  attempt_totals: number[];
  selected_attempt: number;
  created_at: string;
  actor_name?: string;
}

export interface MonsterTemplate {
  id: string;
  name: string;
  max_hp: number;
  current_hp: number;
  armor_class: number;
  conditions: string[];
  actions: string[];
  image_url?: string | null;
  notes?: string;
  species?: string;
  abilities?: string;
  damage?: string;
  items?: string;
}

export interface CombatState {
  id: string;
  name?: string;
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
  class_ids?: string[];
  required_stats?: Record<string, number>;
  required_ability_ids?: string[];
}

export interface CharacterOption {
  id: string;
  name: string;
  description: string;
}

export interface CharacterOptions {
  races: (CharacterOption & { hp_bonus: number })[];
  classes: (CharacterOption & {
    base_hp: number;
    base_armor_class: number;
  })[];
  abilities: AbilityCard[];
  class_details?: Array<{
    id: string;
    name: string;
    theme: string;
    primary_stat: string;
    difficulty: string;
    hit_die: number;
  }>;
  species?: Array<{
    id: string;
    name: string;
    description: string;
    source_url: string;
    creature_type: string;
    sizes: string[];
    speed: number;
    lineages: string[];
    features: Array<{
      id: string;
      name: string;
      description: string;
      required_level: number;
    }>;
  }>;
  stats?: Array<{ id: string; name: string; description: string }>;
}

export interface CharacterDraft {
  id: string;
  name: string;
  race_id: string;
  class_id: string;
  offered_cards: AbilityCard[];
  chosen_cards: AbilityCard[];
  completed_rounds: number;
  required_rounds: number;
  ready_to_confirm: boolean;
  version: number;
  stats?: Record<string, number>;
  base_stats?: Record<string, number>;
  species_choices?: Record<string, string>;
  persistent_conditions?: Array<Record<string, unknown>>;
  stat_method?: "standard" | "random" | "point_buy";
  random_rolls?: Array<{
    values: number[];
    dropped_index: number;
    total: number;
  }>;
}

export interface InventoryItem {
  id: string;
  name: string;
  quantity: number;
  consumable: boolean;
  locked: boolean;
  unit_weight?: string;
  slot_compatibility?: "hand" | "armor" | "other" | "none";
  equipment_slot?: string | null;
}

export interface Character {
  id: string;
  name: string;
  race_id: string;
  class_id: string;
  max_hp: number;
  current_hp: number;
  armor_class: number;
  owner_id: string;
  stats: Record<string, number>;
  abilities: AbilityCard[];
  inventory: InventoryItem[];
  version: number;
  level?: number;
  experience?: number;
  temporary_hp?: number;
  initiative?: number;
  proficiency_bonus?: number;
  size?: string;
  speed?: number;
  darkvision?: number;
  species_choices?: Record<string, string>;
  persistent_conditions?: Array<Record<string, unknown>>;
  total_weight?: string;
  archived_at?: string | null;
}

export interface CharacterSummary {
  id: string;
  name: string;
  version: number;
  selected: boolean;
  race_id?: string;
  class_id?: string;
  max_hp?: number;
  current_hp?: number;
  armor_class?: number;
  owner_id?: string;
  owner_name?: string;
}

export interface NpcNote {
  id: string;
  room_id: string;
  name: string;
  details: string;
  version: number;
}

export interface GmNotes {
  campaign: string;
  other: string;
  version: number;
  npcs: NpcNote[];
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
  dice_rolls?: DiceRoll[];
  archived_characters?: CharacterSummary[];
  encounters?: CombatState[];
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

function newId(): string {
  if (typeof crypto.randomUUID === "function") return crypto.randomUUID();

  const bytes = crypto.getRandomValues(new Uint8Array(16));
  bytes[6] = (bytes[6] & 0x0f) | 0x40;
  bytes[8] = (bytes[8] & 0x3f) | 0x80;
  const hex = Array.from(bytes, (byte) => byte.toString(16).padStart(2, "0"));
  return [
    hex.slice(0, 4).join(""),
    hex.slice(4, 6).join(""),
    hex.slice(6, 8).join(""),
    hex.slice(8, 10).join(""),
    hex.slice(10, 16).join(""),
  ].join("-");
}

export function installationId(): string {
  const key = "ttc-device-installation";
  const stored = sessionStorage.getItem(key);
  if (stored) return stored;
  const value = newId();
  sessionStorage.setItem(key, value);
  return value;
}

export function commandMeta(deviceId = installationId()) {
  return { command_id: newId(), device_id: deviceId };
}

async function request<T>(path: string, init?: RequestInit): Promise<T> {
  const isFormData = init?.body instanceof FormData;
  const response = await fetch(path, {
    ...init,
    credentials: "same-origin",
    headers: isFormData
      ? init?.headers
      : { "Content-Type": "application/json", ...init?.headers },
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
          gm_id: newId(),
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
  createWifiQr: (
    roomId: string,
    input: {
      ssid: string;
      security: "WPA" | "WEP" | "nopass";
      password: string;
    },
  ) =>
    request<{ qr_data_url: string }>(`/api/v2/rooms/${roomId}/wifi-qr`, {
      method: "POST",
      body: JSON.stringify(input),
    }),
  uploadMedia: (roomId: string, file: File) => {
    return request<{ url: string }>(`/api/v2/rooms/${roomId}/media`, {
      method: "POST",
      body: file,
      headers: {
        "Content-Type": file.type,
        "X-Upload-Filename": file.name,
      },
    });
  },
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
    request<CommandResponse<{ player: Player; device: Device }>>(
      "/api/v2/me/profile",
      {
        method: "POST",
        body: JSON.stringify({
          ...commandMeta(deviceId),
          display_name: input.displayName,
          password: input.password || null,
          invitation_token: input.invitationToken || null,
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
  characterOptions: () =>
    request<CharacterOptions>("/api/v2/character-options"),
  startDraft: (
    deviceId: string,
    name: string,
    raceId: string,
    classId: string,
    configuration?: {
      species_choices: Record<string, string>;
      stat_method: "standard" | "random" | "point_buy";
      stats: Record<string, number>;
      background_pattern: "2+1" | "1+1+1";
      background_stats: [string, string, string];
      background_allocations: Record<string, number>;
    },
  ) =>
    request<CommandResponse<CharacterDraft>>("/api/v2/me/character-drafts", {
      method: "POST",
      body: JSON.stringify({
        ...commandMeta(deviceId),
        name,
        race_id: raceId,
        class_id: classId,
        ...configuration,
      }),
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
  kickPlayer: (roomId: string, playerId: string, deviceId: string) =>
    request<CommandResponse<{ player_id: string; device_ids: string[] }>>(
      `/api/v2/rooms/${roomId}/players/${playerId}`,
      { method: "DELETE", body: JSON.stringify(commandMeta(deviceId)) },
    ),
  updateCharacter: (roomId: string, deviceId: string, character: Character) =>
    request<CommandResponse<Character>>(
      `/api/v2/rooms/${roomId}/characters/${character.id}`,
      {
        method: "PUT",
        body: JSON.stringify({
          ...commandMeta(deviceId),
          name: character.name,
          race_id: character.race_id,
          class_id: character.class_id,
          stats: character.stats,
          ability_ids: character.abilities.map((ability) => ability.id),
          max_hp: character.max_hp,
          current_hp: character.current_hp,
          armor_class: character.armor_class,
          temporary_hp: character.temporary_hp ?? 0,
          level: character.level ?? 1,
          experience: character.experience ?? 0,
          initiative: character.initiative ?? 0,
          proficiency_bonus: character.proficiency_bonus ?? 2,
          size: character.size ?? "medium",
          speed: character.speed ?? 30,
          darkvision: character.darkvision ?? 0,
          species_choices: character.species_choices ?? {},
          persistent_conditions: character.persistent_conditions ?? [],
          expected_version: character.version,
        }),
      },
    ),
  gmAddItem: (
    roomId: string,
    deviceId: string,
    character: Character,
    name: string,
  ) =>
    request<CommandResponse<Character>>(
      `/api/v2/rooms/${roomId}/characters/${character.id}/inventory`,
      {
        method: "POST",
        body: JSON.stringify({
          ...commandMeta(deviceId),
          actor_id: deviceId,
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
  gmDiscardItem: (
    roomId: string,
    deviceId: string,
    character: Character,
    item: InventoryItem,
  ) =>
    request<CommandResponse<Character>>(
      `/api/v2/rooms/${roomId}/characters/${character.id}/inventory/${item.id}/discard`,
      {
        method: "POST",
        body: JSON.stringify({
          ...commandMeta(deviceId),
          actor_id: deviceId,
          quantity: item.quantity,
          expected_version: character.version,
        }),
      },
    ),
  gmNotes: (roomId: string) =>
    request<GmNotes>(`/api/v2/rooms/${roomId}/notes`),
  updateGmNotes: (roomId: string, deviceId: string, notes: GmNotes) =>
    request<CommandResponse<Omit<GmNotes, "npcs">>>(
      `/api/v2/rooms/${roomId}/notes`,
      {
        method: "PUT",
        body: JSON.stringify({
          ...commandMeta(deviceId),
          campaign: notes.campaign,
          other: notes.other,
          expected_version: notes.version,
        }),
      },
    ),
  createNpcNote: (roomId: string, deviceId: string, name: string) =>
    request<CommandResponse<NpcNote>>(`/api/v2/rooms/${roomId}/notes/npcs`, {
      method: "POST",
      body: JSON.stringify({ ...commandMeta(deviceId), name }),
    }),
  updateNpcNote: (roomId: string, deviceId: string, npc: NpcNote) =>
    request<CommandResponse<NpcNote>>(
      `/api/v2/rooms/${roomId}/notes/npcs/${npc.id}`,
      {
        method: "PUT",
        body: JSON.stringify({
          ...commandMeta(deviceId),
          name: npc.name,
          details: npc.details,
          expected_version: npc.version,
        }),
      },
    ),
  deleteNpcNote: (roomId: string, deviceId: string, npcId: string) =>
    request<CommandResponse<{ npc_id: string; deleted: boolean }>>(
      `/api/v2/rooms/${roomId}/notes/npcs/${npcId}`,
      { method: "DELETE", body: JSON.stringify(commandMeta(deviceId)) },
    ),
  addItem: (
    deviceId: string,
    playerId: string,
    character: Character,
    name: string,
    unitWeight = "0",
    slotCompatibility: InventoryItem["slot_compatibility"] = "none",
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
          unit_weight: unitWeight,
          slot_compatibility: slotCompatibility,
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
  equipItem: (
    deviceId: string,
    playerId: string,
    character: Character,
    item: InventoryItem,
    slot: string | null,
  ) =>
    request<CommandResponse<Character>>(
      `/api/v2/characters/${character.id}/inventory/${item.id}/equipment`,
      {
        method: "POST",
        body: JSON.stringify({
          ...commandMeta(deviceId),
          actor_id: playerId,
          slot,
          expected_version: character.version,
        }),
      },
    ),
  changeCharacterLifecycle: (
    deviceId: string,
    character: Character | CharacterSummary,
    action: "assign" | "archive" | "restore",
  ) =>
    request<CommandResponse<Character>>(
      `/api/v2/me/characters/${character.id}/lifecycle`,
      {
        method: "POST",
        body: JSON.stringify({
          ...commandMeta(deviceId),
          action,
          expected_version: character.version,
        }),
      },
    ),
  createCombat: (
    roomId: string,
    sessionId: string,
    deviceId: string,
    name = "Энкаунтер",
  ) =>
    request<CommandResponse<CombatState>>(
      `/api/v2/rooms/${roomId}/sessions/${sessionId}/combats`,
      {
        method: "POST",
        body: JSON.stringify({ ...commandMeta(deviceId), name }),
      },
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
    input: {
      name: string;
      hp: number;
      armorClass: number;
      imageUrl?: string;
      notes?: string;
      species?: string;
      abilities?: string;
      damage?: string;
      items?: string;
    },
  ) =>
    request<CommandResponse<MonsterTemplate>>(
      `/api/v2/rooms/${roomId}/monster-templates`,
      {
        method: "POST",
        body: JSON.stringify({
          ...commandMeta(deviceId),
          name: input.name,
          image_url: input.imageUrl || null,
          max_hp: input.hp,
          current_hp: input.hp,
          armor_class: input.armorClass,
          notes: input.notes ?? "",
          conditions: [],
          actions: [],
          species: input.species ?? "",
          abilities: input.abilities ?? "",
          damage: input.damage ?? "",
          items: input.items ?? "",
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
    persistent = false,
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
          persistent,
        }),
      },
    ),
  rollCombat: (
    combat: CombatState,
    deviceId: string,
    actorIds: string[],
    expression: string,
    visibility: DiceRoll["visibility"] = "public",
    selection: DiceRoll["selection"] = "neutral",
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
          selection,
        }),
      },
    ),
  rollRoom: (
    roomId: string,
    deviceId: string,
    expression: string,
    selection: DiceRoll["selection"],
  ) =>
    request<CommandResponse<{ roll: DiceRoll }>>(
      `/api/v2/rooms/${roomId}/rolls`,
      {
        method: "POST",
        body: JSON.stringify({
          ...commandMeta(deviceId),
          expression,
          selection,
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
