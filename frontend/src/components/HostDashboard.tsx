import { useEffect, useState } from "react";

import { api, type Diagnostics, type GameSession, type Snapshot } from "../api";
import { HostCombatPanel } from "./CombatPanel";
import { ErrorNotice } from "./ErrorNotice";

interface PairingInfo {
  id: string;
  short_code: string;
  pair_url: string;
  qr_data_url: string;
  expires_at: string;
}

export function HostDashboard({
  snapshot,
  refresh,
}: {
  snapshot: Snapshot;
  refresh: () => void;
}) {
  const [pairing, setPairing] = useState<PairingInfo>();
  const [invitation, setInvitation] = useState<string>();
  const [diagnostics, setDiagnostics] = useState<Diagnostics>();
  const [pending, setPending] = useState("");
  const [error, setError] = useState<unknown>();
  const deviceId = snapshot.current_device_id;

  useEffect(() => {
    api
      .diagnostics()
      .then(setDiagnostics)
      .catch(() => undefined);
  }, [snapshot.cursor]);

  async function action(name: string, operation: () => Promise<unknown>) {
    setPending(name);
    setError(undefined);
    try {
      await operation();
      refresh();
    } catch (reason) {
      setError(reason);
    } finally {
      setPending("");
    }
  }

  async function createPairing() {
    await action("pairing", async () => {
      const response = await api.createPairing(snapshot.room.id, deviceId);
      setPairing(response.data);
    });
  }

  async function createInvitation() {
    await action("invitation", async () => {
      const response = await api.createRoomInvitation(
        snapshot.room.id,
        deviceId,
      );
      setInvitation(response.data.invitation_token);
    });
  }

  async function transition(target: GameSession["status"]) {
    if (!snapshot.session) return;
    await action("session", () =>
      api.transitionSession(
        snapshot.room.id,
        snapshot.session!,
        target,
        deviceId,
      ),
    );
  }

  const sessionAction = (() => {
    if (!snapshot.session)
      return {
        label: "Новая сессия",
        run: () => api.createSession(snapshot.room.id, deviceId),
      };
    const transitions: Partial<
      Record<
        GameSession["status"],
        { label: string; target: GameSession["status"] }
      >
    > = {
      PREPARATION: { label: "Открыть лобби", target: "LOBBY" },
      LOBBY: { label: "Начать игру", target: "ACTIVE" },
      ACTIVE: { label: "Пауза", target: "PAUSED" },
      PAUSED: { label: "Продолжить", target: "ACTIVE" },
    };
    const next = transitions[snapshot.session.status];
    return next
      ? { label: next.label, run: () => transition(next.target) }
      : undefined;
  })();

  return (
    <main className="dashboard">
      <header className="topbar">
        <div>
          <p className="eyebrow">ПАНЕЛЬ ВЕДУЩЕГО</p>
          <h1>{snapshot.room.name}</h1>
        </div>
        <div className="room-code" aria-label="Код комнаты">
          {snapshot.room.code}
        </div>
      </header>
      <ErrorNotice error={error} />
      <div className="dashboard-grid">
        {snapshot.session &&
          ["ACTIVE", "PAUSED"].includes(snapshot.session.status) && (
            <HostCombatPanel snapshot={snapshot} refresh={refresh} />
          )}
        <section className="card stack">
          <div className="section-heading">
            <div>
              <p className="eyebrow">ПОДКЛЮЧЕНИЕ</p>
              <h2>Пригласить игроков</h2>
            </div>
            <button
              className="primary"
              onClick={createPairing}
              disabled={pending === "pairing"}
            >
              {pending === "pairing" ? "Создаём…" : "Новый QR"}
            </button>
          </div>
          {pairing ? (
            <div className="pairing">
              <img src={pairing.qr_data_url} alt="QR-код подключения" />
              <div>
                <span>Короткий код</span>
                <strong>{pairing.short_code}</strong>
                <small>
                  Действует до{" "}
                  {new Date(pairing.expires_at).toLocaleTimeString()}
                </small>
                <button
                  className="danger-text"
                  onClick={() =>
                    action("pairing", () =>
                      api.revokePairing(snapshot.room.id, pairing.id, deviceId),
                    )
                  }
                >
                  Отозвать
                </button>
              </div>
            </div>
          ) : (
            <p className="muted">Создайте одноразовый QR или короткий код.</p>
          )}
          {snapshot.room.access_mode === "invitation" && (
            <div className="stack compact">
              <button className="secondary" onClick={createInvitation}>
                Создать пропуск в комнату
              </button>
              {invitation && <code className="secret">{invitation}</code>}
            </div>
          )}
        </section>

        <section className="card stack">
          <div className="section-heading">
            <div>
              <p className="eyebrow">СЕССИЯ</p>
              <h2>{snapshot.session?.status ?? "Нет активной"}</h2>
            </div>
            {sessionAction && (
              <button
                className="primary"
                onClick={() => action("session", sessionAction.run)}
                disabled={pending === "session"}
              >
                {sessionAction.label}
              </button>
            )}
          </div>
          {snapshot.session &&
            ["ACTIVE", "PAUSED"].includes(snapshot.session.status) && (
              <button
                className="danger"
                onClick={() => transition("COMPLETED")}
              >
                Завершить сессию
              </button>
            )}
        </section>

        <section className="card stack span-2">
          <div className="section-heading">
            <div>
              <p className="eyebrow">ЛОББИ</p>
              <h2>Участники · {snapshot.players?.length ?? 0}</h2>
            </div>
          </div>
          <div className="participant-list">
            {snapshot.players?.map((player) => (
              <article key={player.id} className="participant">
                <div className="avatar">
                  {player.display_name.slice(0, 1).toUpperCase()}
                </div>
                <div>
                  <strong>{player.display_name}</strong>
                  <small>
                    {player.selected_character_id
                      ? "Персонаж выбран"
                      : "Выбирает персонажа"}
                  </small>
                </div>
              </article>
            ))}
            {!snapshot.players?.length && (
              <p className="muted">Игроки ещё не подключились.</p>
            )}
          </div>
          <h3>Устройства</h3>
          <div className="device-list">
            {snapshot.devices?.map((device) => (
              <div className="device-row" key={device.id}>
                <span>
                  <strong>{device.label}</strong>
                  <small>
                    {device.connection_state ?? "offline"} ·{" "}
                    {new Date(device.last_seen_at).toLocaleTimeString()}
                  </small>
                </span>
                {device.role !== "gm" && device.status === "active" && (
                  <button
                    className="danger-text"
                    onClick={() =>
                      action("revoke", () =>
                        api.revokeDevice(snapshot.room.id, device.id, deviceId),
                      )
                    }
                  >
                    Отключить
                  </button>
                )}
              </div>
            ))}
          </div>
        </section>

        <section className="card stack span-2">
          <p className="eyebrow">ДИАГНОСТИКА</p>
          <h2>Локальная сеть</h2>
          {diagnostics ? (
            <dl className="diagnostics">
              <div>
                <dt>Адреса</dt>
                <dd>
                  {diagnostics.addresses
                    .map((address) => `${address}:${diagnostics.port}`)
                    .join(", ")}
                </dd>
              </div>
              <div>
                <dt>WebSocket</dt>
                <dd>{diagnostics.websocket_connections}</dd>
              </div>
              <div>
                <dt>Курсор событий</dt>
                <dd>{diagnostics.event_cursor}</dd>
              </div>
              <div>
                <dt>SQLite</dt>
                <dd>{diagnostics.sqlite_journal_mode.toUpperCase()}</dd>
              </div>
              <div>
                <dt>Свободно</dt>
                <dd>
                  {Math.round(diagnostics.free_disk_bytes / 1024 / 1024)} МБ
                </dd>
              </div>
            </dl>
          ) : (
            <p className="muted">Получаем состояние…</p>
          )}
          <a
            className="button secondary"
            href="/api/v2/host/diagnostics/export"
            download
          >
            Скачать безопасный отчёт
          </a>
        </section>
      </div>
    </main>
  );
}
