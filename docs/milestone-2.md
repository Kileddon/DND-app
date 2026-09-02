# Milestone 2 — Local Multiplayer Alpha

Статус: реализация и автоматизированные quality gates завершены; физические Wi-Fi/mobile
проверки остаются открыты в ручном checklist.

## Допущения

- Один Windows-host и один процесс FastAPI являются источником истины.
- Alpha используется только в доверенной частной LAN по HTTP/WS; internet exposure запрещён.
- Локальная identity не является облачным аккаунтом; дальнейшая привязка к аккаунту вне этапа.
- Presence transient, но room/player/device/selected character/session/event cursor durable.
- Простое обратимое решение для QR выбирает первый non-loopback IPv4; при VPN ГМ использует
  адрес из diagnostics и short code.

## Связь со сценариями

| Сценарий | Реализованная acceptance-цепочка | Проверка |
|---|---|---|
| `GM-03` | host → room → lobby → QR/code → device/player list → session start | API integration + Playwright |
| `P-02` | pairing → временный профиль → recovery → reconnect без интернета | API restart/recovery tests |
| `P-03` | open/password/invite policy, QR/short code, late join snapshot | domain + API integration |
| `P-04` | четыре раунда карточек → итог → атомарное confirm; restart draft API | unit + component + E2E |
| `P-07` | select/switch, один профиль на нескольких devices, realtime update | API/WS integration + E2E |
| `P-08` | add/discard stack, optimistic version, committed event | unit + API + component + E2E |
| `S-01` | visible reconnect, cursor replay либо role-filtered snapshot, dedup command | WS integration + component + E2E |
| `S-02` | restart host читает committed SQLite state и незавершённую session | restart + migration/backup tests |

## Definition of Done

- [x] Windows start script и production static delivery.
- [x] Pairing QR/short code, TTL/single-use/revoke/rotation.
- [x] Opaque device credentials, role checks и active disconnect on revoke.
- [x] Open/password/invite комнаты.
- [x] Временный профиль, recovery и несколько устройств.
- [x] Простой персонаж, выбор и inventory flow.
- [x] Полный session lifecycle и запрет второй незавершённой session.
- [x] Commit-before-broadcast, versioned events, cursor/snapshot/replay.
- [x] GM diagnostics и allowlisted export.
- [x] Backend/frontend/Playwright автоматизированные проверки.
- [x] HTTPS spike, threat model, ADR и Windows документация.
- [ ] Реальные Windows Firewall/Wi-Fi/Android Chrome/iPhone Safari проверки.

## Границы

В этап не входят cloud identity/sync, перенос между host, combat, monsters, scenes, media,
shared TV, advanced character builder, granular permissions, Windows installer и failover.
Полный перечень рисков: [threat model](security.md). Ручная приёмка:
[checklist](manual-test-checklist.md).
