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

    def redact(self, text: object) -> str:
        # Ошибки requests содержат URL запроса, а в нём токен бота.
        return str(text).replace(self.base_url.rpartition("/bot")[2], "***")

    def get_me(self) -> dict:
        resp = self.session.get(f"{self.base_url}/getMe", timeout=15)
        data = resp.json()
        if not data.get("ok"):
            raise TelegramError(data.get("description", resp.text))
        return data["result"]

    def send(self, text: str, reply_to: int | None = None, attempts: int = 5) -> dict:
        """Отправляет сообщение и возвращает его (нужен message_id)."""
        payload = {
            "chat_id": self.chat_id,
            "text": text,
            "parse_mode": "HTML",
            "disable_web_page_preview": True,
        }
        if reply_to is not None:
            payload["reply_parameters"] = {"message_id": reply_to, "allow_sending_without_reply": True}
        for attempt in range(1, attempts + 1):
            try:
                resp = self.session.post(f"{self.base_url}/sendMessage", json=payload, timeout=30)
            except requests.RequestException as exc:
                log.warning("Telegram недоступен (попытка %d/%d): %s", attempt, attempts, self.redact(exc))
                time.sleep(min(2**attempt, 60))
                continue

            if resp.ok:
                return resp.json()["result"]
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

    def get_updates(self, offset: int | None, timeout: int = 50) -> list[dict]:
        """Long polling: ждёт новые сообщения боту до timeout секунд."""
        payload = {"timeout": timeout, "allowed_updates": ["message"]}
        if offset is not None:
            payload["offset"] = offset
        try:
            resp = self.session.post(f"{self.base_url}/getUpdates", json=payload, timeout=timeout + 15)
        except requests.RequestException as exc:
            raise TelegramUnavailable(self.redact(exc)) from None
        if resp.status_code == 429 or resp.status_code >= 500:
            raise TelegramUnavailable(f"{resp.status_code}: {resp.text}")
        if not resp.ok:
            # 409 — для бота задан webhook или запущен второй экземпляр сервиса.
            raise TelegramError(f"{resp.status_code}: {resp.text}")
        return resp.json()["result"]
