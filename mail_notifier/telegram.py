"""Клиент Telegram Bot API."""

import logging
import time

import requests

log = logging.getLogger(__name__)


class TelegramError(Exception):
    """Telegram отклонил запрос (4xx): повтор не поможет."""


class TelegramUnavailable(TelegramError):
    """Telegram временно недоступен: сообщение стоит отправить позже."""


class Telegram:
    def __init__(self, token: str, chat_id: str):
        # TELEGRAM_API может быть как голым токеном, так и URL вида https://api.telegram.org/bot<токен>
        token = token.strip().rstrip("/")
        if token.startswith("http"):
            self.base_url = token
        else:
            self.base_url = f"https://api.telegram.org/bot{token}"
        self.chat_id = chat_id
        self.session = requests.Session()

    def get_me(self) -> dict:
        resp = self.session.get(f"{self.base_url}/getMe", timeout=15)
        data = resp.json()
        if not data.get("ok"):
            raise TelegramError(data.get("description", resp.text))
        return data["result"]

    def send(self, text: str, attempts: int = 5) -> None:
        payload = {
            "chat_id": self.chat_id,
            "text": text,
            "parse_mode": "HTML",
            "disable_web_page_preview": True,
        }
        for attempt in range(1, attempts + 1):
            try:
                resp = self.session.post(f"{self.base_url}/sendMessage", json=payload, timeout=30)
            except requests.RequestException as exc:
                log.warning("Telegram недоступен (попытка %d/%d): %s", attempt, attempts, exc)
                time.sleep(min(2**attempt, 60))
                continue

            if resp.ok:
                return
            if resp.status_code == 429:
                retry_after = resp.json().get("parameters", {}).get("retry_after", 5)
                log.warning("Telegram просит подождать %s с", retry_after)
                time.sleep(retry_after + 1)
                continue
            if resp.status_code >= 500:
                log.warning("Ошибка сервера Telegram %s (попытка %d/%d)", resp.status_code, attempt, attempts)
                time.sleep(min(2**attempt, 60))
                continue
            # 4xx: повтор не поможет (неверный токен, chat_id, разметка).
            raise TelegramError(f"{resp.status_code}: {resp.text}")
        raise TelegramUnavailable("не удалось отправить сообщение после нескольких попыток")
