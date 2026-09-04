import { useEffect, useState } from "react";

import {
  api,
  type Character,
  type CharacterDraft,
  type CharacterOptions,
  type CharacterSummary,
  type Snapshot,
} from "../api";
import { CharacterCreationWizard } from "./CharacterCreationWizard";
import { CharacterSheet } from "./CharacterSheet";
import { DicePanel } from "./DicePanel";
import { ErrorNotice } from "./ErrorNotice";

type PlayerSection = "lobby" | "character" | "dice";

export function PlayerDashboard({
  snapshot,
  refresh,
}: {
  snapshot: Snapshot;
  refresh: () => void;
}) {
  const player = snapshot.player!;
  const [section, setSection] = useState<PlayerSection>("lobby");
  const [cabinetOpen, setCabinetOpen] = useState(false);
  const [draft, setDraft] = useState<CharacterDraft>();
  const [character, setCharacter] = useState<Character>();
  const [options, setOptions] = useState<CharacterOptions>();
  const [creating, setCreating] = useState(
    !player.selected_character_id && !(snapshot.characters?.length ?? 0),
  );
  const [pending, setPending] = useState(false);
  const [error, setError] = useState<unknown>();

  useEffect(() => {
    api.characterOptions().then(setOptions).catch(setError);
  }, []);
  useEffect(() => {
    if (player.selected_character_id)
      api
        .character(player.selected_character_id)
        .then(setCharacter)
        .catch(setError);
  }, [player.selected_character_id, snapshot.cursor]);

  async function choose(cardId: string) {
    if (!draft) return;
    setPending(true);
    setError(undefined);
    try {
      const response = await api.chooseCard(
        snapshot.current_device_id,
        draft,
        cardId,
      );
      setDraft(response.data);
    } catch (reason) {
      setError(reason);
    } finally {
      setPending(false);
    }
  }

  async function confirm() {
    if (!draft) return;
    setPending(true);
    setError(undefined);
    try {
      const response = await api.confirmDraft(
        snapshot.current_device_id,
        draft,
      );
      await api.selectCharacter(
        snapshot.current_device_id,
        player,
        response.data.id,
      );
      setCharacter(response.data);
      setDraft(undefined);
      setCreating(false);
      refresh();
    } catch (reason) {
      setError(reason);
    } finally {
      setPending(false);
    }
  }

  async function select(summary: CharacterSummary) {
    try {
      await api.selectCharacter(snapshot.current_device_id, player, summary.id);
      setCreating(false);
      refresh();
    } catch (reason) {
      setError(reason);
    }
  }

  async function restore(summary: CharacterSummary) {
    try {
      await api.changeCharacterLifecycle(
        snapshot.current_device_id,
        summary,
        "restore",
      );
      refresh();
    } catch (reason) {
      setError(reason);
    }
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
        <button
          className="secondary cabinet-toggle"
          onClick={() => setCabinetOpen(true)}
        >
          На связи
        </button>
      </header>
      <nav className="dashboard-nav" aria-label="Разделы игрока">
        {(
          [
            ["lobby", "Лобби"],
            ["character", "Персонаж"],
            ["dice", "Кубики"],
          ] as const
        ).map(([value, label]) => (
          <button
            key={value}
            className={section === value ? "active" : ""}
            onClick={() => setSection(value)}
          >
            {label}
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
        </section>
      )}
      {section === "dice" && (
        <DicePanel snapshot={snapshot} refresh={refresh} />
      )}
      {cabinetOpen && !draft && !creating && (
        <section
          className="card stack span-2 cabinet-panel"
          role="dialog"
          aria-label="Личный кабинет"
        >
          <div className="section-heading">
            <h2>Мои персонажи</h2>
            <div className="inline-actions">
              <button className="primary" onClick={() => setCreating(true)}>
                Создать нового
              </button>
              <button onClick={() => setCabinetOpen(false)}>Закрыть</button>
            </div>
          </div>
          <div className="option-list">
            {snapshot.characters?.map((summary) => (
              <button
                className={
                  summary.selected
                    ? "character-choice selected"
                    : "character-choice"
                }
                onClick={() => select(summary)}
                key={summary.id}
              >
                <strong>{summary.name}</strong>
                <span>
                  {summary.current_hp}/{summary.max_hp} HP · КБ{" "}
                  {summary.armor_class}
                </span>
              </button>
            ))}
          </div>
          {!!snapshot.archived_characters?.length && (
            <details>
              <summary>Архив персонажей</summary>
              {snapshot.archived_characters.map((summary) => (
                <div className="inventory-row" key={summary.id}>
                  <strong>{summary.name}</strong>
                  <button onClick={() => restore(summary)}>Восстановить</button>
                </div>
              ))}
            </details>
          )}
        </section>
      )}
      {cabinetOpen && creating && !draft && options && (
        <CharacterCreationWizard
          deviceId={snapshot.current_device_id}
          options={options}
          onCreated={setDraft}
        />
      )}
      {cabinetOpen && draft && (
        <section className="card stack">
          <div className="round-counter">
            Способность{" "}
            {Math.min(draft.completed_rounds + 1, draft.required_rounds)} из{" "}
            {draft.required_rounds}
          </div>
          {!draft.ready_to_confirm && <h2>Выберите способность</h2>}
          {draft.random_rolls?.length ? (
            <div className="roll-attempts">
              {draft.random_rolls.map((roll, index) => (
                <span key={index}>
                  [{roll.values.join(", ")}] → {roll.total}
                </span>
              ))}
            </div>
          ) : null}
          <div className="ability-grid">
            {draft.offered_cards.map((card) => (
              <button
                className="ability-card"
                disabled={pending}
                onClick={() => choose(card.id)}
                key={card.id}
              >
                <span className="ability-kind">Плейсхолдер</span>
                <strong>{card.name}</strong>
                <span>{card.description}</span>
              </button>
            ))}
          </div>
          {draft.ready_to_confirm && (
            <>
              <h3>Итоговый просмотр</h3>
              <div className="stats">
                {Object.entries(draft.stats ?? {}).map(([stat, value]) => (
                  <div key={stat}>
                    <span>
                      {options?.stats?.find((item) => item.id === stat)?.name ??
                        stat}
                    </span>
                    <strong>{value}</strong>
                  </div>
                ))}
              </div>
              <button className="primary" disabled={pending} onClick={confirm}>
                Подтвердить персонажа
              </button>
            </>
          )}
        </section>
      )}
      {section === "character" && character && options && (
        <CharacterSheet
          snapshot={snapshot}
          initial={character}
          options={options}
          onRefresh={refresh}
        />
      )}
      {section === "character" && !character && (
        <section className="card stack">
          <h2>Персонаж не выбран</h2>
          <button className="primary" onClick={() => setCabinetOpen(true)}>
            Открыть личный кабинет
          </button>
        </section>
      )}
    </main>
  );
}
