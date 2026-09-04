import { type FormEvent, useEffect, useState } from "react";

import { api, type GmNotes, type NpcNote, type Snapshot } from "../api";
import { ErrorNotice } from "./ErrorNotice";

type NotesTab = "campaign" | "npcs" | "other";

export function GmNotesPanel({ snapshot }: { snapshot: Snapshot }) {
  const [notes, setNotes] = useState<GmNotes>();
  const [tab, setTab] = useState<NotesTab>("campaign");
  const [selectedNpcId, setSelectedNpcId] = useState<string>();
  const [newNpcName, setNewNpcName] = useState("");
  const [pending, setPending] = useState(false);
  const [error, setError] = useState<unknown>();
  const selectedNpc = notes?.npcs.find((npc) => npc.id === selectedNpcId);

  useEffect(() => {
    api.gmNotes(snapshot.room.id).then(setNotes).catch(setError);
  }, [snapshot.room.id]);

  async function saveText() {
    if (!notes) return;
    setPending(true);
    try {
      const response = await api.updateGmNotes(
        snapshot.room.id,
        snapshot.current_device_id,
        notes,
      );
      setNotes({ ...notes, ...response.data });
    } catch (reason) {
      setError(reason);
    } finally {
      setPending(false);
    }
  }

  async function addNpc(event: FormEvent) {
    event.preventDefault();
    if (!notes) return;
    setPending(true);
    try {
      const response = await api.createNpcNote(
        snapshot.room.id,
        snapshot.current_device_id,
        newNpcName,
      );
      setNotes({ ...notes, npcs: [...notes.npcs, response.data] });
      setSelectedNpcId(response.data.id);
      setNewNpcName("");
    } catch (reason) {
      setError(reason);
    } finally {
      setPending(false);
    }
  }

  function patchNpc(values: Partial<NpcNote>) {
    if (!notes || !selectedNpc) return;
    setNotes({
      ...notes,
      npcs: notes.npcs.map((npc) =>
        npc.id === selectedNpc.id ? { ...npc, ...values } : npc,
      ),
    });
  }

  async function saveNpc() {
    if (!notes || !selectedNpc) return;
    setPending(true);
    try {
      const response = await api.updateNpcNote(
        snapshot.room.id,
        snapshot.current_device_id,
        selectedNpc,
      );
      setNotes({
        ...notes,
        npcs: notes.npcs.map((npc) =>
          npc.id === selectedNpc.id ? response.data : npc,
        ),
      });
    } catch (reason) {
      setError(reason);
    } finally {
      setPending(false);
    }
  }

  async function removeNpc() {
    if (!notes || !selectedNpc) return;
    setPending(true);
    try {
      await api.deleteNpcNote(
        snapshot.room.id,
        snapshot.current_device_id,
        selectedNpc.id,
      );
      setNotes({
        ...notes,
        npcs: notes.npcs.filter((npc) => npc.id !== selectedNpc.id),
      });
      setSelectedNpcId(undefined);
    } catch (reason) {
      setError(reason);
    } finally {
      setPending(false);
    }
  }

  return (
    <section className="card stack span-2">
      <div>
        <p className="eyebrow">БЛОК ВЕДУЩЕГО</p>
        <h2>Заметки</h2>
      </div>
      <div className="tabs">
        <button
          aria-pressed={tab === "campaign"}
          onClick={() => setTab("campaign")}
        >
          Кампания
        </button>
        <button aria-pressed={tab === "npcs"} onClick={() => setTab("npcs")}>
          Неигровые персонажи
        </button>
        <button aria-pressed={tab === "other"} onClick={() => setTab("other")}>
          Другие заметки
        </button>
      </div>
      <ErrorNotice error={error} />
      {!notes && <p className="muted">Загружаем заметки…</p>}
      {notes && tab === "campaign" && (
        <>
          <textarea
            aria-label="Заметки кампании"
            rows={14}
            value={notes.campaign}
            onChange={(e) => setNotes({ ...notes, campaign: e.target.value })}
            placeholder="Сюжет, места, важные события…"
          />
          <button className="primary" onClick={saveText} disabled={pending}>
            Сохранить
          </button>
        </>
      )}
      {notes && tab === "other" && (
        <>
          <textarea
            aria-label="Другие заметки"
            rows={14}
            value={notes.other}
            onChange={(e) => setNotes({ ...notes, other: e.target.value })}
            placeholder="Любые заметки ведущего…"
          />
          <button className="primary" onClick={saveText} disabled={pending}>
            Сохранить
          </button>
        </>
      )}
      {notes && tab === "npcs" && (
        <div className="master-detail">
          <div className="npc-list stack compact">
            <form className="inline-form" onSubmit={addNpc}>
              <input
                aria-label="Имя нового NPC"
                value={newNpcName}
                onChange={(e) => setNewNpcName(e.target.value)}
                placeholder="Новый NPC"
                required
              />
              <button className="secondary" disabled={pending}>
                Создать
              </button>
            </form>
            {notes.npcs.map((npc) => (
              <button
                key={npc.id}
                className={selectedNpcId === npc.id ? "active" : ""}
                onClick={() => setSelectedNpcId(npc.id)}
              >
                {npc.name}
              </button>
            ))}
          </div>
          {selectedNpc ? (
            <div className="stack">
              <label>
                Имя
                <input
                  value={selectedNpc.name}
                  onChange={(e) => patchNpc({ name: e.target.value })}
                />
              </label>
              <label>
                Информация
                <textarea
                  rows={12}
                  value={selectedNpc.details}
                  onChange={(e) => patchNpc({ details: e.target.value })}
                />
              </label>
              <div className="inline-actions">
                <button
                  className="primary"
                  onClick={saveNpc}
                  disabled={pending}
                >
                  Сохранить NPC
                </button>
                <button
                  className="danger-text"
                  onClick={removeNpc}
                  disabled={pending}
                >
                  Удалить
                </button>
              </div>
            </div>
          ) : (
            <div className="empty-detail">
              Выберите NPC или создайте нового.
            </div>
          )}
        </div>
      )}
    </section>
  );
}
