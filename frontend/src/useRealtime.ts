import { useEffect, useRef, useState } from "react";

import type { ConnectionState } from "./api";

interface RealtimeMessage {
  type?: string;
  schema_version: number;
  cursor?: number;
}

export function useRealtime(
  enabled: boolean,
  onChange: () => void,
): ConnectionState {
  const [state, setState] = useState<ConnectionState>(
    enabled ? "connecting" : "offline",
  );
  const callback = useRef(onChange);

  useEffect(() => {
    callback.current = onChange;
  }, [onChange]);

  useEffect(() => {
    if (!enabled) {
      return;
    }
    let stopped = false;
    let socket: WebSocket | undefined;
    let retryTimer: number | undefined;
    let attempt = 0;

    const connect = () => {
      if (stopped) return;
      setState(attempt === 0 ? "connecting" : "reconnecting");
      const cursor = Number(localStorage.getItem("ttc-event-cursor") ?? "0");
      const protocol = location.protocol === "https:" ? "wss:" : "ws:";
      socket = new WebSocket(
        `${protocol}//${location.host}/api/v2/realtime?cursor=${cursor}`,
      );
      socket.onopen = () => {
        attempt = 0;
        setState("online");
      };
      socket.onmessage = (event) => {
        const message = JSON.parse(String(event.data)) as RealtimeMessage;
        if (message.schema_version !== 1) {
          socket?.close(4400, "unsupported_schema");
          return;
        }
        if (message.type === "ping") {
          socket?.send(JSON.stringify({ type: "pong", schema_version: 1 }));
          return;
        }
        if (typeof message.cursor === "number") {
          localStorage.setItem("ttc-event-cursor", String(message.cursor));
          socket?.send(
            JSON.stringify({
              type: "ack",
              schema_version: 1,
              cursor: message.cursor,
            }),
          );
        }
        callback.current();
      };
      socket.onclose = (event) => {
        if (stopped || event.code === 4003) {
          setState("offline");
          return;
        }
        attempt += 1;
        setState("reconnecting");
        retryTimer = window.setTimeout(
          connect,
          Math.min(1000 * 2 ** attempt, 15000),
        );
      };
      socket.onerror = () => socket?.close();
    };

    connect();
    return () => {
      stopped = true;
      if (retryTimer !== undefined) window.clearTimeout(retryTimer);
      socket?.close(1000, "component_unmounted");
    };
  }, [enabled]);

  return state;
}
