# ADR-0002: Local pairing и device credentials

- Статус: принято
- Дата: 2026-09-02

## Контекст

Телефон игрока подключается к Windows-host в общей Wi-Fi сети без облачного аккаунта. Адрес
может быть известен любому участнику LAN, поэтому знание URL не должно давать право выполнять
команды. Требуются QR/короткий код, повторное подключение, несколько устройств и немедленный
revoke.

## Решение

Используем два разных секрета:

1. Краткоживущее pairing invitation привязано к room и role, одноразово и отзываемо. Token
   генерируется CSPRNG; token и short code сохраняются только как HMAC digest.
2. После успешного обмена выдаётся отдельный случайный opaque device credential. Сервер хранит
   digest, а браузер получает credential в HttpOnly, SameSite=Strict cookie. Credential имеет
   срок жизни, rotation и revoke.

QR передаёт одноразовый token после `#`; fragment не отправляется серверу и клиент обменивает
его через POST body. Долгоживущий credential не помещается в URL или local storage. Device
role/room/player проверяются при каждой команде. Room password хранится как Argon2 hash;
recovery и room invitation secrets — как digest. Попытки обмена и входа ограничиваются по IP.

## Последствия

- Утечка pairing token ограничена TTL, room/role и одним использованием.
- Revoke не требует blacklist JWT и закрывает активные WebSocket соединения.
- Смена host secret делает прежние digest непроверяемыми; файл секрета должен резервироваться
  вместе с БД и не попадать в репозиторий.
- В HTTP alpha cookie нельзя пометить `Secure`; это принимается только для доверенной LAN и
  пересматривается вместе с TLS в ADR-0005.
