"""Загрузка настроек из .env."""

import os
from dataclasses import dataclass
from pathlib import Path

from dotenv import load_dotenv

from . import PROJECT_ROOT


def env_bool(name: str, default: bool) -> bool:
    value = os.getenv(name)
    if value is None or value.strip() == "":
        return default
    return value.strip().lower() in ("1", "true", "yes", "on")


@dataclass
class Config:
    imap_host: str
    imap_port: int
    imap_ssl: bool
    imap_user: str
    imap_password: str
    imap_folder: str
    telegram_token: str
    telegram_chat_id: str
    idle_timeout: int
    poll_interval: int
    state_file: Path
    replies_enabled: bool
    replies_file: Path
    telegram_allowed_users: frozenset[int]
    smtp_host: str
    smtp_port: int
    smtp_ssl: bool
    smtp_starttls: bool
    smtp_user: str
    smtp_password: str
    mail_from: str
    # None — найти по флагу \Sent, пустая строка — не сохранять копии.
    sent_folder: str | None

    @classmethod
    def from_env(cls) -> "Config":
        load_dotenv(PROJECT_ROOT / ".env")

        missing = [
            name
            for name in ("TELEGRAM_API", "TELEGRAM_CHAT_ID", "EMAIL_HOST_USER", "EMAIL_HOST_PASSWORD")
            if not os.getenv(name)
        ]
        if not (os.getenv("IMAP_HOST") or os.getenv("EMAIL_HOST")):
            missing.append("IMAP_HOST/EMAIL_HOST")
        if missing:
            raise SystemExit(f"В .env не заданы обязательные параметры: {', '.join(missing)}")

        # EMAIL_PORT/EMAIL_USE_TLS в .env относятся к SMTP (587), поэтому для IMAP
        # используются отдельные необязательные параметры: по умолчанию 993 + SSL.
        imap_ssl = env_bool("IMAP_SSL", True)
        # SMTP (ответы из Telegram) настраивается в формате Django: EMAIL_PORT/EMAIL_USE_TLS/EMAIL_USE_SSL.
        smtp_ssl = env_bool("EMAIL_USE_SSL", False)
        state_file = Path(os.getenv("STATE_FILE") or PROJECT_ROOT / "state.json")
        try:
            allowed_users = frozenset(int(x) for x in os.getenv("TELEGRAM_ALLOWED_USERS", "").replace(",", " ").split())
        except ValueError:
            raise SystemExit("TELEGRAM_ALLOWED_USERS: ожидаются числовые ID пользователей через запятую")
        return cls(
            imap_host=os.getenv("IMAP_HOST") or os.environ["EMAIL_HOST"],
            imap_port=int(os.getenv("IMAP_PORT") or (993 if imap_ssl else 143)),
            imap_ssl=imap_ssl,
            imap_user=os.getenv("IMAP_USER") or os.environ["EMAIL_HOST_USER"],
            imap_password=os.getenv("IMAP_PASSWORD") or os.environ["EMAIL_HOST_PASSWORD"],
            imap_folder=os.getenv("IMAP_FOLDER", "INBOX"),
            telegram_token=os.environ["TELEGRAM_API"],
            telegram_chat_id=os.environ["TELEGRAM_CHAT_ID"],
            # RFC 2177 рекомендует перезапускать IDLE не реже чем раз в 29 минут.
            idle_timeout=int(os.getenv("IMAP_IDLE_TIMEOUT", "300")),
            poll_interval=int(os.getenv("IMAP_POLL_INTERVAL", "60")),
            state_file=state_file,
            replies_enabled=env_bool("TELEGRAM_REPLIES", True),
            replies_file=Path(os.getenv("REPLIES_FILE") or state_file.with_name("replies.json")),
            telegram_allowed_users=allowed_users,
            smtp_host=os.getenv("SMTP_HOST") or os.getenv("EMAIL_HOST") or os.environ["IMAP_HOST"],
            smtp_port=int(os.getenv("EMAIL_PORT") or (465 if smtp_ssl else 587)),
            smtp_ssl=smtp_ssl,
            smtp_starttls=env_bool("EMAIL_USE_TLS", not smtp_ssl),
            smtp_user=os.environ["EMAIL_HOST_USER"],
            smtp_password=os.environ["EMAIL_HOST_PASSWORD"],
            mail_from=os.getenv("DEFAULT_FROM_EMAIL") or os.environ["EMAIL_HOST_USER"],
            sent_folder=os.getenv("IMAP_SENT_FOLDER"),
        )
