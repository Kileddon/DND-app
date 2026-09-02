# ADR-0003: Realtime через cursor, snapshot и replay

- Статус: принято
- Дата: 2026-09-02

## Контекст

Мобильная сеть может кратковременно исчезать, а один персонаж открыт на нескольких устройствах.
Нельзя считать WebSocket надёжным журналом или публиковать изменение до фиксации SQLite.

## Решение

Каждое committed domain event получает монотонный cursor комнаты в той же транзакции, что и
изменение состояния. После commit API передаёт событие в in-process EventHub.

При WebSocket handshake устройство аутентифицируется и сообщает последний cursor. Сервер
выбирает incremental replay, если диапазон доступен и не превышает лимит; иначе отдаёт полный
role-filtered snapshot. Envelope имеет `schema_version=1`; неизвестная версия отклоняется.

Очередь каждого соединения ограничена, heartbeat выявляет оборванный socket, slow consumer
отключается с backpressure code и затем восстанавливается по cursor/snapshot. Presence живёт
только в runtime. Конфликтующие команды используют optimistic version и не перезаписывают
чужое изменение.

## Последствия

- Потерянная post-commit публикация восстанавливается из durable event log.
- Порядок определяется cursor, а не временем клиента.
- EventHub подходит одному host-процессу; multi-process или failover потребует durable broker
  либо иной fan-out механизм и нового ADR.
- Snapshot и event payload обязаны фильтроваться по роли и проверяются контрактными тестами.
