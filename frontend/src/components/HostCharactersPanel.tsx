import { type FormEvent, useEffect, useState } from "react";

import {
  api,
  type Character,
  type CharacterOptions,
  type Snapshot,
} from "../api";
import { ErrorNotice } from "./ErrorNotice";

export function HostCharactersPanel({
  snapshot,
  refresh,
}: {
  snapshot: Snapshot;
  refresh: () => void;
}) {
  const [selected, setSelected] = useState<Character>();
  const [options, setOptions] = useState<CharacterOptions>();
  const [pending, setPending] = useState(false);
  const [error, setError] = useState<unknown>();
  const [itemName, setItemName] = useState("");

  useEffect(() => {
    api.characterOptions().then(setOptions).catch(setError);
  }, []);

  async function open(characterId: string) {
    setError(undefined);
    try {
      setSelected(await api.character(characterId));
    } catch (reason) {
      setError(reason);
    }
  }

  async function save() {
    if (!selected) return;
    setPending(true);
    setError(undefined);
    try {
      const response = await api.updateCharacter(
        snapshot.room.id,
        snapshot.current_device_id,
        selected,
      );
      setSelected(response.data);
      refresh();
    } catch (reason) {
      setError(reason);
    } finally {
      setPending(false);
    }
  }

  function patch(values: Partial<Character>) {
    setSelected((current) => (current ? { ...current, ...values } : current));
  }

  function toggleAbility(abilityId: string) {
    if (!selected || !options) return;
    const ability = options.abilities.find((item) => item.id === abilityId);
    if (!ability) return;
    const hasAbility = selected.abilities.some((item) => item.id === abilityId);
    patch({
      abilities: hasAbility
        ? selected.abilities.filter((item) => item.id !== abilityId)
        : [...selected.abilities, ability],
    });
  }

  async function addItem(event: FormEvent) {
    event.preventDefault();
    if (!selected) return;
    setPending(true);
    setError(undefined);
    try {
      const response = await api.gmAddItem(
        snapshot.room.id,
        snapshot.current_device_id,
        selected,
        itemName,
      );
      setSelected(response.data);
      setItemName("");
      refresh();
    } catch (reason) {
      setError(reason);
    } finally {
      setPending(false);
    }
  }

  async function removeItem(itemId: string) {
    if (!selected) return;
    const item = selected.inventory.find(
      (candidate) => candidate.id === itemId,
    );
    if (!item) return;
    setPending(true);
    setError(undefined);
    try {
      const response = await api.gmDiscardItem(
        snapshot.room.id,
        snapshot.current_device_id,
        selected,
        item,
      );
      setSelected(response.data);
      refresh();
    } catch (reason) {
      setError(reason);
    } finally {
      setPending(false);
    }
  }

  const availableAbilities = options?.abilities.filter(
    (ability) =>
      !ability.class_ids?.length ||
      ability.class_ids.includes(selected?.class_id ?? ""),
  );

  return (
    <section className="card stack span-2">
      <div className="section-heading">
        <div>
          <p className="eyebrow">ПЕРСОНАЖИ</p>
          <h2>Карточки участников</h2>
        </div>
      </div>
      <ErrorNotice error={error} />
      <div className="master-detail">
        <div className="character-master-list">
          {snapshot.characters?.map((character) => (
            <button
              key={character.id}
              className={selected?.id === character.id ? "active" : ""}
              onClick={() => open(character.id)}
            >
              <strong>{character.name}</strong>
              <span>Персонаж участника {character.owner_name}</span>
              <small>
                HP {character.current_hp}/{character.max_hp} · КБ{" "}
                {character.armor_class}
              </small>
            </button>
          ))}
          {!snapshot.characters?.length && (
            <p className="muted">Персонажей пока нет.</p>
          )}
        </div>

        {selected ? (
          <div className="character-editor stack">
            <label>
              Имя
              <input
                value={selected.name}
                onChange={(e) => patch({ name: e.target.value })}
              />
            </label>
            <div className="form-grid">
              <label>
                Раса
                <select
                  value={selected.race_id}
                  onChange={(e) => patch({ race_id: e.target.value })}
                >
                  {options?.races.map((race) => (
                    <option key={race.id} value={race.id}>
                      {race.name}
                    </option>
                  ))}
                </select>
              </label>
              <label>
                Класс
                <select
                  value={selected.class_id}
                  onChange={(e) =>
                    patch({ class_id: e.target.value, abilities: [] })
                  }
                >
                  {options?.classes.map((item) => (
                    <option key={item.id} value={item.id}>
                      {item.name}
                    </option>
                  ))}
                </select>
              </label>
            </div>
            <div className="form-grid three">
              <label>
                Текущие HP
                <input
                  type="number"
                  min="0"
                  value={selected.current_hp}
                  onChange={(e) =>
                    patch({ current_hp: Number(e.target.value) })
                  }
                />
              </label>
              <label>
                Максимум HP
                <input
                  type="number"
                  min="1"
                  value={selected.max_hp}
                  onChange={(e) => patch({ max_hp: Number(e.target.value) })}
                />
              </label>
              <label>
                Класс брони
                <input
                  type="number"
                  min="1"
                  value={selected.armor_class}
                  onChange={(e) =>
                    patch({ armor_class: Number(e.target.value) })
                  }
                />
              </label>
            </div>
            <div className="form-grid three">
              <label>
                Временные HP
                <input
                  type="number"
                  min="0"
                  value={selected.temporary_hp ?? 0}
                  onChange={(e) =>
                    patch({ temporary_hp: Number(e.target.value) })
                  }
                />
              </label>
              <label>
                Уровень
                <input
                  type="number"
                  min="1"
                  max="20"
                  value={selected.level ?? 1}
                  onChange={(e) => patch({ level: Number(e.target.value) })}
                />
              </label>
              <label>
                Опыт
                <input
                  type="number"
                  min="0"
                  value={selected.experience ?? 0}
                  onChange={(e) =>
                    patch({ experience: Number(e.target.value) })
                  }
                />
              </label>
              <label>
                Инициатива
                <input
                  type="number"
                  value={selected.initiative ?? 0}
                  onChange={(e) =>
                    patch({ initiative: Number(e.target.value) })
                  }
                />
              </label>
              <label>
                Бонус владения
                <input
                  type="number"
                  min="2"
                  value={selected.proficiency_bonus ?? 2}
                  onChange={(e) =>
                    patch({ proficiency_bonus: Number(e.target.value) })
                  }
                />
              </label>
              <label>
                Размер
                <select
                  value={selected.size ?? "medium"}
                  onChange={(e) => patch({ size: e.target.value })}
                >
                  <option value="small">Маленький</option>
                  <option value="medium">Средний</option>
                </select>
              </label>
              <label>
                Скорость
                <input
                  type="number"
                  min="0"
                  value={selected.speed ?? 30}
                  onChange={(e) => patch({ speed: Number(e.target.value) })}
                />
              </label>
              <label>
                Тёмное зрение
                <input
                  type="number"
                  min="0"
                  value={selected.darkvision ?? 0}
                  onChange={(e) =>
                    patch({ darkvision: Number(e.target.value) })
                  }
                />
              </label>
            </div>
            <h3>Характеристики</h3>
            <div className="form-grid three">
              {Object.entries(selected.stats).map(([key, value]) => (
                <label key={key}>
                  {key}
                  <input
                    type="number"
                    min="1"
                    max="30"
                    value={value}
                    onChange={(e) =>
                      patch({
                        stats: {
                          ...selected.stats,
                          [key]: Number(e.target.value),
                        },
                      })
                    }
                  />
                </label>
              ))}
            </div>
            <h3>Способности класса</h3>
            <div className="ability-checklist">
              {availableAbilities?.map((ability) => (
                <label key={ability.id}>
                  <input
                    type="checkbox"
                    checked={selected.abilities.some(
                      (item) => item.id === ability.id,
                    )}
                    onChange={() => toggleAbility(ability.id)}
                  />
                  <span>
                    <strong>{ability.name}</strong>
                    <small>{ability.description}</small>
                  </span>
                </label>
              ))}
            </div>
            <h3>Инвентарь</h3>
            {selected.inventory.map((item) => (
              <div className="inventory-row" key={item.id}>
                <span>
                  <strong>{item.name}</strong>
                  <small>Количество: {item.quantity}</small>
                </span>
                <button
                  className="danger-text"
                  disabled={pending}
                  onClick={() => removeItem(item.id)}
                >
                  Удалить
                </button>
              </div>
            ))}
            {!selected.inventory.length && (
              <p className="muted">Инвентарь пуст.</p>
            )}
            <form className="inline-form" onSubmit={addItem}>
              <input
                aria-label="Название предмета для персонажа"
                placeholder="Новый предмет"
                value={itemName}
                onChange={(event) => setItemName(event.target.value)}
                required
              />
              <button className="secondary" disabled={pending}>
                Добавить
              </button>
            </form>
            <button className="primary" onClick={save} disabled={pending}>
              {pending ? "Сохраняем…" : "Сохранить карточку"}
            </button>
          </div>
        ) : (
          <div className="empty-detail">
            Выберите персонажа, чтобы открыть полную карточку.
          </div>
        )}
      </div>
    </section>
  );
}
