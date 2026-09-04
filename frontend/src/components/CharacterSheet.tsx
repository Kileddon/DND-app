import { type FormEvent, useState } from "react";

import {
  api,
  type Character,
  type CharacterOptions,
  type CharacterSummary,
  type InventoryItem,
  type Snapshot,
} from "../api";
import { ErrorNotice } from "./ErrorNotice";
import { visibleOtherSlotCount } from "../viewRules";

const slotLabels: Record<string, string> = {
  left_hand: "Левая рука",
  right_hand: "Правая рука",
  armor: "Доспех",
  other_1: "Иное 1",
  other_2: "Иное 2",
  other_3: "Иное 3",
  other_4: "Иное 4",
};

interface FeatureView {
  id: string;
  name: string;
  description: string;
  required_level: number;
}

function modifier(value: number) {
  if (!Number.isFinite(value)) return "+0";
  const result = Math.floor((value - 10) / 2);
  return result >= 0 ? `+${result}` : `${result}`;
}

function fitsSlot(item: InventoryItem, slot: string) {
  if (slot === "armor") return item.slot_compatibility === "armor";
  if (slot.startsWith("other_")) return item.slot_compatibility === "other";
  return item.slot_compatibility === "hand";
}

export function CharacterSheet({
  snapshot,
  initial,
  options,
  onRefresh,
}: {
  snapshot: Snapshot;
  initial: Character;
  options?: CharacterOptions;
  onRefresh: () => void;
}) {
  const player = snapshot.player!;
  const [character, setCharacter] = useState(initial);
  const [feature, setFeature] = useState<FeatureView>();
  const [confirmArchive, setConfirmArchive] = useState(false);
  const [itemName, setItemName] = useState("");
  const [weight, setWeight] = useState("0");
  const [compatibility, setCompatibility] =
    useState<InventoryItem["slot_compatibility"]>("none");
  const [error, setError] = useState<unknown>();
  const [pending, setPending] = useState(false);
  const species = options?.species?.find(
    (item) => item.id === character.race_id,
  );
  const className =
    options?.class_details?.find((item) => item.id === character.class_id)
      ?.name ?? character.class_id;
  const slots = [
    "left_hand",
    "right_hand",
    "armor",
    ...Array.from(
      { length: visibleOtherSlotCount(character.inventory) },
      (_, index) => `other_${index + 1}`,
    ),
  ];

  async function run(operation: () => Promise<{ data: Character }>) {
    setPending(true);
    setError(undefined);
    try {
      const response = await operation();
      setCharacter(response.data);
      onRefresh();
    } catch (reason) {
      setError(reason);
    } finally {
      setPending(false);
    }
  }

  async function addItem(event: FormEvent) {
    event.preventDefault();
    await run(() =>
      api.addItem(
        snapshot.current_device_id,
        player.id,
        character,
        itemName,
        weight,
        compatibility,
      ),
    );
    setItemName("");
  }

  async function select(summary: CharacterSummary) {
    try {
      await api.selectCharacter(snapshot.current_device_id, player, summary.id);
      onRefresh();
    } catch (reason) {
      setError(reason);
    }
  }

  return (
    <div className="player-grid character-sheet">
      <section className="card stack">
        <div className="section-heading">
          <div>
            <p className="eyebrow">ЛИСТ ПЕРСОНАЖА</p>
            <h2>{character.name}</h2>
          </div>
          <select
            aria-label="Переключить персонажа"
            value={character.id}
            onChange={(event) => {
              const target = snapshot.characters?.find(
                (item) => item.id === event.target.value,
              );
              if (target) void select(target);
            }}
          >
            {snapshot.characters?.map((item) => (
              <option value={item.id} key={item.id}>
                {item.name}
              </option>
            ))}
          </select>
        </div>
        <p>
          {species?.name ?? character.race_id} · {className} · уровень{" "}
          {character.level ?? 1} · {character.experience ?? 0} опыта
        </p>
        <div className="vitals">
          <strong>
            {character.current_hp}/{character.max_hp} HP
          </strong>
          <strong>Временные HP {character.temporary_hp ?? 0}</strong>
          <strong>КБ {character.armor_class}</strong>
          <strong>Инициатива {modifier(character.stats.dexterity)}</strong>
        </div>
        <p>
          Размер: {character.size} · Скорость: {character.speed} футов · Тёмное
          зрение: {character.darkvision || "нет"} · Бонус владения: +
          {character.proficiency_bonus ?? 2}
        </p>
        <div className="stats">
          {Object.entries(character.stats).map(([id, value]) => {
            const stat = options?.stats?.find((item) => item.id === id);
            return (
              <button className="stat-card" key={id} title={stat?.description}>
                <span>{stat?.name ?? id}</span>
                <strong>{value}</strong>
                <small>{modifier(value)}</small>
              </button>
            );
          })}
        </div>
        <h3>Расовые особенности</h3>
        <div className="feature-buttons">
          {species?.features.map((item) => (
            <button
              className="secondary"
              key={item.id}
              onClick={() => setFeature(item)}
            >
              {item.name}
              {item.required_level > (character.level ?? 1)
                ? ` · уровень ${item.required_level}`
                : ""}
            </button>
          ))}
        </div>
        <h3>Карточки способностей</h3>
        <div className="abilities">
          {character.abilities.map((ability) => (
            <article key={ability.id}>
              <strong>{ability.name}</strong>
              <span>{ability.description}</span>
            </article>
          ))}
        </div>
        <button className="danger-text" onClick={() => setConfirmArchive(true)}>
          Архивировать персонажа
        </button>
        <ErrorNotice error={error} />
      </section>
      <section className="card stack backpack">
        <p className="eyebrow">РЮКЗАК И ЭКИПИРОВКА</p>
        <h2>Общий вес: {character.total_weight} кг</h2>
        <div className="equipment-layout">
          <div className="humanoid" aria-hidden="true">
            ◯<br />
            ╱▣╲
            <br />╱ ╲
          </div>
          <div className="equipment-slots">
            {slots.map((slot) => {
              const item = character.inventory.find(
                (candidate) => candidate.equipment_slot === slot,
              );
              return (
                <div className="equipment-slot" key={slot}>
                  <strong>{slotLabels[slot]}</strong>
                  {item ? (
                    <>
                      <span>{item.name}</span>
                      <button
                        disabled={pending}
                        onClick={() =>
                          run(() =>
                            api.equipItem(
                              snapshot.current_device_id,
                              player.id,
                              character,
                              item,
                              null,
                            ),
                          )
                        }
                      >
                        Снять
                      </button>
                    </>
                  ) : (
                    <select
                      value=""
                      onChange={(event) => {
                        const selected = character.inventory.find(
                          (candidate) => candidate.id === event.target.value,
                        );
                        if (selected)
                          void run(() =>
                            api.equipItem(
                              snapshot.current_device_id,
                              player.id,
                              character,
                              selected,
                              slot,
                            ),
                          );
                      }}
                    >
                      <option value="">Пусто</option>
                      {character.inventory
                        .filter(
                          (candidate) =>
                            !candidate.equipment_slot &&
                            fitsSlot(candidate, slot),
                        )
                        .map((candidate) => (
                          <option value={candidate.id} key={candidate.id}>
                            {candidate.name}
                          </option>
                        ))}
                    </select>
                  )}
                </div>
              );
            })}
          </div>
        </div>
        <h3>В рюкзаке</h3>
        {character.inventory
          .filter((item) => !item.equipment_slot)
          .map((item) => (
            <div className="inventory-row" key={item.id}>
              <span>
                <strong>{item.name}</strong>
                <small>
                  {item.quantity} шт. · {item.unit_weight} кг
                </small>
              </span>
              <button
                className="danger-text"
                disabled={pending || item.locked}
                onClick={() =>
                  run(() =>
                    api.discardItem(
                      snapshot.current_device_id,
                      player.id,
                      character,
                      item,
                    ),
                  )
                }
              >
                <span aria-label="Удалить 1">Выбросить 1</span>
              </button>
            </div>
          ))}
        {!character.inventory.length && (
          <p className="muted">Инвентарь пуст.</p>
        )}
        <form className="stack compact" onSubmit={addItem}>
          <input
            placeholder="Новый предмет"
            value={itemName}
            onChange={(event) => setItemName(event.target.value)}
            required
          />
          <input
            aria-label="Вес предмета"
            value={weight}
            onChange={(event) => setWeight(event.target.value)}
            pattern="\d+(\.\d{1,3})?"
          />
          <select
            aria-label="Тип слота"
            value={compatibility}
            onChange={(event) =>
              setCompatibility(
                event.target.value as InventoryItem["slot_compatibility"],
              )
            }
          >
            <option value="none">Только рюкзак</option>
            <option value="hand">Рука</option>
            <option value="armor">Доспех</option>
            <option value="other">Иное</option>
          </select>
          <button className="secondary" disabled={pending}>
            Добавить
          </button>
        </form>
      </section>
      {feature && (
        <div className="dice-overlay" role="dialog" aria-modal="true">
          <div className="dice-animation-card">
            <h2>{feature.name}</h2>
            <p>{feature.description}</p>
            <p>{species?.source_url}</p>
            <strong>
              {feature.required_level <= (character.level ?? 1)
                ? "Доступно"
                : `Откроется на уровне ${feature.required_level}`}
            </strong>
            <button onClick={() => setFeature(undefined)}>Закрыть</button>
          </div>
        </div>
      )}
      {confirmArchive && (
        <div className="dice-overlay" role="dialog" aria-modal="true">
          <div className="dice-animation-card">
            <h2>Архивировать {character.name}?</h2>
            <p>Персонаж исчезнет из активного списка, но история сохранится.</p>
            <button
              className="danger"
              onClick={() =>
                run(() =>
                  api.changeCharacterLifecycle(
                    snapshot.current_device_id,
                    character,
                    "archive",
                  ),
                )
              }
            >
              Архивировать
            </button>
            <button onClick={() => setConfirmArchive(false)}>Отмена</button>
          </div>
        </div>
      )}
    </div>
  );
}
