# Архитектура Local Multiplayer Alpha

## Контекст

Приложение — локальный модульный монолит. Один Windows-host ГМа является источником истины,
хранит состояние в SQLite и обслуживает HTTP, WebSocket и production build React-клиента из
одного процесса. Облачных зависимостей в игровом runtime нет.

```text
Browser ── HTTP/WS ──> api ──> application ──> domain
                        │             │
                        │             v
                        └──── infrastructure ──> SQLite / host secret / filesystem
```

- `domain` использует только стандартную библиотеку: агрегаты, переходы, события и ошибки;
- `application` реализует use cases и зависит от узких UoW/hashing-протоколов;
- `infrastructure` реализует SQLAlchemy UoW, SQLite, Alembic, hashing и диагностику;
- `api` преобразует DTO в команды, аутентифицирует устройство и публикует уже сохранённые
  события;
- `frontend` — отдельная build-time часть; её статический результат обслуживает FastAPI.

Generic repository и универсального CRUD/service слоя нет. UoW содержит только операции,
необходимые текущим use cases.

## Транзакционная модель

Проект не использует полный event sourcing. Нормализованные таблицы хранят текущее состояние,
а `game_events` — append-only журнал значимых изменений.

Каждая изменяющая команда в одной SQLite-транзакции:

Последовательность обработки:

1. ищет `command_id`;
2. сверяет тип команды, actor и SHA-256 fingerprint канонического payload;
3. загружает и валидирует агрегат;
4. сохраняет состояние с optimistic version;
5. получает монотонный room cursor и добавляет версионированное событие;
6. сохраняет безопасный результат для idempotent replay;
7. выполняет commit.

WebSocket publication происходит только после commit. При rollback состояние, событие и
результат команды исчезают вместе. Если процесс завершился после commit, но до publication,
клиент догоняет состояние через cursor replay или snapshot.

SQLite работает с foreign keys, WAL и `busy_timeout`. Перед migration непустая file-backed БД
резервируется через SQLite backup API, включая согласованное состояние WAL.

## Pairing и локальная идентичность

Pairing invitation ограничен комнатой, ролью и TTL. Случайный token и короткий код хранятся
только как HMAC digest и допускают один обмен. QR содержит token во fragment URL, поэтому он
не попадает в HTTP request target или Referer. После обмена выдаётся отдельный opaque device
credential в HttpOnly/SameSite=Strict cookie; credential можно обновить и отозвать.

Device role (`GM` или `PLAYER`) проверяется при каждой команде. Профиль игрока отделён от
устройства, поэтому один игрок может восстановить identity на втором телефоне и управлять тем
же выбранным персонажем. Recovery code также хранится только как digest. Password комнаты
хешируется Argon2; invitation имеет TTL/max-use/revoke и никогда не выдаёт роль ГМа.

Старый `/api/v1` сохранён для совместимости первого среза, но middleware пропускает его только
с loopback хоста. Все LAN-команды проходят через authenticated `/api/v2`.

## Сессии

`GameSession` поддерживает только переходы:

```text
PREPARATION → LOBBY → ACTIVE ⇄ PAUSED
                         └──────┴──→ COMPLETED
```

На комнату существует максимум одна незавершённая сессия; это правило защищено доменом и
частичным уникальным индексом SQLite. Версия агрегата не даёт молча потерять конкурентный
переход. Завершение не удаляет игроков, персонажей или события.

## Realtime

Версионированный event envelope содержит `schema_version`, `event_id`, `cursor`, `room_id`,
`session_id`, `event_type`, `occurred_at`, `payload`. Неизвестная версия отклоняется явно.

При подключении клиент передаёт последний cursor:

- cursor находится в доступном диапазоне — сервер отправляет последующие события;
- cursor отсутствует, слишком стар или разрыв превышает лимит — сервер отправляет
  role-filtered snapshot;
- после initial sync события идут через bounded in-process queue;
- heartbeat обнаруживает оборванные соединения, queue overflow закрывает медленного клиента,
  а device revoke немедленно закрывает активные sockets.

Presence — transient transport state, а не доменная сущность. Состояния online/offline/
reconnecting объединяются со snapshot только на API-границе.

## Доставка web-клиента

React + TypeScript + Vite использует локальный state без тяжёлой state-management библиотеки.
Production assets статичны и обслуживаются FastAPI с того же origin. Клиент хранит только
последний cursor в local storage; credential недоступен JavaScript. Manifest есть, service
worker отсутствует до появления доверенного HTTPS в LAN.

## Диагностика и наблюдаемость

Структурные JSON-логи содержат command/error code, но не секреты. GM diagnostics показывает
LAN-адреса, hostname/port, access mode, connection/presence counts, cursor, SQLite/WAL/disk,
uptime и версии. Последние ошибки — bounded список только из timestamp и стабильного code.
Экспорт не включает credentials, password, invitation token или содержимое персонажей.

## Архитектурные решения

## Боевой контур

`Combat` управляет lifecycle, раундом и инициативой; `Combatant` инкапсулирует HP, временные HP, состояния и словесную категорию ранения; `DiceRoll` хранит исходный и скорректированный результат. Группа монстров — одна initiative entry со ссылками на несколько независимых combatants.

Бой использует ту же транзакционную модель command/state/event, что и остальная система. Отмена не удаляет и не меняет исходную запись журнала: фактические дельты обращаются новым событием. Итоговый отчёт сворачивает `report_delta` исходных и компенсирующих событий. HTTP snapshot, WebSocket broadcast и cursor replay проходят через одну role-aware проекцию видимости.

Подробности решения: [ADR-0006](adr/0006-combat-state-and-compensation.md).

- [ADR-0001: локальное состояние и журнал событий](adr/0001-local-state-and-event-log.md)
- [ADR-0002: pairing и device credentials](adr/0002-local-pairing-and-device-credentials.md)
- [ADR-0003: realtime cursor/snapshot/replay](adr/0003-realtime-cursor-snapshot-replay.md)
- [ADR-0004: React/Vite и static delivery](adr/0004-frontend-static-delivery.md)
- [ADR-0005: HTTPS/LAN security spike](adr/0005-https-lan-security.md)
