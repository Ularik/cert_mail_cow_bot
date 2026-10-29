"""Разбор писем: декодирование заголовков, извлечение текста и вложений."""

import html
import re
from email.header import decode_header, make_header
from email.message import Message
from email.utils import getaddresses


def decode_str(value: str | None) -> str:
    if not value:
        return ""
    try:
        return str(make_header(decode_header(value)))
    except (UnicodeDecodeError, LookupError, ValueError):
        return value


def format_addresses(value: str | None) -> str:
    result = []
    for name, addr in getaddresses([value or ""]):
        name = decode_str(name)
        if name and addr:
            result.append(f"{name} <{addr}>")
        else:
            result.append(name or addr)
    return ", ".join(filter(None, result))


def part_text(part: Message) -> str:
    payload = part.get_payload(decode=True)
    if payload is None:
        return ""
    charset = part.get_content_charset() or "utf-8"
    try:
        return payload.decode(charset, errors="replace")
    except LookupError:
        return payload.decode("utf-8", errors="replace")


def html_to_text(raw: str) -> str:
    raw = re.sub(r"(?is)<(script|style|head).*?</\1>", " ", raw)
    raw = re.sub(r"(?i)<br\s*/?>|</p>|</div>", "\n", raw)
    return html.unescape(re.sub(r"<[^>]+>", " ", raw))


def extract_body(msg: Message) -> tuple[str, list[str]]:
    """Возвращает (текст письма, список имён вложений)."""
    plain, html_body, attachments = None, None, []
    for part in msg.walk():
        if part.is_multipart():
            continue
        filename = part.get_filename()
        if filename or part.get_content_disposition() == "attachment":
            attachments.append(decode_str(filename) or "без имени")
            continue
        ctype = part.get_content_type()
        if ctype == "text/plain" and plain is None:
            plain = part_text(part)
        elif ctype == "text/html" and html_body is None:
            html_body = part_text(part)

    text = plain if plain and plain.strip() else html_to_text(html_body or "")
    text = re.sub(r"[ \t\r\f\v]+", " ", text)
    text = re.sub(r"\n\s*\n+", "\n\n", text).strip()
    return text, attachments
