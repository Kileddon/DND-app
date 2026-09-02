import { ApiError } from "../api";

export function ErrorNotice({ error }: { error: unknown }) {
  if (!error) return null;
  const isConflict = error instanceof ApiError && error.status === 409;
  const message = error instanceof Error ? error.message : "Неизвестная ошибка";
  return (
    <div
      className={
        isConflict ? "notice notice--conflict" : "notice notice--error"
      }
      role="alert"
    >
      <strong>
        {isConflict
          ? "Данные изменились на другом устройстве"
          : "Не удалось выполнить действие"}
      </strong>
      <span>{message}</span>
      {isConflict && <span>Обновите состояние и повторите действие.</span>}
    </div>
  );
}
