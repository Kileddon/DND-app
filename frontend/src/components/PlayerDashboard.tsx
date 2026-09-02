import { type FormEvent, useEffect, useState } from "react";

import {
  api,
  type Character,
  type CharacterDraft,
  type CharacterSummary,
  type Snapshot,
} from "../api";
import { ErrorNotice } from "./ErrorNotice";

export function PlayerDashboard({
  snapshot,
  refresh,
}: {
  snapshot: Snapshot;
  refresh: () => void;
}) {
  const player = snapshot.player!;
  const [draft, setDraft] = useState<CharacterDraft>();
  const [character, setCharacter] = useState<Character>();
  const [name, setName] = useState("");
  const [itemName, setItemName] = useState("");
  const [pending, setPending] = useState("");
  const [error, setError] = useState<unknown>();

  useEffect(() => {
    if (player.selected_character_id) {
      api
        .character(player.selected_character_id)
        .then(setCharacter)
        .catch(setError);
    }
  }, [player.selected_character_id, snapshot.cursor]);

  async function action<T>(
    name: string,
    operation: () => Promise<T>,
  ): Promise<T | undefined> {
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
      api.startDraft(snapshot.current_device_id, name),
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
      refresh();
    }
  }

  async function select(summary: CharacterSummary) {
    const response = await action("select", () =>
      api.selectCharacter(snapshot.current_device_id, player, summary.id),
    );
    if (response) refresh();
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
      <ErrorNotice error={error} />

      {!player.selected_character_id && !draft && (
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
              <span>Открыть</span>
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
            <button className="primary" disabled={pending === "draft"}>
              {pending === "draft" ? "Готовим…" : "Начать простой конструктор"}
            </button>
          </form>
        </section>
      )}

      {draft && (
        <section className="card stack">
          <div className="round-counter">
            Раунд {Math.min(draft.completed_rounds + 1, draft.required_rounds)}{" "}
            из {draft.required_rounds}
          </div>
          <h2>Выберите способность для {draft.name}</h2>
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

      {character && (
        <div className="player-grid">
          <section className="card stack">
            <p className="eyebrow">КАРТОЧКА ПЕРСОНАЖА</p>
            <h2>{character.name}</h2>
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
