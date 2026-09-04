import { useCallback, useEffect, useState } from "react";

import { ApiError, api, type Snapshot } from "./api";
import { ConnectionBadge } from "./components/ConnectionBadge";
import {
  HostSetup,
  ProfileSetup,
  WelcomeScreen,
} from "./components/EntryScreens";
import { ErrorNotice } from "./components/ErrorNotice";
import { HostDashboard } from "./components/HostDashboard";
import { PlayerDashboard } from "./components/PlayerDashboard";
import { useRealtime } from "./useRealtime";

export function App() {
  const [snapshot, setSnapshot] = useState<Snapshot>();
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<unknown>();
  const [route, setRoute] = useState(location.hash);

  const refresh = useCallback(async () => {
    try {
      const value = await api.snapshot();
      setSnapshot(value);
      setError(undefined);
    } catch (reason) {
      if (reason instanceof ApiError && reason.status === 401)
        setSnapshot(undefined);
      else setError(reason);
    } finally {
      setLoading(false);
    }
  }, []);

  useEffect(() => {
    let active = true;
    api
      .snapshot()
      .then((value) => {
        if (active) {
          setSnapshot(value);
          setError(undefined);
        }
      })
      .catch((reason: unknown) => {
        if (!active) return;
        if (reason instanceof ApiError && reason.status === 401)
          setSnapshot(undefined);
        else setError(reason);
      })
      .finally(() => {
        if (active) setLoading(false);
      });
    return () => {
      active = false;
    };
  }, []);

  useEffect(() => {
    const updateRoute = () => setRoute(location.hash);
    window.addEventListener("hashchange", updateRoute);
    return () => window.removeEventListener("hashchange", updateRoute);
  }, []);

  const isAwaitingProfile =
    snapshot?.device?.role === "player" && !snapshot.player;
  const connection = useRealtime(
    Boolean(snapshot) && !isAwaitingProfile,
    () => void refresh(),
  );

  if (loading) {
    return (
      <main className="centered">
        <div className="loader" role="status">
          Запускаем стол…
        </div>
      </main>
    );
  }
  if (!snapshot) {
    return route === "#/host" ? (
      <HostSetup onReady={refresh} />
    ) : (
      <WelcomeScreen onReady={refresh} />
    );
  }
  if (isAwaitingProfile) {
    return <ProfileSetup device={snapshot.device!} onReady={refresh} />;
  }

  return (
    <>
      <div className="connection-bar">
        <ConnectionBadge state={connection} />
      </div>
      <ErrorNotice error={error} />
      {snapshot.players ? (
        <HostDashboard snapshot={snapshot} refresh={refresh} />
      ) : (
        <PlayerDashboard snapshot={snapshot} refresh={refresh} />
      )}
    </>
  );
}
