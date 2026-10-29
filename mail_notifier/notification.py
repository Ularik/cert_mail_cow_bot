"""Формирование текста уведомления для Telegram (parse_mode=HTML)."""

import html
from email.message import Message
from email.utils import parsedate_to_datetime

from .parser import decode_str, extract_body, format_addresses

TELEGRAM_MAX_LEN = 4096
SNIPPET_LEN = 700
# Служебный заголовок: письмо загружено без тела (слишком большое).
HEADERS_ONLY = "X-Headers-Only"


def build_notification(msg: Message, folder: str) -> str:
    subject = decode_str(msg.get("Subject")) or "(без темы)"
    sender = format_addresses(msg.get("From")) or "неизвестно"
    recipients = format_addresses(msg.get("To"))
    headers_only = bool(msg.get(HEADERS_ONLY))

    date_str = ""
    if msg.get("Date"):
        try:
            date_str = parsedate_to_datetime(msg["Date"]).astimezone().strftime("%d.%m.%Y %H:%M")
        except (TypeError, ValueError):
            date_str = msg["Date"]

    body, attachments = ("", []) if headers_only else extract_body(msg)

    esc = html.escape
    lines = ["📧 <b>Новое письмо</b>" + (f" ({esc(folder)})" if folder.upper() != "INBOX" else "")]
    lines.append(f"<b>От:</b> {esc(sender)}")
    if recipients:
        lines.append(f"<b>Кому:</b> {esc(recipients)}")
    lines.append(f"<b>Тема:</b> {esc(subject)}")
    if date_str:
        lines.append(f"<b>Дата:</b> {esc(date_str)}")
    if attachments:
        lines.append(f"📎 <b>Вложения:</b> {esc(', '.join(attachments))}")
    if headers_only:
        lines.append("<i>Письмо слишком большое, текст не загружен.</i>")

    header = "\n".join(lines)
    if body:
        budget = min(SNIPPET_LEN, TELEGRAM_MAX_LEN - len(header) - 50)
        snippet = body[:budget] + ("…" if len(body) > budget else "")
        return f"{header}\n\n<blockquote>{esc(snippet)}</blockquote>"
    return header
