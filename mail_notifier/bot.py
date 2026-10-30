"""Приём ответов из Telegram: ответ (reply) на уведомление уходит отправителю письма."""

import html
import logging
import smtplib
import time

from .config import Config
from .mailer import Mailer
from .replies import ReplyStore, build_reply
from .telegram import Telegram, TelegramError

log = logging.getLogger(__name__)


class ReplyBot:
    def __init__(self, config: Config, store: ReplyStore):
        self.cfg = config
        self.store = store
        self.mailer = Mailer(config)
        # Отдельный клиент: requests.Session не стоит делить между потоками.
        self.telegram = Telegram(config.telegram_token, config.telegram_chat_id)

    def answer(self, message: dict, text: str) -> None:
        try:
            self.telegram.send(text, reply_to=message["message_id"])
        except TelegramError as exc:
            log.error("Не удалось ответить в Telegram: %s", exc)

    def handle(self, message: dict | None) -> None:
        if not message or str(message["chat"]["id"]) != str(self.cfg.telegram_chat_id):
            return  # сообщения из посторонних чатов игнорируются
        user = message.get("from") or {}
        if self.cfg.telegram_allowed_users and user.get("id") not in self.cfg.telegram_allowed_users:
            log.warning("Ответ от пользователя %s проигнорирован: его нет в TELEGRAM_ALLOWED_USERS", user.get("id"))
            return

        original = message.get("reply_to_message")
        if not original or not (original.get("from") or {}).get("is_bot"):
            # В группе это обычная переписка участников — молчим; подсказка только в личном чате.
            if message["chat"].get("type") == "private":
                self.answer(message, "Чтобы ответить на письмо, используйте «Ответить» на уведомлении о нём.")
            return
        target = self.store.get(original["message_id"])
        if target is None:
            self.answer(message, "Не нашёл письмо для этого сообщения: отвечать можно только на уведомления о новых письмах.")
            return
        text = message.get("text")
        if not text:
            self.answer(message, "Поддерживаются только текстовые ответы.")
            return

        reply = build_reply(target, text, self.cfg.mail_from)
        try:
            self.mailer.send(reply)
        except (smtplib.SMTPException, OSError) as exc:
            log.error("Не удалось отправить ответ: %s", exc)
            self.answer(message, f"❌ Ответ не отправлен: {html.escape(str(exc))}")
            return
        result = f"✅ Ответ отправлен: {html.escape(str(reply['To']))}"
        if not self.mailer.save_to_sent(reply):
            result += "\n<i>Копию не удалось сохранить в «Отправленные».</i>"
        self.answer(message, result)

    def run_forever(self) -> None:
        log.info("Приём ответов из Telegram включён")
        offset = self.store.last_update_id + 1 if self.store.last_update_id else None
        while offset is None:
            # Первый запуск: накопившиеся старые сообщения не обрабатываем, как и старые письма.
            try:
                backlog = self.telegram.get_updates(-1, timeout=0)
            except TelegramError as exc:
                log.error("Telegram getUpdates: %s", exc)
                time.sleep(30)
                continue
            offset = backlog[-1]["update_id"] + 1 if backlog else 0
            if backlog:
                self.store.mark_update(backlog[-1]["update_id"])
        while True:
            try:
                updates = self.telegram.get_updates(offset)
            except TelegramError as exc:
                log.error("Telegram getUpdates: %s", exc)
                time.sleep(30)
                continue
            for update in updates:
                offset = update["update_id"] + 1
                if update["update_id"] <= self.store.last_update_id:
                    continue
                # Отмечаем update сразу после обработки, даже при ошибке: повторная
                # отправка письма после перезапуска хуже, чем потерянный ответ.
                try:
                    self.handle(update.get("message"))
                except Exception:
                    log.exception("Ошибка при обработке сообщения из Telegram")
                self.store.mark_update(update["update_id"])
