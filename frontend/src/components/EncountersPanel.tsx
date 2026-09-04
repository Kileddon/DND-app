import { type FormEvent, useState } from "react";

import { api, type Snapshot } from "../api";
import { HostCombatPanel, PlayerCombatPanel } from "./CombatPanel";
import { ErrorNotice } from "./ErrorNotice";

export function EncountersPanel({
  snapshot,
  refresh,
  gm,
}: {
  snapshot: Snapshot;
  refresh: () => void;
  gm: boolean;
}) {
  const encounters = snapshot.encounters ?? [];
  const [selectedId, setSelectedId] = useState(
    snapshot.combat?.id ?? encounters[0]?.id,
  );
  const [name, setName] = useState("");
  const [error, setError] = useState<unknown>();
  const selected =
    encounters.find((item) => item.id === selectedId) ?? encounters[0];
  async function create(event: FormEvent) {
    event.preventDefault();
    if (!snapshot.session) return;
    try {
      const response = await api.createCombat(
        snapshot.room.id,
        snapshot.session.id,
        snapshot.current_device_id,
        name,
      );
      setSelectedId(response.data.id);
      setName("");
      refresh();
    } catch (reason) {
      setError(reason);
    }
  }

  return (
    <div className="stack span-2 encounters-panel">
      <ErrorNotice error={error} />
      <div className="encounter-tabs" role="tablist">
        {encounters.map((item) => (
          <button
            role="tab"
            aria-selected={item.id === selected?.id}
            className={item.id === selected?.id ? "active" : ""}
            onClick={() => setSelectedId(item.id)}
            key={item.id}
          >
            {item.name} · {item.status}
          </button>
        ))}
      </div>
      {gm && snapshot.session && snapshot.session.status !== "COMPLETED" && (
        <form className="inline-form" onSubmit={create}>
          <input
            placeholder="Название нового энкаунтера"
            value={name}
            onChange={(event) => setName(event.target.value)}
            required
          />
          <button className="secondary">Подготовить энкаунтер</button>
        </form>
      )}
      {selected ? (
        gm ? (
          <HostCombatPanel
            snapshot={{ ...snapshot, combat: selected }}
            refresh={refresh}
          />
        ) : (
          <PlayerCombatPanel
            snapshot={{ ...snapshot, combat: selected }}
            refresh={refresh}
          />
        )
      ) : (
        <section className="card">
          <h2>Энкаунтеров пока нет</h2>
          <p className="muted">
            Ведущий может подготовить бой заранее; открытие вкладки его не
            запускает.
          </p>
        </section>
      )}
    </div>
  );
}
