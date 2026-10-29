"""Работа с IMAP: подключение, ожидание новых писем (IDLE), их обработка."""

import email
import logging
import socket
import ssl
import time

from imapclient import IMAPClient
from imapclient.exceptions import IMAPClientError

from .config import Config
from .notification import HEADERS_ONLY, build_notification
from .state import State
from .telegram import Telegram, TelegramError, TelegramUnavailable

log = logging.getLogger(__name__)

# Письма крупнее этого размера не скачиваются целиком — в уведомление попадут только заголовки.
MAX_BODY_FETCH = 5 * 1024 * 1024


def connect(cfg: Config) -> IMAPClient:
    ssl_context = ssl.create_default_context()
    client = IMAPClient(
        cfg.imap_host,
        port=cfg.imap_port,
        ssl=cfg.imap_ssl,
        ssl_context=ssl_context,
        timeout=60,
    )
    if not cfg.imap_ssl:
        client.starttls(ssl_context)
    client.login(cfg.imap_user, cfg.imap_password)
    log.info("Подключено к %s:%s как %s", cfg.imap_host, cfg.imap_port, cfg.imap_user)
    return client


class MailWatcher:
    def __init__(self, config: Config, telegram: Telegram):
        self.cfg = config
        self.telegram = telegram
        self.state = State(config.state_file)

    def open_folder(self, client: IMAPClient) -> None:
        # readonly: сервис не должен помечать письма прочитанными.
        info = client.select_folder(self.cfg.imap_folder, readonly=True)
        uidvalidity = info[b"UIDVALIDITY"]
        if self.state.uidvalidity != uidvalidity:
            # Первый запуск (или ящик пересоздан): старые письма не присылаем,
            # начинаем отслеживать с текущего момента.
            if b"UIDNEXT" in info:
                last_uid = info[b"UIDNEXT"] - 1
            else:
                last_uid = max(client.search(["ALL"]), default=0)
            if self.state.uidvalidity is not None:
                log.warning("UIDVALIDITY изменился, отслеживание начинается заново")
            self.state.uidvalidity = uidvalidity
            self.state.last_uid = last_uid
            self.state.save()
        log.info(
            "Папка %s: %s писем, последний обработанный UID %s",
            self.cfg.imap_folder, info.get(b"EXISTS"), self.state.last_uid,
        )

    def process_new(self, client: IMAPClient) -> None:
        # Диапазон "N:*" всегда содержит максимальный UID, даже если он меньше N.
        uids = sorted(u for u in client.search(["UID", f"{self.state.last_uid + 1}:*"]) if u > self.state.last_uid)
        if not uids:
            return
        log.info("Новых писем: %d", len(uids))

        meta = client.fetch(uids, ["RFC822.SIZE", "BODY.PEEK[HEADER]"])
        for uid in uids:
            data = meta.get(uid)
            if data is None:  # письмо успели удалить
                self.state.last_uid = uid
                continue

            if data.get(b"RFC822.SIZE", 0) <= MAX_BODY_FETCH:
                raw = client.fetch([uid], ["BODY.PEEK[]"]).get(uid, {}).get(b"BODY[]")
            else:
                raw = None
            if raw:
                msg = email.message_from_bytes(raw)
            else:
                msg = email.message_from_bytes(data[b"BODY[HEADER]"])
                msg[HEADERS_ONLY] = "1"

            try:
                self.telegram.send(build_notification(msg, self.cfg.imap_folder))
                log.info("Уведомление отправлено: UID %s", uid)
            except TelegramUnavailable:
                # UID не сдвигаем — письмо будет обработано повторно после переподключения.
                raise
            except TelegramError as exc:
                log.error("Telegram отклонил уведомление для UID %s: %s", uid, exc)

            self.state.last_uid = uid
            self.state.save()

    def session(self) -> None:
        client = connect(self.cfg)
        try:
            self.open_folder(client)
            self.process_new(client)
            use_idle = client.has_capability("IDLE")
            if not use_idle:
                log.info("Сервер не поддерживает IDLE, опрос каждые %s с", self.cfg.poll_interval)

            while True:
                if use_idle:
                    client.idle()
                    try:
                        responses = client.idle_check(timeout=self.cfg.idle_timeout)
                    finally:
                        client.idle_done()
                    if responses:
                        log.debug("IDLE: %s", responses)
                else:
                    time.sleep(self.cfg.poll_interval)
                    client.noop()
                # Проверяем и по событию, и по таймауту — это же служит keepalive.
                self.process_new(client)
        finally:
            try:
                client.logout()
            except Exception:
                pass

    def run_forever(self) -> None:
        delay = 5
        while True:
            started = time.monotonic()
            try:
                self.session()
            except IMAPClientError as exc:
                if "authentication" in str(exc).lower() or "login" in str(exc).lower():
                    log.error("Ошибка авторизации IMAP: %s", exc)
                else:
                    log.error("Ошибка IMAP: %s", exc)
            except (OSError, socket.timeout, ssl.SSLError, TelegramError) as exc:
                log.error("Соединение потеряно: %s", exc)
            # Сбрасываем задержку, если сессия проработала долго.
            if time.monotonic() - started > 300:
                delay = 5
            log.info("Переподключение через %s с", delay)
            time.sleep(delay)
            delay = min(delay * 2, 300)
