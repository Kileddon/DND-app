# ADR-0004: React/Vite и static delivery

- Статус: принято
- Дата: 2026-09-02

## Контекст

Нужны mobile-first интерфейсы ГМа и игрока без интернета во время игры. Отдельный production
web-server и сложное client-state решение не оправданы локальной alpha.

## Решение

Используем TypeScript, React и Vite. Production build размещается в `frontend/dist` и
обслуживается FastAPI с того же origin, что HTTP API и WebSocket. Для разработки Vite запускает
отдельный server и проксирует `/api` на backend.

Состояние управляется React hooks; тяжёлая state-management библиотека не добавляется.
Credential находится только в HttpOnly cookie. Local storage содержит только последний cursor,
session storage — несекретный install identifier. Web manifest включён, service worker не
регистрируется до решения TLS.

## Последствия

- В игре нет зависимости от CDN или внешних шрифтов.
- Same-origin упрощает cookie auth и исключает production CORS-конфигурацию.
- Изменение frontend требует новой сборки; Windows start script собирает её при первом запуске
  или по `-RebuildFrontend`.
- Offline app-shell после полного выключения host пока недоступен: это осознанная граница alpha.
