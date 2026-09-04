# Threat model Local Multiplayer Alpha

## Активы и границы доверия

Защищаются: device/pairing/invitation credentials, room password, приватное состояние
ГМа, персонажи, inventory, event log и целостность session lifecycle. Host-процесс и локальные
файлы Windows считаются доверенными; браузер игрока, входящие HTTP/WS данные и остальные
устройства LAN — недоверенными. Интернет и cloud в runtime отсутствуют.

## Основные угрозы и меры

| Угроза | Меры alpha | Остаточный риск |
|---|---|---|
| Подбор pairing/room password | CSPRNG token, TTL, single use, revoke, short-code и login rate limit, Argon2 | DoS с множества IP в LAN |
| Утечка URL в log/Referer | Одноразовый pairing secret только во fragment, обмен через POST | История/скриншот браузера может раскрыть token до обмена |
| Кража credential через JS | HttpOnly, SameSite=Strict, opaque revocable credential, rotation | HTTP позволяет сетевому атакующему перехватить cookie |
| Повтор команды | command ID + type/actor/payload fingerprint, сохранённый безопасный result | Клиент обязан использовать новый ID для новой операции |
| Подмена роли/объекта | Проверка authenticated device, room, role, player и ownership на каждой v2-команде | `/api/v1` допустим только с loopback хоста |
| Silent concurrent overwrite | Optimistic version и `409 state_conflict` | UI должен повторить действие только после обновления |
| Событие до commit | State, cursor, event и result в одной транзакции; publish только после commit | Сбой publication требует reconnect/replay |
| Медленный/злой WS client | Auth handshake limit, room/device caps, bounded queue, heartbeat, disconnect | Один процесс остаётся точкой отказа |
| Утечка через diagnostics/logs | Safe error code+timestamp, allowlisted diagnostics, no content/secrets | Адреса и размеры БД видны ГМу |
| Повреждение/несовместимая миграция | WAL, FK, backup API, revision tests, restore test | Нет автоматического failover |
| MITM/прослушивание Wi-Fi | Предупреждение trusted-LAN-only, no port forwarding, short-lived/revocable secrets | Трафик HTTP/WS не зашифрован |

## Security-инварианты

- Plaintext password, host secret, device/pairing/invitation token не сохраняются в БД,
  журнале событий, structured logs или diagnostic export.
- Player snapshot/replay не содержит GM-only events и секретных полей.
- Revoke блокирует новые HTTP-команды и закрывает существующие WebSocket соединения.
- Неизвестный `schema_version` не интерпретируется молча.
- Network publication никогда не выполняется внутри открытой DB-транзакции.

## Не покрыто alpha

Нет защиты от администратора Windows-host, malware на host/телефоне, физического доступа к
разблокированному устройству, hostile access point/MITM, публичного internet exposure и
distributed denial of service. HTTPS/WSS и `Secure` cookie обязательны до использования вне
доверенной частной LAN; решение зафиксировано в ADR-0005.
