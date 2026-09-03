import { type FormEvent, useMemo, useState } from "react";

import { api, type CombatState, type Snapshot } from "../api";
import { ErrorNotice } from "./ErrorNotice";

function eventLabel(eventType: string): string {
  const labels: Record<string, string> = {
    HealthChanged: "Изменение здоровья",
    HealthActionCompensated: "Действие отменено",
    HealthActionCorrected: "Действие исправлено",
    DiceRolled: "Бросок кубиков",
    DiceRollEdited: "Бросок исправлен",
    DiceRollRevealed: "Бросок раскрыт",
    SupportDeclared: "Заявка поддержки",
    ConditionAdded: "Состояние добавлено",
    ConditionRemoved: "Состояние снято",
    CombatTurnChanged: "Ход передан",
  };
  return labels[eventType] ?? eventType;
}

function CombatHeader({ combat }: { combat: CombatState }) {
  const current = combat.entries.find(
    (entry) => entry.id === combat.current_entry_id,
  );
  return (
    <div className="combat-heading">
      <div>
        <p className="eyebrow">БОЙ · {combat.status}</p>
        <h2>Раунд {combat.round_number}</h2>
      </div>
      <div className="current-turn">
        <span>Сейчас ходит</span>
        <strong>{current?.name ?? "Бой ещё не начат"}</strong>
      </div>
    </div>
  );
}

export function HostCombatPanel({
  snapshot,
  refresh,
}: {
  snapshot: Snapshot;
  refresh: () => void;
}) {
  const combat = snapshot.combat ?? undefined;
  const [selected, setSelected] = useState<string[]>([]);
  const [amount, setAmount] = useState(1);
  const [monsterName, setMonsterName] = useState("Гоблин");
  const [monsterHp, setMonsterHp] = useState(10);
  const [monsterCount, setMonsterCount] = useState(1);
  const [condition, setCondition] = useState("Сбит с ног");
  const [critical, setCritical] = useState(false);
  const [pending, setPending] = useState("");
  const [error, setError] = useState<unknown>();

  async function run<T>(name: string, operation: () => Promise<T>) {
    setPending(name);
    setError(undefined);
    try {
      const response = await operation();
      refresh();
      return response;
    } catch (reason) {
      setError(reason);
      refresh();
      return undefined;
    } finally {
      setPending("");
    }
  }

  async function create() {
    if (!snapshot.session) return;
    await run("create", () =>
      api.createCombat(
        snapshot.room.id,
        snapshot.session!.id,
        snapshot.current_device_id,
      ),
    );
  }

  async function addSelectedCharacters() {
    if (!combat) return;
    let current = combat;
    for (const player of snapshot.players ?? []) {
      if (!player.selected_character_id) continue;
      if (
        current.combatants.some(
          (item) => item.reference_id === player.selected_character_id,
        )
      )
        continue;
      const response = await api.addCombatCharacter(
        current,
        player.selected_character_id,
        snapshot.current_device_id,
        current.status !== "PREPARATION",
      );
      current = response.data;
    }
    refresh();
  }

  async function addMonster(event: FormEvent) {
    event.preventDefault();
    if (!combat) return;
    await run("monster", async () => {
      const template = await api.createMonsterTemplate(
        snapshot.room.id,
        snapshot.current_device_id,
        { name: monsterName, hp: monsterHp, armorClass: 12 },
      );
      return api.addMonsters(
        combat,
        template.data.id,
        snapshot.current_device_id,
        monsterCount,
      );
    });
  }

  async function health(
    action: "damage" | "healing" | "temporary_hp" | "prevention",
  ) {
    if (!combat || !selected.length) return;
    const response = await run("health", () =>
      api.applyHealth(
        combat,
        snapshot.current_device_id,
        selected,
        action,
        amount,
        critical,
      ),
    );
    if (response) refresh();
  }

  async function addCondition() {
    if (!combat || selected.length !== 1) return;
    const target = combat.combatants.find((item) => item.id === selected[0]);
    if (!target) return;
    const response = await run("condition", () =>
      api.addCondition(combat, target, snapshot.current_device_id, condition),
    );
    if (response) refresh();
  }

  function toggleTarget(id: string) {
    setSelected((current) =>
      current.includes(id)
        ? current.filter((candidate) => candidate !== id)
        : [...current, id],
    );
  }

  async function moveEntry(entryId: string, direction: -1 | 1) {
    if (!combat) return;
    const ids = combat.entries.map((item) => item.id);
    const index = ids.indexOf(entryId);
    const destination = index + direction;
    if (index < 0 || destination < 0 || destination >= ids.length) return;
    [ids[index], ids[destination]] = [ids[destination], ids[index]];
    await run("reorder", () =>
      api.reorderCombat(combat, ids, snapshot.current_device_id),
    );
  }

  if (!combat)
    return (
      <section className="card stack span-2 combat-panel">
        <p className="eyebrow">БОЕВОЙ РЕЖИМ</p>
        <h2>Подготовьте сцену боя</h2>
        <p className="muted">
          Инициатива, здоровье и журнал будут сохранены в текущей сессии.
        </p>
        <button
          className="primary"
          onClick={create}
          disabled={pending === "create"}
        >
          Создать бой
        </button>
      </section>
    );

  const nextAction =
    combat.status === "PREPARATION"
      ? "start"
      : combat.status === "ACTIVE"
        ? "pause"
        : combat.status === "PAUSED"
          ? "resume"
          : undefined;
  const nextLabel = {
    start: "Начать бой",
    pause: "Пауза",
    resume: "Продолжить",
  };

  return (
    <section
      className="card stack span-2 combat-panel"
      aria-label="Управление боем"
    >
      <CombatHeader combat={combat} />
      <ErrorNotice error={error} />
      <div className="combat-toolbar">
        {nextAction && (
          <button
            className="primary"
            onClick={() =>
              run("transition", () =>
                api.transitionCombat(
                  combat,
                  snapshot.current_device_id,
                  nextAction,
                ),
              )
            }
          >
            {nextLabel[nextAction]}
          </button>
        )}
        {combat.status !== "COMPLETED" && combat.status !== "PREPARATION" && (
          <>
            <button
              onClick={() =>
                run("turn", () =>
                  api.moveTurn(combat, snapshot.current_device_id, -1),
                )
              }
            >
              Предыдущий
            </button>
            <button
              onClick={() =>
                run("turn", () =>
                  api.moveTurn(combat, snapshot.current_device_id, 1),
                )
              }
            >
              Следующий ход
            </button>
            <button
              className="danger"
              onClick={() =>
                run("transition", () =>
                  api.transitionCombat(
                    combat,
                    snapshot.current_device_id,
                    "complete",
                  ),
                )
              }
            >
              Завершить бой
            </button>
          </>
        )}
      </div>

      {combat.status !== "COMPLETED" && (
        <div className="combat-setup">
          <button
            className="secondary"
            onClick={() => run("characters", addSelectedCharacters)}
          >
            Добавить выбранных персонажей
          </button>
          {combat.status === "PREPARATION" && (
            <form
              className="inline-form combat-monster-form"
              onSubmit={addMonster}
            >
              <input
                aria-label="Имя монстра"
                value={monsterName}
                onChange={(event) => setMonsterName(event.target.value)}
                required
              />
              <input
                aria-label="HP монстра"
                type="number"
                min="1"
                value={monsterHp}
                onChange={(event) => setMonsterHp(Number(event.target.value))}
                required
              />
              <input
                aria-label="Количество монстров"
                type="number"
                min="1"
                max="20"
                value={monsterCount}
                onChange={(event) =>
                  setMonsterCount(Number(event.target.value))
                }
                required
              />
              <button className="secondary">Добавить монстров</button>
            </form>
          )}
        </div>
      )}

      <div className="initiative-list">
        {combat.entries.map((entry) => (
          <article
            className={
              entry.id === combat.current_entry_id
                ? "initiative active"
                : "initiative"
            }
            key={entry.id}
          >
            <span className="initiative-score">{entry.initiative}</span>
            <div>
              <strong>{entry.name}</strong>
              <small>
                {entry.combatant_ids.length > 1
                  ? `Группа: ${entry.combatant_ids.length}`
                  : "Один участник"}
              </small>
            </div>
            {combat.status !== "COMPLETED" && (
              <div className="initiative-actions">
                <button
                  aria-label={`Поднять ${entry.name}`}
                  onClick={() => moveEntry(entry.id, -1)}
                >
                  ↑
                </button>
                <button
                  aria-label={`Опустить ${entry.name}`}
                  onClick={() => moveEntry(entry.id, 1)}
                >
                  ↓
                </button>
                {combat.status === "PREPARATION" && (
                  <button
                    className="danger-text"
                    onClick={() =>
                      run("remove", () =>
                        api.removeCombatEntry(
                          combat,
                          entry.id,
                          snapshot.current_device_id,
                        ),
                      )
                    }
                  >
                    Удалить
                  </button>
                )}
              </div>
            )}
          </article>
        ))}
      </div>

      {combat.status !== "COMPLETED" && (
        <div className="combat-resolution">
          <h3>Разрешить действие</h3>
          <div className="target-grid">
            {combat.combatants.map((item) => (
              <label
                className={
                  selected.includes(item.id) ? "target selected" : "target"
                }
                key={item.id}
              >
                <input
                  type="checkbox"
                  checked={selected.includes(item.id)}
                  onChange={() => toggleTarget(item.id)}
                />
                <span>
                  <strong>{item.name}</strong>
                  <small>
                    {item.current_hp ?? "?"}/{item.max_hp ?? "?"} HP ·{" "}
                    {item.wound_state ?? "без ран"}
                  </small>
                </span>
              </label>
            ))}
          </div>
          <div className="combat-toolbar">
            <input
              aria-label="Величина эффекта"
              type="number"
              min="0"
              value={amount}
              onChange={(event) => setAmount(Number(event.target.value))}
            />
            <button onClick={() => health("damage")}>Урон</button>
            <button onClick={() => health("healing")}>Лечение</button>
            <button onClick={() => health("temporary_hp")}>Временные HP</button>
            <button onClick={() => health("prevention")}>Предотвращение</button>
            <label className="checkbox-inline">
              <input
                type="checkbox"
                checked={critical}
                onChange={(event) => setCritical(event.target.checked)}
              />
              Критический
            </label>
          </div>
          <div className="combat-toolbar">
            <input
              aria-label="Состояние"
              value={condition}
              onChange={(event) => setCondition(event.target.value)}
            />
            <button onClick={addCondition} disabled={selected.length !== 1}>
              Добавить состояние
            </button>
          </div>
        </div>
      )}

      {combat.report && (
        <div className="combat-report">
          <h3>Итоговый отчёт</h3>
          <pre>{JSON.stringify(combat.report, null, 2)}</pre>
        </div>
      )}
      <CombatJournal
        combat={combat}
        onCancel={(eventId) =>
          run("cancel", async () => {
            const response = await api.cancelCombatEvent(
              combat,
              snapshot.current_device_id,
              eventId,
            );
            refresh();
            return response;
          })
        }
        onCorrect={(eventId, eventTargets) => {
          const targetIds = selected.length ? selected : eventTargets;
          if (!targetIds.length) return;
          void run("correct", async () => {
            const response = await api.correctCombatEvent(
              combat,
              snapshot.current_device_id,
              eventId,
              targetIds,
              "damage",
              amount,
              critical,
            );
            refresh();
            return response;
          });
        }}
      />
    </section>
  );
}

function CombatJournal({
  combat,
  onCancel,
  onCorrect,
}: {
  combat: CombatState;
  onCancel?: (eventId: string) => void;
  onCorrect?: (eventId: string, targetIds: string[]) => void;
}) {
  return (
    <div className="combat-journal">
      <h3>Журнал боя</h3>
      {!combat.journal.length && (
        <p className="muted">Боевые события появятся здесь.</p>
      )}
      {combat.journal
        .slice()
        .reverse()
        .slice(0, 12)
        .map((event) => (
          <div className="journal-row" key={event.id}>
            <span>
              <strong>{eventLabel(event.event_type)}</strong>
              <small>{new Date(event.occurred_at).toLocaleTimeString()}</small>
            </span>
            {event.event_type === "HealthChanged" &&
              (onCancel || onCorrect) && (
                <span className="journal-actions">
                  {onCorrect && (
                    <button
                      onClick={() => {
                        const values = Array.isArray(event.payload.targets)
                          ? event.payload.targets
                          : [];
                        const ids = values.flatMap((item) =>
                          typeof item === "object" &&
                          item !== null &&
                          "target_id" in item
                            ? [String(item.target_id)]
                            : [],
                        );
                        onCorrect(event.id, ids);
                      }}
                    >
                      Исправить
                    </button>
                  )}
                  {onCancel && (
                    <button
                      className="danger-text"
                      onClick={() => onCancel(event.id)}
                    >
                      Отменить
                    </button>
                  )}
                </span>
              )}
          </div>
        ))}
    </div>
  );
}

export function PlayerCombatPanel({
  snapshot,
  refresh,
}: {
  snapshot: Snapshot;
  refresh: () => void;
}) {
  const combat = snapshot.combat;
  const [support, setSupport] = useState("");
  const [error, setError] = useState<unknown>();
  const own = useMemo(
    () =>
      combat?.combatants.find(
        (item) => item.reference_id === snapshot.player?.selected_character_id,
      ),
    [combat, snapshot.player?.selected_character_id],
  );

  async function perform(operation: () => Promise<unknown>) {
    setError(undefined);
    try {
      await operation();
      refresh();
    } catch (reason) {
      setError(reason);
    }
  }
  if (!combat) return null;
  const rollActor = own?.id ?? combat.combatants[0]?.id;
  return (
    <section className="card stack combat-panel" aria-label="Бой">
      <CombatHeader combat={combat} />
      <ErrorNotice error={error} />
      {own && (
        <div className="hero-health">
          <strong>{own.name}</strong>
          <span>
            {own.current_hp}/{own.max_hp} HP
            {own.temporary_hp ? ` + ${own.temporary_hp} временных` : ""}
          </span>
          <small>
            {own.conditions.map((item) => item.name).join(", ") ||
              "Нет состояний"}
          </small>
        </div>
      )}
      <div className="player-monsters">
        {combat.combatants
          .filter((item) => item.kind === "monster")
          .map((item) => (
            <div key={item.id}>
              <strong>{item.name}</strong>
              <span>{item.wound_state ?? "состояние скрыто"}</span>
            </div>
          ))}
      </div>
      {combat.status !== "COMPLETED" && rollActor && (
        <>
          {own && (
            <form
              className="inline-form"
              onSubmit={(event) => {
                event.preventDefault();
                void perform(() =>
                  api.support(
                    combat,
                    snapshot.current_device_id,
                    own.reference_id!,
                    support,
                  ),
                );
                setSupport("");
              }}
            >
              <input
                aria-label="Заявка поддержки"
                placeholder="Как вы помогаете союзнику?"
                value={support}
                onChange={(event) => setSupport(event.target.value)}
                required
              />
              <button className="secondary">Предложить поддержку</button>
            </form>
          )}
        </>
      )}
      <CombatJournal combat={combat} />
    </section>
  );
}
