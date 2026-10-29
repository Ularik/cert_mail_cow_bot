# mail_messanger

Сервис следит за почтовым ящиком mailcow по IMAP (через IDLE, а если сервер его не поддерживает — периодическим опросом) и отправляет уведомление о каждом новом письме в Telegram.

## Запуск

```
pip install -r requirements.txt
python main.py --check   # проверить подключение к IMAP и Telegram
python main.py           # или: python -m mail_notifier
```

### Docker

```
docker compose run --rm mail-notifier python main.py --check   # проверка подключения
docker compose up -d --build                                   # запуск в фоне
docker compose logs -f                                         # логи
```

Параметры берутся из `.env` (через `env_file`, в образ файл не копируется). `state.json` хранится в томе `mail-notifier-data` (`/app/data/state.json` внутри контейнера), поэтому прогресс сохраняется при пересоздании контейнера.

Код разбит по слоям в пакете `mail_notifier/`. Подробное техническое описание — в [spec.md](spec.md).

## Параметры `.env`

Обязательные (уже есть): `TELEGRAM_API` (токен бота или URL `https://api.telegram.org/bot<токен>`),
`TELEGRAM_CHAT_ID`, `EMAIL_HOST`, `EMAIL_HOST_USER`, `EMAIL_HOST_PASSWORD`.

`EMAIL_PORT`/`EMAIL_USE_TLS` относятся к SMTP и не используются. Необязательные параметры IMAP:

| Параметр | По умолчанию |
|---|---|
| `IMAP_HOST` | `EMAIL_HOST` |
| `IMAP_PORT` | `993` (или `143` при `IMAP_SSL=false`) |
| `IMAP_SSL` | `true` (`false` — подключение через STARTTLS) |
| `IMAP_USER` / `IMAP_PASSWORD` | `EMAIL_HOST_USER` / `EMAIL_HOST_PASSWORD` |
| `IMAP_FOLDER` | `INBOX` |
| `IMAP_IDLE_TIMEOUT` | `300` с |
| `IMAP_POLL_INTERVAL` | `60` с (если нет IDLE) |
| `STATE_FILE` | `state.json` рядом со скриптом |
| `LOG_LEVEL` | `INFO` |

## Поведение

- Папка открывается только для чтения, поэтому письма не помечаются прочитанными.
- Последний обработанный UID хранится в `state.json`: после перезапуска пропущенные письма приходят, повторов нет. При первом запуске старые письма не отправляются.
- При обрыве соединения сервис переподключается с нарастающей задержкой (5 с → 5 мин).
- Если Telegram недоступен, письмо не считается обработанным и будет отправлено повторно.
