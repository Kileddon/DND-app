# ADR-0005: Результат HTTPS/LAN security spike

- Статус: принято для alpha, пересмотреть перед публичным пилотом
- Дата: 2026-09-02

## Контекст

Host не имеет гарантированного DNS-имени, публичного домена или интернета. Игроки используют
личные Android/iOS устройства, на которые нельзя незаметно установить доверенный локальный CA.
Нужны честные границы HTTP alpha, cookie security и PWA.

## Исследованные варианты

1. Самоподписанный leaf certificate: шифрует трафик, но не даёт проверяемой identity и вызывает
   предупреждения/ошибки доверия.
2. Локальный CA: технически корректен, но требует установки и доверия root certificate на
   каждом телефоне. Apple прямо описывает это требование для local-network TLS.
3. Публичный CA + домен: хороший UX после выпуска, но требует управления доменом, DNS и
   сертификатами; offline bootstrap/renewal требует отдельного продукта.
4. HTTP в доверенной LAN: минимальный setup и работает без интернета, но трафик можно читать
   или изменять участнику сети.

## Решение alpha

Используем HTTP/WS только в доверенной частной LAN, без port forwarding. UI и README явно
предупреждают о границе. Credentials короткоживущие/отзываемые, не помещаются в query string;
cookie HttpOnly + SameSite=Strict, но без `Secure`. Compatibility API ограничен loopback.

Service worker и обещание installable PWA не включаются. Service Worker API требует secure
context; исключение для `http://localhost` не распространяется на `http://192.168.x.x`, который
видит телефон. Manifest остаётся подготовкой app shell.

Перед публичным пилотом требуется отдельный vertical slice: выбрать автоматизируемое доверие
TLS (публичный домен с локальным адресом либо управляемый локальный CA), включить HTTPS/WSS,
`Secure` cookie, HSTS после подтверждения recovery-пути и физически проверить Android Chrome и
iPhone Safari. Нужно также повторно проверить новые Local Network Access prompts Chromium.

## Источники

- [MDN: Secure contexts](https://developer.mozilla.org/en-US/docs/Web/Security/Secure_Contexts)
- [MDN: Service Worker API](https://developer.mozilla.org/en-US/docs/Web/API/Service_Worker_API)
- [Apple: Creating an Identity for Local Network TLS](https://developer.apple.com/documentation/network/creating-an-identity-for-local-network-tls)
- [Chrome: Local Network Access permission](https://developer.chrome.com/blog/local-network-access)

## Последствия

- Alpha нельзя безопасно использовать в публичной/недоверенной сети.
- Web app работает с host, но не получает secure-context возможности на телефоне.
- TLS не имитируется фиктивной настройкой, которую обычный пользователь не сможет безопасно
  пройти; переход имеет зафиксированный план и критерии.
