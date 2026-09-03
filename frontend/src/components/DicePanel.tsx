import { type FormEvent, useState } from "react";

import { api, type DiceRoll, type Snapshot } from "../api";
import { ErrorNotice } from "./ErrorNotice";

type Selection = DiceRoll["selection"];

const selectionLabels: Record<Selection, string> = {
  neutral: "Обычный",
  advantage: "С преимуществом",
  disadvantage: "С помехой",
};

interface RollAnimation {
  spinning: boolean;
  face: number;
  roll?: DiceRoll;
}

export function DicePanel({
  snapshot,
  refresh,
}: {
  snapshot: Snapshot;
  refresh: () => void;
}) {
  const [selection, setSelection] = useState<Selection>("neutral");
  const [count, setCount] = useState(1);
  const [sides, setSides] = useState(20);
  const [bonus, setBonus] = useState(0);
  const [animation, setAnimation] = useState<RollAnimation>();
  const [pending, setPending] = useState(false);
  const [error, setError] = useState<unknown>();

  async function roll(expression: string, faceCount: number) {
    if (pending) return;
    setPending(true);
    setError(undefined);
    setAnimation({ spinning: true, face: 1 });
    const interval = window.setInterval(() => {
      setAnimation((current) =>
        current
          ? { ...current, face: Math.floor(Math.random() * faceCount) + 1 }
          : current,
      );
    }, 70);
    try {
      const [response] = await Promise.all([
        api.rollRoom(
          snapshot.room.id,
          snapshot.current_device_id,
          expression,
          selection,
        ),
        new Promise((resolve) => window.setTimeout(resolve, 2000)),
      ]);
      window.clearInterval(interval);
      setAnimation({
        spinning: false,
        face: response.data.roll.result,
        roll: response.data.roll,
      });
      refresh();
    } catch (reason) {
      window.clearInterval(interval);
      setAnimation(undefined);
      setError(reason);
    } finally {
      setPending(false);
    }
  }

  function customRoll(event: FormEvent) {
    event.preventDefault();
    const modifier = bonus === 0 ? "" : bonus > 0 ? `+${bonus}` : `${bonus}`;
    void roll(`${count}d${sides}${modifier}`, sides);
  }

  const history = [...(snapshot.dice_rolls ?? [])].reverse().slice(0, 30);

  return (
    <section
      className="card stack span-2 dice-panel"
      aria-label="Броски кубиков"
    >
      <div className="section-heading">
        <div>
          <p className="eyebrow">КУБИКИ</p>
          <h2>Бросок кубиков</h2>
        </div>
      </div>
      <ErrorNotice error={error} />

      <div className="roll-selection" role="group" aria-label="Режим броска">
        {(Object.keys(selectionLabels) as Selection[]).map((value) => (
          <button
            key={value}
            className={selection === value ? "active" : ""}
            onClick={() => setSelection(value)}
            disabled={pending}
          >
            {selectionLabels[value]}
          </button>
        ))}
      </div>

      <div className="quick-dice">
        {[20, 6, 4, 100].map((faceCount) => (
          <button
            key={faceCount}
            className="die-button"
            disabled={pending}
            onClick={() => roll(`1d${faceCount}`, faceCount)}
          >
            <span>d{faceCount}</span>
            <small>Бросить 1d{faceCount}</small>
          </button>
        ))}
      </div>

      <form className="custom-roll" onSubmit={customRoll}>
        <h3>Свой бросок</h3>
        <div className="form-grid three">
          <label>
            Количество кубиков
            <input
              type="number"
              min="1"
              max="100"
              value={count}
              onChange={(event) => setCount(Number(event.target.value))}
            />
          </label>
          <label>
            Граней
            <input
              type="number"
              min="2"
              max="1000"
              value={sides}
              onChange={(event) => setSides(Number(event.target.value))}
            />
          </label>
          <label>
            Бонус
            <input
              type="number"
              min="-100000"
              max="100000"
              value={bonus}
              onChange={(event) => setBonus(Number(event.target.value))}
            />
          </label>
        </div>
        <button className="primary" disabled={pending}>
          Бросить {count}d{sides}
          {bonus > 0 ? `+${bonus}` : bonus < 0 ? bonus : ""}
        </button>
      </form>

      <div className="roll-history stack">
        <h3>История бросков</h3>
        {!history.length && <p className="muted">Бросков пока не было.</p>}
        {history.map((item) => (
          <article className="roll-history-row" key={item.id}>
            <div>
              <strong>{item.expression}</strong>
              <span>
                {item.actor_name ?? "Участник"} ·{" "}
                {selectionLabels[item.selection]}
              </span>
            </div>
            <div className="roll-attempts">
              {(item.attempts.length ? item.attempts : [item.values]).map(
                (attempt, index) => (
                  <span
                    key={index}
                    className={
                      index === item.selected_attempt ? "selected" : ""
                    }
                  >
                    [{attempt.join(", ")}] ={" "}
                    {item.attempt_totals[index] ?? item.result}
                  </span>
                ),
              )}
            </div>
            <strong className="roll-total">{item.result}</strong>
          </article>
        ))}
      </div>

      {animation && (
        <div
          className="dice-overlay"
          role="dialog"
          aria-modal="true"
          aria-label="Результат броска"
        >
          <div className="dice-animation-card">
            <span
              className={animation.spinning ? "rolling-number" : "final-number"}
            >
              {animation.face}
            </span>
            <strong>
              {animation.spinning ? "Кубики катятся…" : "Результат"}
            </strong>
            {!animation.spinning && animation.roll && (
              <>
                <div className="animated-attempts">
                  {animation.roll.attempts.map((attempt, index) => (
                    <span
                      key={index}
                      className={
                        index === animation.roll?.selected_attempt
                          ? "selected"
                          : ""
                      }
                    >
                      [{attempt.join(", ")}] ={" "}
                      {animation.roll?.attempt_totals[index]}
                    </span>
                  ))}
                </div>
                <button
                  className="primary"
                  onClick={() => setAnimation(undefined)}
                >
                  Закрыть
                </button>
              </>
            )}
          </div>
        </div>
      )}
    </section>
  );
}
