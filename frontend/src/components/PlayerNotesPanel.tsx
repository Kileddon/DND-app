import { type FormEvent, useEffect, useState } from "react";

import { api, type PlayerNoteNode, type Snapshot } from "../api";
import { ErrorNotice } from "./ErrorNotice";

interface CreationTarget {
  kind: PlayerNoteNode["kind"];
  parentId: string | null;
}

function storedSettings(key: string) {
  try {
    return JSON.parse(localStorage.getItem(key) ?? "{}") as {
      hideFolders?: boolean;
      hideNotes?: boolean;
    };
  } catch {
    return {};
  }
}

export function PlayerNotesPanel({ snapshot }: { snapshot: Snapshot }) {
  const settingsKey = `ttc-player-notes-settings-${snapshot.player?.id ?? "local"}`;
  const initialSettings = storedSettings(settingsKey);
  const [nodes, setNodes] = useState<PlayerNoteNode[]>([]);
  const [hideFolders, setHideFolders] = useState(
    Boolean(initialSettings.hideFolders),
  );
  const [hideNotes, setHideNotes] = useState(
    Boolean(initialSettings.hideNotes),
  );
  const [creation, setCreation] = useState<CreationTarget>();
  const [newName, setNewName] = useState("");
  const [expandedNotes, setExpandedNotes] = useState<Set<string>>(new Set());
  const [editing, setEditing] = useState<PlayerNoteNode>();
  const [pending, setPending] = useState(false);
  const [error, setError] = useState<unknown>();

  useEffect(() => {
    api
      .playerNotes()
      .then((response) => setNodes(response.nodes))
      .catch(setError);
  }, []);

  function saveSettings(nextFolders: boolean, nextNotes: boolean) {
    setHideFolders(nextFolders);
    setHideNotes(nextNotes);
    localStorage.setItem(
      settingsKey,
      JSON.stringify({ hideFolders: nextFolders, hideNotes: nextNotes }),
    );
  }

  function beginCreate(kind: PlayerNoteNode["kind"], parentId: string | null) {
    setCreation({ kind, parentId });
    setNewName("");
  }

  async function create(event: FormEvent) {
    event.preventDefault();
    if (!creation) return;
    setPending(true);
    setError(undefined);
    try {
      const response = await api.createPlayerNoteNode(
        snapshot.current_device_id,
        creation.kind,
        newName,
        creation.parentId,
      );
      setNodes((current) => [...current, response.data]);
      setCreation(undefined);
      setNewName("");
    } catch (reason) {
      setError(reason);
    } finally {
      setPending(false);
    }
  }

  async function saveEdit(event: FormEvent) {
    event.preventDefault();
    if (!editing) return;
    setPending(true);
    setError(undefined);
    try {
      const response = await api.updatePlayerNoteNode(
        snapshot.current_device_id,
        editing,
      );
      setNodes((current) =>
        current.map((node) =>
          node.id === response.data.id ? response.data : node,
        ),
      );
      setEditing(undefined);
    } catch (reason) {
      setError(reason);
    } finally {
      setPending(false);
    }
  }

  function toggleNote(id: string) {
    setExpandedNotes((current) => {
      const next = new Set(current);
      if (next.has(id)) next.delete(id);
      else next.add(id);
      return next;
    });
  }

  function renderLevel(parentId: string | null, level: number) {
    return nodes
      .filter((node) => node.parent_id === parentId)
      .sort((left, right) =>
        left.kind === right.kind
          ? left.name.localeCompare(right.name, "ru")
          : left.kind === "folder"
            ? -1
            : 1,
      )
      .map((node) =>
        node.kind === "folder" ? (
          <details className="player-note-folder" key={node.id} open>
            <summary>
              <span aria-hidden="true">{level ? "↳ " : ""}</span>
              {node.name}
            </summary>
            <div className="player-note-folder-actions">
              {!hideFolders && node.depth < 3 && (
                <button
                  className="secondary"
                  onClick={() => beginCreate("folder", node.id)}
                >
                  Создать подкаталог
                </button>
              )}
              {!hideNotes && (
                <button
                  className="secondary"
                  onClick={() => beginCreate("note", node.id)}
                >
                  Создать заметку
                </button>
              )}
              <button
                className="secondary"
                onClick={() => setEditing({ ...node })}
              >
                Переименовать
              </button>
            </div>
            <div className="player-note-children">
              {renderLevel(node.id, level + 1)}
            </div>
          </details>
        ) : (
          <article className="player-note-document" key={node.id}>
            <div className="player-note-row">
              <button
                className="note-title"
                onClick={() => toggleNote(node.id)}
              >
                <span aria-hidden="true">{level ? "↳ " : ""}</span>
                {node.name}
              </button>
              <button
                className="secondary"
                onClick={() => setEditing({ ...node })}
              >
                Редактировать
              </button>
            </div>
            {expandedNotes.has(node.id) && (
              <div className="player-note-body">
                <strong>{node.name}</strong>
                <p>{node.body || "Заметка пока пустая."}</p>
              </div>
            )}
          </article>
        ),
      );
  }

  return (
    <section className="card stack player-notes-panel">
      <p className="eyebrow">ЗАМЕТКИ</p>
      <h2>Личные заметки</h2>
      <details className="player-notes-settings">
        <summary>Настройки</summary>
        <label className="checkbox-inline">
          <input
            type="checkbox"
            checked={hideFolders}
            onChange={(event) => saveSettings(event.target.checked, hideNotes)}
          />
          Скрыть создание каталогов
        </label>
        <label className="checkbox-inline">
          <input
            type="checkbox"
            checked={hideNotes}
            onChange={(event) =>
              saveSettings(hideFolders, event.target.checked)
            }
          />
          Скрыть создание заметок
        </label>
      </details>
      <ErrorNotice error={error} />
      <div className="player-note-root-actions">
        {!hideFolders && (
          <button
            className="secondary"
            onClick={() => beginCreate("folder", null)}
          >
            Создать каталог
          </button>
        )}
        {!hideNotes && (
          <button
            className="secondary"
            onClick={() => beginCreate("note", null)}
          >
            Создать заметку
          </button>
        )}
      </div>
      {creation && (
        <form className="player-note-name-editor" onSubmit={create}>
          <label>
            Название {creation.kind === "folder" ? "каталога" : "заметки"}
            <input
              autoFocus
              maxLength={120}
              value={newName}
              onChange={(event) => setNewName(event.target.value)}
              required
            />
          </label>
          <button className="primary" disabled={pending}>
            Создать
          </button>
          <button type="button" onClick={() => setCreation(undefined)}>
            Отмена
          </button>
        </form>
      )}
      <div className="player-note-tree">{renderLevel(null, 0)}</div>
      {!nodes.length && (
        <p className="muted">Каталоги и заметки пока не созданы.</p>
      )}
      {editing && (
        <form className="player-note-editor" onSubmit={saveEdit}>
          <label>
            Название
            <input
              maxLength={120}
              value={editing.name}
              onChange={(event) =>
                setEditing({ ...editing, name: event.target.value })
              }
              required
            />
          </label>
          {editing.kind === "note" && (
            <label>
              Текст заметки
              <textarea
                rows={6}
                value={editing.body}
                onChange={(event) =>
                  setEditing({ ...editing, body: event.target.value })
                }
                onInput={(event) => {
                  event.currentTarget.style.height = "auto";
                  event.currentTarget.style.height = `${event.currentTarget.scrollHeight}px`;
                }}
              />
            </label>
          )}
          <div className="inline-actions">
            <button className="primary" disabled={pending}>
              Сохранить
            </button>
            <button type="button" onClick={() => setEditing(undefined)}>
              Отмена
            </button>
          </div>
        </form>
      )}
    </section>
  );
}
