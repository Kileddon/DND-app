# Tabletop Companion — Local Multiplayer Alpha

Локальный помощник для настольной ролевой игры: Windows-ноутбук ГМа хранит состояние в
SQLite и раздаёт интерфейсы ГМа и игроков по одной Wi-Fi сети. После первоначальной
установки зависимостей интернет для игры не нужен.

В alpha реализованы защищённое подключение по QR или короткому коду, временный локальный
профиль и его восстановление, open/password/invite комнаты, выбор и простой конструктор
персонажа, несколько устройств одного игрока, полный lifecycle игровой сессии,
WebSocket-синхронизация, reconnect через cursor/snapshot и безопасная диагностика.

## Запуск на Windows одной командой

Нужны Windows 10/11, PowerShell, Git, [uv](https://docs.astral.sh/uv/) и Node.js 22+.
Из корня проекта выполните:

```powershell
powershell -NoProfile -ExecutionPolicy Bypass -File .\scripts\start-host.ps1
```

Скрипт синхронизирует Python-зависимости, при необходимости собирает frontend и запускает
host на `0.0.0.0:8000`. Откройте на ноутбуке ГМа `http://127.0.0.1:8000`. Чтобы пересобрать
уже существующий frontend:

```powershell
powershell -NoProfile -ExecutionPolicy Bypass -File .\scripts\start-host.ps1 -RebuildFrontend
```

Первый запуск создаёт `data/`, секрет хоста, SQLite БД и применяет Alembic-миграции. Перед
изменением непустой БД создаётся timestamped backup через SQLite backup API.

## Подключение игроков

1. ГМ создаёт комнату и pairing-приглашение.
2. Игрок сканирует QR системной камерой телефона или открывает LAN-адрес из диагностики и
   вводит короткий код.
3. Одноразовый pairing token обменивается на отзываемый device credential в HttpOnly cookie.
4. Игрок создаёт профиль либо восстанавливает его recovery-кодом и выбирает персонажа.

Если Windows запросит доступ брандмауэра, разрешите Python только для частных сетей. Телефон
и ноутбук должны быть в одной Wi-Fi сети без client isolation. LAN-адреса и порт показаны в
панели диагностики ГМа.

## Важная граница безопасности alpha

LAN-режим сейчас работает по HTTP/WS и предназначен только для доверенной частной сети.
Трафик не зашифрован, поэтому не запускайте host в публичной Wi-Fi сети и не публикуйте порт
в интернет. Долгоживущие credentials не передаются в URL; QR-секрет находится после `#` и
обменивается однократно. Password хранится как Argon2 hash, остальные секреты — как HMAC
digest. Compatibility API `/api/v1` доступен только с loopback-интерфейса хоста; LAN-клиенты
используют аутентифицированный `/api/v2`.

Service worker намеренно не включён: LAN HTTP не является secure context на мобильном
устройстве. Обоснование и путь к TLS описаны в
[ADR-0005](docs/adr/0005-https-lan-security.md) и [threat model](docs/security.md).

## Настройка

Локальный `.env` создаётся при необходимости из `.env.example`:

```dotenv
TTC_DATABASE_URL=sqlite:///data/tabletop_companion.sqlite3
TTC_HOST=0.0.0.0
TTC_PORT=8000
TTC_LOG_LEVEL=INFO
TTC_HOST_SECRET_PATH=data/host-secret.key
TTC_FRONTEND_DIST=frontend/dist
```

OpenAPI: `http://127.0.0.1:8000/docs`. Health check: `/health`. Production build frontend
раздаётся FastAPI с того же origin, что API и WebSocket.

## Разработка и проверки

Backend:

```powershell
uv sync --locked --all-groups
uv run ruff format --check .
uv run ruff check .
uv run mypy src tests
uv run pytest tests/unit
uv run pytest tests/integration
uv run pytest
```

Frontend:

```powershell
Set-Location frontend
npm ci
npm run format:check
npm run lint
npm run typecheck
npm run test
npm run build
npm run e2e
```

Для разработки запустите backend из корня, затем `npm run dev` из `frontend/`; Vite
проксирует `/api` на `127.0.0.1:8000`.

## Устранение проблем

- Телефон не открывает адрес: проверьте общую сеть, частный профиль Windows Firewall,
  отсутствие VPN/client isolation и правильность IP из диагностики.
- QR ведёт не туда: откройте отображённый LAN-адрес вручную и используйте короткий код;
  VPN-адаптер может оказаться первым в списке адресов.
- Код не принимается: pairing token одноразовый и ограничен по времени; ГМ создаёт новый.
- После сна видно reconnect: дождитесь синхронизации; клиент применит события после cursor
  либо получит полный snapshot.
- Порт занят: измените `TTC_PORT` в `.env` и перезапустите host.
- БД повреждена после внешнего вмешательства: остановите host и восстановите последний
  `.backup-*` файл; не копируйте активную WAL-БД обычным файловым копированием.

## Структура

```text
src/tabletop_companion/
  domain/          чистые сущности, правила, события и типизированные ошибки
  application/     команды, use cases и узкие boundary-протоколы
  infrastructure/  SQLite/SQLAlchemy, миграции, hashing и диагностика
  api/             HTTP/WebSocket transport, auth, rate limit и DTO
frontend/           React + TypeScript + Vite, component и Playwright tests
migrations/         Alembic revisions
tests/unit/         доменные-free от БД и сети
tests/integration/  API, SQLite, миграции, restart и realtime
docs/               архитектура, ADR, threat model и ручные проверки
```

Подробности: [архитектура](docs/architecture.md),
[Milestone 2](docs/milestone-2.md), [ручной checklist](docs/manual-test-checklist.md).

## Известные ограничения

Нет облачных аккаунтов/синхронизации, переноса персонажа между хостами, боя, сцен, медиа,
общего TV-экрана, расширенного конструктора, granular permission editor, Windows installer и
автоматического failover. HTTPS/PWA installation отложены до решения доверия сертификатам на
Android и iOS. Физические мобильные устройства должны быть проверены по ручному checklist.
