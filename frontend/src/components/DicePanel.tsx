import { type FormEvent, useEffect, useRef, useState } from "react";

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
  faces: number[][];
  bonus: number;
  roll?: DiceRoll;
}

function expressionParts(expression: string) {
  const match = /^(\d*)d(\d+)([+-]\d+)?$/i.exec(expression);
  return {
    count: Number(match?.[1] || 1),
    sides: Number(match?.[2] || 20),
    bonus: Number(match?.[3] || 0),
  };
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
  const intervalRef = useRef<number | undefined>(undefined);
  const timeoutRef = useRef<number | undefined>(undefined);

  function clearAnimationTimers() {
    if (intervalRef.current) window.clearInterval(intervalRef.current);
    if (timeoutRef.current) window.clearTimeout(timeoutRef.current);
    intervalRef.current = undefined;
    timeoutRef.current = undefined;
  }

  useEffect(() => clearAnimationTimers, []);

  async function roll(expression: string) {
    if (pending) return;
    setPending(true);
    setError(undefined);
    const parts = expressionParts(expression);
    const attemptCount = selection === "neutral" ? 1 : 2;
    let frame = 0;
    setAnimation({
      spinning: true,
      bonus: parts.bonus,
      faces: Array.from({ length: attemptCount }, (_, attemptIndex) =>
        Array.from(
          { length: parts.count },
          (_, dieIndex) => ((attemptIndex + dieIndex) % parts.sides) + 1,
        ),
      ),
    });
    intervalRef.current = window.setInterval(() => {
      frame += 1;
      setAnimation((current) =>
        current
          ? {
              ...current,
              faces: current.faces.map((attempt, attemptIndex) =>
                attempt.map(
                  (_, dieIndex) =>
                    ((frame + dieIndex * 3 + attemptIndex * 7) % parts.sides) +
                    1,
                ),
              ),
            }
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
        new Promise((resolve) => {
          timeoutRef.current = window.setTimeout(resolve, 2000);
        }),
      ]);
      clearAnimationTimers();
      const rolled = response.data.roll;
      setAnimation({
        spinning: false,
        bonus: parts.bonus,
        faces: rolled.attempts.length ? rolled.attempts : [rolled.values],
        roll: rolled,
      });
      refresh();
    } catch (reason) {
      clearAnimationTimers();
      setAnimation(undefined);
      setError(reason);
    } finally {
      setPending(false);
    }
  }

  function customRoll(event: FormEvent) {
    event.preventDefault();
    const modifier = bonus === 0 ? "" : bonus > 0 ? `+${bonus}` : `${bonus}`;
    void roll(`${count}d${sides}${modifier}`);
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
            onClick={() => roll(`1d${faceCount}`)}
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
              aria-label="Количество кубиков"
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
              aria-label="Количество граней"
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
              aria-label="Бонус броска"
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
                    [{attempt.join(", ")}]{" "}
                    {expressionParts(item.expression).bonus >= 0 ? "+" : ""}
                    {expressionParts(item.expression).bonus} ={" "}
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
            <strong>
              {animation.spinning ? "Кубики катятся…" : "Результат"}
            </strong>
            <div className="animated-attempts dice-groups">
              {animation.faces.map((attempt, attemptIndex) => (
                <div
                  className={
                    !animation.spinning &&
                    attemptIndex === animation.roll?.selected_attempt
                      ? "selected dice-attempt"
                      : "dice-attempt"
                  }
                  key={attemptIndex}
                >
                  <div>
                    {attempt.map((face, dieIndex) => (
                      <span
                        className={
                          animation.spinning ? "rolling-number" : "final-number"
                        }
                        key={dieIndex}
                      >
                        {face}
                      </span>
                    ))}
                  </div>
                  {!animation.spinning && animation.roll && (
                    <small>
                      {animation.bonus >= 0 ? "+" : ""}
                      {animation.bonus} ={" "}
                      {animation.roll.attempt_totals[attemptIndex]}
                    </small>
                  )}
                </div>
              ))}
            </div>
            {!animation.spinning && animation.roll && (
              <>
                <strong className="roll-total">
                  Итого: {animation.roll.result}
                </strong>
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
