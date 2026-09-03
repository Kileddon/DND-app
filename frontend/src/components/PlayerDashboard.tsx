import { type FormEvent, useEffect, useState } from "react";

import {
  api,
  type Character,
  type CharacterDraft,
  type CharacterOptions,
  type CharacterSummary,
  type Snapshot,
} from "../api";
import { PlayerCombatPanel } from "./CombatPanel";
import { ErrorNotice } from "./ErrorNotice";
import { DicePanel } from "./DicePanel";

type PlayerSection = "lobby" | "character" | "combat" | "dice";

export function PlayerDashboard({
  snapshot,
  refresh,
}: {
  snapshot: Snapshot;
  refresh: () => void;
}) {
  const player = snapshot.player!;
  const [section, setSection] = useState<PlayerSection>("lobby");
  const [draft, setDraft] = useState<CharacterDraft>();
  const [character, setCharacter] = useState<Character>();
  const [options, setOptions] = useState<CharacterOptions>();
  const [name, setName] = useState("");
  const [raceId, setRaceId] = useState("human");
  const [classId, setClassId] = useState("fighter");
  const [itemName, setItemName] = useState("");
  const [pending, setPending] = useState("");
  const [error, setError] = useState<unknown>();

  useEffect(() => {
    api.characterOptions().then(setOptions).catch(setError);
  }, []);

  useEffect(() => {
    if (player.selected_character_id) {
      api
        .character(player.selected_character_id)
        .then(setCharacter)
        .catch(setError);
    }
  }, [player.selected_character_id, snapshot.cursor]);

  async function action<T>(name: string, operation: () => Promise<T>) {
    setPending(name);
    setError(undefined);
    try {
      return await operation();
    } catch (reason) {
      setError(reason);
      if (reason instanceof Error && reason.message.includes("version"))
        refresh();
      return undefined;
    } finally {
      setPending("");
    }
  }

  async function startDraft(event: FormEvent) {
    event.preventDefault();
    const response = await action("draft", () =>
      api.startDraft(snapshot.current_device_id, name, raceId, classId),
    );
    if (response) setDraft(response.data);
  }

  async function choose(cardId: string) {
    if (!draft) return;
    const response = await action("choice", () =>
      api.chooseCard(snapshot.current_device_id, draft, cardId),
    );
    if (response) setDraft(response.data);
  }

  async function confirm() {
    if (!draft) return;
    const response = await action("confirm", () =>
      api.confirmDraft(snapshot.current_device_id, draft),
    );
    if (!response) return;
    const selected = await action("select", () =>
      api.selectCharacter(snapshot.current_device_id, player, response.data.id),
    );
    if (selected) {
      setCharacter(response.data);
      setDraft(undefined);
      setSection("character");
      refresh();
    }
  }

  async function select(summary: CharacterSummary) {
    const response = await action("select", () =>
      api.selectCharacter(snapshot.current_device_id, player, summary.id),
    );
    if (response) {
      setSection("character");
      refresh();
    }
  }

  async function addItem(event: FormEvent) {
    event.preventDefault();
    if (!character) return;
    const response = await action("inventory", () =>
      api.addItem(snapshot.current_device_id, player.id, character, itemName),
    );
    if (response) {
      setCharacter(response.data);
      setItemName("");
    }
  }

  async function discard(itemId: string) {
    if (!character) return;
    const item = character.inventory.find(
      (candidate) => candidate.id === itemId,
    );
    if (!item) return;
    const response = await action("inventory", () =>
      api.discardItem(snapshot.current_device_id, player.id, character, item),
    );
    if (response) setCharacter(response.data);
  }

  return (
    <main className="dashboard player-dashboard">
      <header className="topbar">
        <div>
          <p className="eyebrow">{snapshot.room.name}</p>
          <h1>Привет, {player.display_name}</h1>
        </div>
        <div className="session-pill">
          {snapshot.session?.status ?? "Ожидаем лобби"}
        </div>
      </header>

      <nav className="dashboard-nav" aria-label="Разделы игрока">
        {(["lobby", "character", "combat", "dice"] as const).map((item) => (
          <button
            key={item}
            className={section === item ? "active" : ""}
            onClick={() => setSection(item)}
          >
            {item === "lobby"
              ? "Лобби"
              : item === "character"
                ? "Персонаж"
                : item === "combat"
                  ? "Бой"
                  : "Кубики"}
          </button>
        ))}
      </nav>
      <ErrorNotice error={error} />

      {section === "lobby" && (
        <section className="card stack">
          <p className="eyebrow">ЛОББИ</p>
          <h2>{snapshot.room.name}</h2>
          <p>
            Вы вошли как <strong>{player.display_name}</strong>.
          </p>
          <p className="muted">
            Статус сессии:{" "}
            {snapshot.session?.status ?? "ведущий ещё не открыл сессию"}
          </p>
          <button className="secondary" onClick={() => setSection("character")}>
            Перейти к персонажу
          </button>
        </section>
      )}

      {section === "combat" && (
        <PlayerCombatPanel snapshot={snapshot} refresh={refresh} />
      )}

      {section === "dice" && (
        <DicePanel snapshot={snapshot} refresh={refresh} />
      )}

      {section === "character" && !player.selected_character_id && !draft && (
        <section className="card stack">
          <p className="eyebrow">ПЕРСОНАЖ</p>
          <h2>
            {snapshot.characters?.length
              ? "Выберите персонажа"
              : "Создайте героя"}
          </h2>
          {snapshot.characters?.map((summary) => (
            <button
              className="character-choice"
              key={summary.id}
              onClick={() => select(summary)}
            >
              <strong>{summary.name}</strong>
              <span>
                {summary.current_hp}/{summary.max_hp} HP · КБ{" "}
                {summary.armor_class}
              </span>
            </button>
          ))}
          <form onSubmit={startDraft} className="stack compact">
            <label>
              Имя нового персонажа
              <input
                value={name}
                onChange={(event) => setName(event.target.value)}
                required
              />
            </label>
            <div className="choice-columns">
              <fieldset>
                <legend>Раса</legend>
                {options?.races.map((race) => (
                  <label className="option-card" key={race.id}>
                    <input
                      type="radio"
                      name="race"
                      checked={raceId === race.id}
                      onChange={() => setRaceId(race.id)}
                    />
                    <span>
                      <strong>{race.name}</strong>
                      <small>{race.description}</small>
                    </span>
                  </label>
                ))}
              </fieldset>
              <fieldset>
                <legend>Класс</legend>
                {options?.classes.map((characterClass) => (
                  <label className="option-card" key={characterClass.id}>
                    <input
                      type="radio"
                      name="class"
                      checked={classId === characterClass.id}
                      onChange={() => setClassId(characterClass.id)}
                    />
                    <span>
                      <strong>{characterClass.name}</strong>
                      <small>{characterClass.description}</small>
                    </span>
                  </label>
                ))}
              </fieldset>
            </div>
            <button
              className="primary"
              disabled={pending === "draft" || !options}
            >
              {pending === "draft" ? "Готовим…" : "Перейти к способностям"}
            </button>
          </form>
        </section>
      )}

      {section === "character" && draft && (
        <section className="card stack">
          <div className="round-counter">
            Способность{" "}
            {Math.min(draft.completed_rounds + 1, draft.required_rounds)} из{" "}
            {draft.required_rounds}
          </div>
          <h2>Выберите способность для {draft.name}</h2>
          <p className="muted">
            {draft.race_id} · {draft.class_id}
          </p>
          <div className="ability-grid">
            {draft.offered_cards.map((card) => (
              <button
                className="ability-card"
                key={card.id}
                disabled={pending === "choice"}
                onClick={() => choose(card.id)}
              >
                <span className="ability-kind">{card.kind}</span>
                <strong>{card.name}</strong>
                <span>{card.description}</span>
              </button>
            ))}
          </div>
          {draft.ready_to_confirm && (
            <button
              className="primary"
              onClick={confirm}
              disabled={pending === "confirm"}
            >
              {pending === "confirm"
                ? "Подтверждаем…"
                : "Подтвердить персонажа"}
            </button>
          )}
        </section>
      )}

      {section === "character" && character && (
        <div className="player-grid">
          <section className="card stack">
            <p className="eyebrow">КАРТОЧКА ПЕРСОНАЖА</p>
            <h2>{character.name}</h2>
            <p className="character-subtitle">
              {character.race_id} · {character.class_id}
            </p>
            <div className="vitals">
              <strong>
                {character.current_hp}/{character.max_hp} HP
              </strong>
              <strong>КБ {character.armor_class}</strong>
            </div>
            <dl className="stats">
              {Object.entries(character.stats).map(([key, value]) => (
                <div key={key}>
                  <dt>{key}</dt>
                  <dd>{value}</dd>
                </div>
              ))}
            </dl>
            <h3>Способности</h3>
            <div className="abilities">
              {character.abilities.map((ability) => (
                <article key={ability.id}>
                  <strong>{ability.name}</strong>
                  <span>{ability.description}</span>
                </article>
              ))}
            </div>
          </section>
          <section className="card stack">
            <p className="eyebrow">ИНВЕНТАРЬ</p>
            <h2>Снаряжение</h2>
            {character.inventory.map((item) => (
              <div className="inventory-row" key={item.id}>
                <span>
                  <strong>{item.name}</strong>
                  <small>Количество: {item.quantity}</small>
                </span>
                <button
                  className="danger-text"
                  disabled={pending === "inventory" || item.locked}
                  onClick={() => discard(item.id)}
                >
                  Удалить 1
                </button>
              </div>
            ))}
            {!character.inventory.length && (
              <p className="muted">Инвентарь пуст.</p>
            )}
            <form onSubmit={addItem} className="inline-form">
              <input
                aria-label="Название предмета"
                placeholder="Новый предмет"
                value={itemName}
                onChange={(event) => setItemName(event.target.value)}
                required
              />
              <button className="secondary" disabled={pending === "inventory"}>
                Добавить
              </button>
            </form>
          </section>
        </div>
      )}
    </main>
  );
}
