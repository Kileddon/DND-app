import type { ConnectionState } from "../api";

const labels: Record<ConnectionState, string> = {
  connecting: "Подключение…",
  online: "На связи",
  reconnecting: "Переподключение…",
  offline: "Нет связи",
};

export function ConnectionBadge({ state }: { state: ConnectionState }) {
  return (
    <span className={`connection connection--${state}`} role="status">
      <span aria-hidden="true">●</span> {labels[state]}
    </span>
  );
}
