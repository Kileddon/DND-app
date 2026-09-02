# Ручной checklist Local Multiplayer Alpha

Автоматизированный Chromium-сценарий не заменяет эти проверки. Отмечать пункт можно только на
указанном физическом устройстве и реальной Wi-Fi сети.

## Подготовка Windows-host

- [ ] Чистый Windows 10/11: старт одной командой из README.
- [ ] Windows Firewall разрешён только для Private networks.
- [ ] Host показывает корректные hostname, LAN IPv4, порт, WAL и версии.
- [ ] Production UI открывается с ноутбука по loopback и LAN IPv4.
- [ ] Перезапуск во время ACTIVE восстанавливает room/session/player/character/inventory.
- [ ] Diagnostic export не содержит password, token, credential, recovery code или character
      content.

## Android Chrome

- [ ] Телефон без мобильного интернета, но в общей Wi-Fi сети открывает LAN-адрес.
- [ ] Системная камера считывает QR и открывает правильный host, не `localhost`.
- [ ] Short code работает при уже открытом адресе.
- [ ] Создаются временный профиль и recovery code.
- [ ] После reload credential восстанавливает устройство без нового pairing.
- [ ] Потеря/возврат Wi-Fi показывает reconnect и приводит к converged state.
- [ ] Второе устройство того же игрока видит изменения inventory в realtime.
- [ ] Expired, consumed и revoked pairing tokens отклоняются.

## iPhone Safari

- [ ] iPhone без мобильного интернета, но в общей Wi-Fi сети открывает LAN-адрес.
- [ ] Camera QR flow и ручной short-code flow завершают pairing.
- [ ] HttpOnly cookie сохраняется после закрытия/повторного открытия вкладки.
- [ ] Background/foreground и краткая потеря Wi-Fi приводят к reconnect.
- [ ] Два устройства одного профиля сходятся по character/inventory state.
- [ ] Expired и revoked credentials не дают выполнять команды.

## Политики комнаты и lifecycle

- [ ] OPEN: новый профиль входит без password или invitation.
- [ ] PASSWORD: неверный password не раскрывает snapshot; верный password входит.
- [ ] INVITATION: token ограничен TTL/числом использований и revoke работает.
- [ ] Player invitation никогда не выдаёт GM role.
- [ ] PREPARATION → LOBBY → ACTIVE → PAUSED → ACTIVE → COMPLETED.
- [ ] Недопустимый переход и stale version возвращают понятный conflict.
- [ ] Late join в ACTIVE получает актуальный snapshot и выбранного персонажа.
- [ ] Device revoke немедленно отключает активный WebSocket и запрещает HTTP.

## Сетевые варианты

- [ ] Полностью отключённый интернет не мешает игре в LAN.
- [ ] Guest Wi-Fi/client isolation диагностируется как недоступность host с телефона.
- [ ] VPN выключен; затем включён — список адресов позволяет выбрать рабочий LAN IP.
- [ ] Sleep/wake Windows-host: клиенты переподключаются или показывают ясную ошибку.

## Статус на 2026-09-02

- [x] Windows 11 loopback, production build, Playwright Chromium critical flow.
- [ ] Реальная Wi-Fi сеть.
- [ ] Физический Android Chrome.
- [ ] Физический iPhone Safari.
- [ ] Windows Firewall prompt на чистой машине.
- [ ] Sleep/wake и guest Wi-Fi/client isolation.
