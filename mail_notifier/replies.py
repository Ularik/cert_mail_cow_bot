"""Ответы на письма из Telegram: связь уведомлений с письмами и сборка ответного письма."""

import json
import logging
import re
import threading
from email.message import EmailMessage, Message
from email.utils import formataddr, formatdate, getaddresses, make_msgid, parseaddr
from pathlib import Path

from .parser import decode_str, format_addresses

log = logging.getLogger(__name__)

# Сколько последних уведомлений помнить: на более старые ответить уже не получится.
MAX_ENTRIES = 1000


def reply_target(msg: Message) -> dict | None:
    """Данные письма, нужные для ответа на него; None, если отвечать некому."""
    to = [
        [decode_str(name), addr]
        for name, addr in getaddresses([msg.get("Reply-To") or msg.get("From") or ""])
        if addr
    ]
    if not to:
        return None
    return {
        "to": to,
        "sender": format_addresses(msg.get("From")),
        # Свёрнутые (многострочные) заголовки нельзя переносить в новое письмо как есть.
        "subject": " ".join(decode_str(msg.get("Subject")).split()),
        "message_id": "".join((msg.get("Message-ID") or "").split()),
        "references": " ".join((msg.get("References") or "").split()),
    }


def build_reply(target: dict, text: str, from_addr: str) -> EmailMessage:
    reply = EmailMessage()
    reply["From"] = from_addr
    reply["To"] = ", ".join(formataddr((name, addr)) for name, addr in target["to"])
    subject = target["subject"] or ""
    if not re.match(r"(?i)^\s*(re|ответ)\s*:", subject):
        subject = f"Re: {subject}".strip()
    reply["Subject"] = subject
    reply["Date"] = formatdate(localtime=True)
    domain = parseaddr(from_addr)[1].rpartition("@")[2] or None
    reply["Message-ID"] = make_msgid(domain=domain)
    # In-Reply-To/References: почтовые клиенты покажут ответ в той же цепочке.
    if target["message_id"]:
        reply["In-Reply-To"] = target["message_id"]
        reply["References"] = " ".join(filter(None, [target["references"], target["message_id"]]))
    reply.set_content(text)
    return reply


class ReplyStore:
    """Хранит соответствие «сообщение в Telegram → письмо» и последний обработанный
    update_id бота. Используется из двух потоков (watcher и бот), поэтому под замком."""

    def __init__(self, path: Path):
        self.path = path
        self.lock = threading.Lock()
        self.messages: dict[str, dict] = {}
        self.last_update_id = 0
        if path.exists():
            try:
                data = json.loads(path.read_text(encoding="utf-8"))
                self.messages = dict(data.get("messages", {}))
                self.last_update_id = int(data.get("last_update_id", 0))
            except (ValueError, OSError) as exc:
                log.warning("Не удалось прочитать %s (%s), ответы на старые уведомления недоступны", path, exc)

    def remember(self, message_id: int, target: dict) -> None:
        with self.lock:
            self.messages[str(message_id)] = target
            for key in list(self.messages)[:-MAX_ENTRIES]:
                del self.messages[key]
            self.save()

    def get(self, message_id: int) -> dict | None:
        with self.lock:
            return self.messages.get(str(message_id))

    def mark_update(self, update_id: int) -> None:
        with self.lock:
            self.last_update_id = update_id
            self.save()

    def save(self) -> None:
        # Запись через временный файл, чтобы не оставить битый JSON при падении.
        tmp = self.path.with_suffix(".tmp")
        tmp.write_text(
            json.dumps({"last_update_id": self.last_update_id, "messages": self.messages}, ensure_ascii=False),
            encoding="utf-8",
        )
        tmp.replace(self.path)
