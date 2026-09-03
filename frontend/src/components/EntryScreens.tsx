import { type FormEvent, useMemo, useState } from "react";

import { api, type Device, type Room } from "../api";
import { ErrorNotice } from "./ErrorNotice";

export function WelcomeScreen({ onReady }: { onReady: () => void }) {
  const token = useMemo(() => {
    const marker = "#/pair/";
    return location.hash.startsWith(marker)
      ? location.hash.slice(marker.length)
      : undefined;
  }, []);
  const [shortCode, setShortCode] = useState("");
  const [pending, setPending] = useState(false);
  const [error, setError] = useState<unknown>();

  async function connect(event: FormEvent) {
    event.preventDefault();
    setPending(true);
    setError(undefined);
    try {
      await api.exchangePairing({
        token,
        shortCode: token ? undefined : shortCode.trim(),
      });
      history.replaceState(null, "", "/");
      onReady();
    } catch (reason) {
      setError(reason);
    } finally {
      setPending(false);
    }
  }

  return (
    <main className="centered">
      <section className="hero card">
        <p className="eyebrow">LOCAL MULTIPLAYER ALPHA</p>
        <h1>Tabletop Companion</h1>
        <p>
          Откройте стол вместе — интернет не нужен, только общая Wi‑Fi сеть.
        </p>
        <form onSubmit={connect} className="stack">
          {token ? (
            <p className="notice">Приглашение из QR-кода готово к обмену.</p>
          ) : (
            <label>
              Короткий код подключения
              <input
                value={shortCode}
                onChange={(event) =>
                  setShortCode(event.target.value.toUpperCase())
                }
                minLength={6}
                maxLength={16}
                autoCapitalize="characters"
                autoComplete="one-time-code"
                required
              />
            </label>
          )}
          <ErrorNotice error={error} />
          <button className="primary" disabled={pending}>
            {pending ? "Подключаем…" : "Подключиться как игрок"}
          </button>
        </form>
        <div className="divider">или на компьютере ведущего</div>
        <a className="button secondary" href="#/host">
          Создать комнату
        </a>
      </section>
    </main>
  );
}

export function HostSetup({ onReady }: { onReady: () => void }) {
  const [name, setName] = useState("Новая кампания");
  const [accessMode, setAccessMode] = useState<Room["access_mode"]>("open");
  const [password, setPassword] = useState("");
  const [pending, setPending] = useState(false);
  const [error, setError] = useState<unknown>();

  async function submit(event: FormEvent) {
    event.preventDefault();
    setPending(true);
    setError(undefined);
    try {
      await api.bootstrap({ name, accessMode, password });
      history.replaceState(null, "", "/");
      onReady();
    } catch (reason) {
      setError(reason);
    } finally {
      setPending(false);
    }
  }

  return (
    <main className="centered">
      <form className="card stack" onSubmit={submit}>
        <p className="eyebrow">КОМПЬЮТЕР ВЕДУЩЕГО</p>
        <h1>Создать комнату</h1>
        <label>
          Название кампании
          <input
            value={name}
            onChange={(event) => setName(event.target.value)}
            required
          />
        </label>
        <fieldset>
          <legend>Кто может войти</legend>
          {(["open", "password", "invitation"] as const).map((mode) => (
            <label className="radio" key={mode}>
              <input
                type="radio"
                name="access"
                value={mode}
                checked={accessMode === mode}
                onChange={() => setAccessMode(mode)}
              />
              {mode === "open"
                ? "Открытая"
                : mode === "password"
                  ? "С паролем"
                  : "По приглашению"}
            </label>
          ))}
        </fieldset>
        {accessMode === "password" && (
          <label>
            Пароль (не менее 10 символов)
            <input
              type="password"
              value={password}
              onChange={(event) => setPassword(event.target.value)}
              minLength={10}
              required
            />
          </label>
        )}
        <ErrorNotice error={error} />
        <button className="primary" disabled={pending}>
          {pending ? "Создаём…" : "Создать и открыть панель"}
        </button>
      </form>
    </main>
  );
}

export function ProfileSetup({
  device,
  onReady,
}: {
  device: Device;
  onReady: () => void;
}) {
  const [displayName, setDisplayName] = useState("");
  const [password, setPassword] = useState("");
  const [invitationToken, setInvitationToken] = useState("");
  const [pending, setPending] = useState(false);
  const [error, setError] = useState<unknown>();

  async function submit(event: FormEvent) {
    event.preventDefault();
    setPending(true);
    setError(undefined);
    try {
      await api.createProfile(device.id, {
        displayName,
        password,
        invitationToken,
      });
      onReady();
    } catch (reason) {
      setError(reason);
    } finally {
      setPending(false);
    }
  }

  return (
    <main className="centered">
      <form className="card stack" onSubmit={submit}>
        <h1>Ваш профиль за столом</h1>
        <label>
          Имя за столом
          <input
            value={displayName}
            onChange={(event) => setDisplayName(event.target.value)}
            required
          />
        </label>
        <label>
          Пароль комнаты, если нужен
          <input
            type="password"
            value={password}
            onChange={(event) => setPassword(event.target.value)}
          />
        </label>
        <label>
          Приглашение, если нужно
          <input
            value={invitationToken}
            onChange={(event) => setInvitationToken(event.target.value)}
          />
        </label>
        <ErrorNotice error={error} />
        <button className="primary" disabled={pending}>
          {pending ? "Подключаем…" : "Войти в комнату"}
        </button>
      </form>
    </main>
  );
}
