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
            state_file=Path(os.getenv("STATE_FILE") or PROJECT_ROOT / "state.json"),
        )
