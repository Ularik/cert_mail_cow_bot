"""Отправка писем по SMTP и сохранение копии в папку «Отправленные» по IMAP."""

import logging
import smtplib
import ssl
from email import policy
from email.message import EmailMessage

from imapclient.imapclient import SENT
from imapclient.exceptions import IMAPClientError

from .config import Config
from .watcher import connect

log = logging.getLogger(__name__)


class Mailer:
    def __init__(self, config: Config):
        self.cfg = config

    def smtp(self) -> smtplib.SMTP:
        ssl_context = ssl.create_default_context()
        if self.cfg.smtp_ssl:
            server = smtplib.SMTP_SSL(self.cfg.smtp_host, self.cfg.smtp_port, timeout=30, context=ssl_context)
        else:
            server = smtplib.SMTP(self.cfg.smtp_host, self.cfg.smtp_port, timeout=30)
            if self.cfg.smtp_starttls:
                server.starttls(context=ssl_context)
        server.login(self.cfg.smtp_user, self.cfg.smtp_password)
        return server

    def send(self, msg: EmailMessage) -> None:
        with self.smtp() as server:
            server.send_message(msg)
        log.info("Письмо отправлено: %s", msg["To"])

    def save_to_sent(self, msg: EmailMessage) -> bool:
        """Кладёт копию письма в «Отправленные»: SMTP сам этого не делает."""
        if self.cfg.sent_folder == "":
            return True
        try:
            client = connect(self.cfg)
            try:
                folder = self.cfg.sent_folder or client.find_special_folder(SENT) or "Sent"
                client.append(folder, msg.as_bytes(policy=policy.SMTP), flags=[rb"\Seen"])
            finally:
                client.logout()
        except (IMAPClientError, OSError) as exc:
            log.error("Не удалось сохранить письмо в «Отправленные»: %s", exc)
            return False
        return True
