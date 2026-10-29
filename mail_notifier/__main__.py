"""Точка входа.

Запуск:
    python -m mail_notifier           # рабочий режим
    python -m mail_notifier --check   # только проверить подключение к IMAP и Telegram
"""

import argparse
import logging
import os
import signal
import sys

import requests
from imapclient.exceptions import IMAPClientError

from .config import Config
from .telegram import Telegram, TelegramError
from .watcher import MailWatcher, connect

log = logging.getLogger("mail_notifier")


def check(config: Config, telegram: Telegram) -> int:
    ok = True
    try:
        bot = telegram.get_me()
        log.info("Telegram: бот @%s доступен, chat_id=%s", bot.get("username"), config.telegram_chat_id)
    except (requests.RequestException, TelegramError, ValueError) as exc:
        log.error("Telegram: %s", exc)
        ok = False
    try:
        client = connect(config)
        info = client.select_folder(config.imap_folder, readonly=True)
        log.info("IMAP: папка %s, писем %s, IDLE=%s",
                 config.imap_folder, info.get(b"EXISTS"), client.has_capability("IDLE"))
        client.logout()
    except (IMAPClientError, OSError) as exc:
        log.error("IMAP: %s", exc)
        ok = False
    return 0 if ok else 1


def main() -> int:
    parser = argparse.ArgumentParser(description="Уведомления о новых письмах в Telegram")
    parser.add_argument("--check", action="store_true", help="проверить подключения и выйти")
    args = parser.parse_args()

    logging.basicConfig(
        level=os.getenv("LOG_LEVEL", "INFO").upper(),
        format="%(asctime)s %(levelname)s %(message)s",
    )
    config = Config.from_env()
    telegram = Telegram(config.telegram_token, config.telegram_chat_id)

    if args.check:
        return check(config, telegram)

    def stop(signum, _frame):
        raise KeyboardInterrupt
    signal.signal(signal.SIGTERM, stop)

    try:
        MailWatcher(config, telegram).run_forever()
    except KeyboardInterrupt:
        log.info("Остановлено")
    return 0


if __name__ == "__main__":
    sys.exit(main())
