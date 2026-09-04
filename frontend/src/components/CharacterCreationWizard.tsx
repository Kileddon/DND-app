import { useMemo, useState } from "react";

import { api, type CharacterDraft, type CharacterOptions } from "../api";
import { ErrorNotice } from "./ErrorNotice";

const statIds = [
  "strength",
  "dexterity",
  "constitution",
  "intelligence",
  "wisdom",
  "charisma",
];
const pointCosts: Record<number, number> = {
  8: 0,
  9: 1,
  10: 2,
  11: 3,
  12: 4,
  13: 5,
  14: 7,
  15: 9,
};

export function CharacterCreationWizard({
  deviceId,
  options,
  onCreated,
}: {
  deviceId: string;
  options: CharacterOptions;
  onCreated: (draft: CharacterDraft) => void;
}) {
  const [step, setStep] = useState(0);
  const [name, setName] = useState("");
  const [classId, setClassId] = useState("fighter");
  const [raceId, setRaceId] = useState("human");
  const [method, setMethod] = useState<"standard" | "random" | "point_buy">(
    "standard",
  );
  const [stats, setStats] = useState<Record<string, number>>({
    strength: 15,
    dexterity: 15,
    constitution: 15,
    intelligence: 8,
    wisdom: 8,
    charisma: 8,
  });
  const [choices, setChoices] = useState<Record<string, string>>({
    size: "medium",
    skill: "perception",
  });
  const [backgroundPattern, setBackgroundPattern] = useState<"2+1" | "1+1+1">(
    "1+1+1",
  );
  const [backgroundStats, setBackgroundStats] = useState<
    [string, string, string]
  >(["strength", "dexterity", "constitution"]);
  const [pending, setPending] = useState(false);
  const [error, setError] = useState<unknown>();
  const speciesCatalog =
    options.species ??
    options.races.map((item) => ({
      ...item,
      source_url: "",
      creature_type: "Гуманоид",
      sizes: ["medium"],
      speed: 30,
      lineages: [],
      features: [],
    }));
  const classCatalog =
    options.class_details ??
    options.classes.map((item) => ({
      ...item,
      theme: item.description,
      primary_stat: "—",
      difficulty: "—",
    }));
  const statCatalog = options.stats ?? [];
  const species = speciesCatalog.find((item) => item.id === raceId);
  const legacyCatalog = !options.class_details;
  const hasVariantStep = ["gnome", "dragonborn", "human", "elf"].includes(
    raceId,
  );
  const spent = useMemo(
    () =>
      Object.values(stats).reduce(
        (sum, value) => sum + (pointCosts[value] ?? 99),
        0,
      ),
    [stats],
  );
  const steps = [
    "Имя",
    "Класс",
    "Раса",
    "Варианты расы",
    "Настройка характеристик",
    "Характеристики",
    "Предыстория",
  ];

  function chooseRace(value: string) {
    setRaceId(value);
    setChoices(
      value === "gnome"
        ? { lineage: "forest", spellcasting_stat: "intelligence" }
        : value === "dragonborn"
          ? { lineage: "red" }
          : value === "human"
            ? { size: "medium", skill: "perception" }
            : value === "elf"
              ? {
                  lineage: "high",
                  spellcasting_stat: "intelligence",
                  keen_senses: "perception",
                }
              : {},
    );
  }

  async function beginAbilities() {
    setPending(true);
    setError(undefined);
    try {
      const request = api.startDraft(deviceId, name, raceId, classId, {
        species_choices: choices,
        stat_method: method,
        stats: method === "point_buy" ? stats : {},
        background_pattern: backgroundPattern,
        background_stats: backgroundStats,
        background_allocations:
          backgroundPattern === "2+1"
            ? { [backgroundStats[0]]: 2, [backgroundStats[1]]: 1 }
            : Object.fromEntries(backgroundStats.map((stat) => [stat, 1])),
      });
      const [response] = await Promise.all([
        request,
        method === "random"
          ? new Promise((resolve) => window.setTimeout(resolve, 2000))
          : Promise.resolve(),
      ]);
      onCreated(response.data);
    } catch (reason) {
      setError(reason);
    } finally {
      setPending(false);
    }
  }

  return (
    <section className="card stack character-wizard">
      <p className="eyebrow">СОЗДАНИЕ ПЕРСОНАЖА · {steps[step]}</p>
      <ErrorNotice error={error} />
      {step === 0 && (
        <label>
          Имя нового персонажа
          <input
            value={name}
            onChange={(event) => setName(event.target.value)}
            autoFocus
          />
        </label>
      )}
      {step === 1 && (
        <div
          className="class-choice-table"
          role="list"
          aria-label="Список классов"
        >
          <div className="class-choice-head" role="presentation">
            <span>Класс</span>
            <span>Специализация</span>
            <span>Основные атрибуты</span>
            <span>Сложность</span>
          </div>
          {classCatalog.map((item) => (
            <button
              className={
                classId === item.id ? "option-card selected" : "option-card"
              }
              onClick={() => setClassId(item.id)}
              key={item.id}
            >
              <strong>{item.name}</strong>
              <small>{item.theme}</small>
              <small>{item.primary_stat}</small>
              <small>{item.difficulty}</small>
            </button>
          ))}
        </div>
      )}
      {step === 2 && (
        <div className="race-choice-grid">
          {speciesCatalog.map((item) => (
            <button
              className={
                raceId === item.id ? "option-card selected" : "option-card"
              }
              onClick={() => chooseRace(item.id)}
              key={item.id}
            >
              <strong>{item.name}</strong>
              <small>{item.description}</small>
            </button>
          ))}
        </div>
      )}
      {step === 3 && hasVariantStep && (
        <div className="stack compact">
          <p>
            {species?.creature_type} · скорость {species?.speed} футов
          </p>
          {raceId === "gnome" && (
            <>
              <Choice
                label="Род"
                value={choices.lineage}
                values={["forest", "rock"]}
                onChange={(value) => setChoices({ ...choices, lineage: value })}
              />
              <Spellcasting choices={choices} setChoices={setChoices} />
            </>
          )}
          {raceId === "dragonborn" && (
            <Choice
              label="Наследие"
              value={choices.lineage}
              values={[
                "white",
                "bronze",
                "green",
                "gold",
                "red",
                "brass",
                "copper",
                "silver",
                "blue",
                "black",
              ]}
              onChange={(value) => setChoices({ ...choices, lineage: value })}
            />
          )}
          {raceId === "human" && (
            <>
              <Choice
                label="Размер"
                value={choices.size}
                values={["medium", "small"]}
                onChange={(value) => setChoices({ ...choices, size: value })}
              />
              <Choice
                label="Навык"
                value={choices.skill}
                values={[
                  "perception",
                  "survival",
                  "insight",
                  "athletics",
                  "arcana",
                  "stealth",
                ]}
                onChange={(value) => setChoices({ ...choices, skill: value })}
              />
            </>
          )}
          {raceId === "elf" && (
            <>
              <Choice
                label="Род"
                value={choices.lineage}
                values={["high", "drow", "wood"]}
                onChange={(value) => setChoices({ ...choices, lineage: value })}
              />
              <Spellcasting choices={choices} setChoices={setChoices} />
              <Choice
                label="Обострённые чувства"
                value={choices.keen_senses}
                values={["perception", "survival", "insight"]}
                onChange={(value) =>
                  setChoices({ ...choices, keen_senses: value })
                }
              />
            </>
          )}
        </div>
      )}
      {step === 4 && (
        <div className="roll-selection">
          {(["standard", "random", "point_buy"] as const).map((value) => (
            <button
              className={method === value ? "active" : ""}
              onClick={() => setMethod(value)}
              key={value}
            >
              {value === "standard"
                ? "Стандартный набор"
                : value === "random"
                  ? "4d6 без меньшего"
                  : "27 очков"}
            </button>
          ))}
        </div>
      )}
      {step === 5 && method === "standard" && (
        <p>Набор будет автоматически распределён с учётом выбранного класса.</p>
      )}
      {step === 5 && method === "random" && (
        <p>
          Сервер выполнит шесть бросков 4d6, исключит один минимальный кубик и
          покажет все значения перед выбором способностей.
        </p>
      )}
      {step === 5 && method === "point_buy" && (
        <div className="stack">
          <strong>Потрачено: {spent} из 27</strong>
          {statIds.map((stat) => (
            <label key={stat}>
              {statCatalog.find((item) => item.id === stat)?.name}
              <input
                type="number"
                min="8"
                max="15"
                value={stats[stat]}
                onChange={(event) =>
                  setStats({ ...stats, [stat]: Number(event.target.value) })
                }
              />
            </label>
          ))}
        </div>
      )}
      {step === 6 && (
        <div className="stack">
          <h3>Произвольная предыстория</h3>
          <div className="roll-selection">
            <button
              className={backgroundPattern === "2+1" ? "active" : ""}
              onClick={() => setBackgroundPattern("2+1")}
            >
              +2 и +1
            </button>
            <button
              className={backgroundPattern === "1+1+1" ? "active" : ""}
              onClick={() => setBackgroundPattern("1+1+1")}
            >
              +1, +1 и +1
            </button>
          </div>
          {backgroundStats
            .slice(0, backgroundPattern === "2+1" ? 2 : 3)
            .map((value, index) => (
              <label key={index}>
                {backgroundPattern === "2+1" && index === 0 ? "+2" : "+1"}
                <select
                  value={value}
                  onChange={(event) => {
                    const next = [...backgroundStats];
                    next[index] = event.target.value;
                    setBackgroundStats(next as [string, string, string]);
                  }}
                >
                  {statIds.map((stat) => (
                    <option value={stat} key={stat}>
                      {statCatalog.find((item) => item.id === stat)?.name ??
                        stat}
                    </option>
                  ))}
                </select>
              </label>
            ))}
          <p>Каждую характеристику можно выбрать только один раз.</p>
        </div>
      )}
      <div className="wizard-actions">
        {legacyCatalog && step === 0 ? (
          <button
            className="primary"
            disabled={!name.trim() || pending}
            onClick={beginAbilities}
          >
            Перейти к способностям
          </button>
        ) : (
          <>
            {step > 0 && (
              <button className="secondary" onClick={() => setStep(step - 1)}>
                Назад
              </button>
            )}
            {step < steps.length - 1 ? (
              <button
                className="primary"
                disabled={step === 0 && !name.trim()}
                onClick={() =>
                  setStep(step === 2 && !hasVariantStep ? 4 : step + 1)
                }
              >
                Далее
              </button>
            ) : (
              <button
                className="primary"
                disabled={
                  pending ||
                  (method === "point_buy" && spent !== 27) ||
                  new Set(
                    backgroundStats.slice(
                      0,
                      backgroundPattern === "2+1" ? 2 : 3,
                    ),
                  ).size !== (backgroundPattern === "2+1" ? 2 : 3)
                }
                onClick={beginAbilities}
              >
                {pending
                  ? method === "random"
                    ? "Кубики катятся…"
                    : "Сохраняем…"
                  : "К карточкам способностей"}
              </button>
            )}
          </>
        )}
      </div>
    </section>
  );
}

function Choice({
  label,
  value,
  values,
  onChange,
}: {
  label: string;
  value?: string;
  values: string[];
  onChange: (value: string) => void;
}) {
  return (
    <label>
      {label}
      <select value={value} onChange={(event) => onChange(event.target.value)}>
        {values.map((item) => (
          <option value={item} key={item}>
            {choiceLabel(item)}
          </option>
        ))}
      </select>
    </label>
  );
}

function choiceLabel(value: string) {
  const labels: Record<string, string> = {
    small: "Маленький",
    medium: "Средний",
    forest: "Лесной",
    rock: "Скальный",
    high: "Высший",
    drow: "Дроу",
    wood: "Лесной",
    intelligence: "Интеллект",
    wisdom: "Мудрость",
    charisma: "Харизма",
    perception: "Внимательность",
    survival: "Выживание",
    insight: "Проницательность",
    athletics: "Атлетика",
    arcana: "Магия",
    stealth: "Скрытность",
    white: "Белое",
    bronze: "Бронзовое",
    green: "Зелёное",
    gold: "Золотое",
    red: "Красное",
    brass: "Латунное",
    copper: "Медное",
    silver: "Серебряное",
    blue: "Синее",
    black: "Чёрное",
  };
  return labels[value] ?? value;
}

function Spellcasting({
  choices,
  setChoices,
}: {
  choices: Record<string, string>;
  setChoices: (value: Record<string, string>) => void;
}) {
  return (
    <Choice
      label="Заклинательная характеристика"
      value={choices.spellcasting_stat}
      values={["intelligence", "wisdom", "charisma"]}
      onChange={(value) => setChoices({ ...choices, spellcasting_stat: value })}
    />
  );
}
