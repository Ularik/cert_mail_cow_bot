# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Overview

Python service (package `mail_notifier/`) that watches a mailcow mailbox over IMAP and posts a notification to Telegram for each new message. A Telegram reply to a notification is sent back to the email's sender over SMTP. User-facing text (logs, notifications, README, spec.md) is in Russian — keep it that way. `spec.md` is the full technical spec; update it when behavior, config, or module layout changes.

## Commands

Windows, project venv in `.venv` (Python 3.13). No test suite or linter is configured.

```
.venv\Scripts\python.exe -m pip install -r requirements.txt
.venv\Scripts\python.exe main.py --check   # verify IMAP login + Telegram getMe, sends nothing
.venv\Scripts\python.exe main.py           # run the service (same as: python -m mail_notifier)
```

`--check` is the safe way to test against the real server. A normal run is also safe on a fresh `state.json` (it does not notify about existing mail), but it will send real Telegram messages for anything new.

To test formatting offline, build an `email.message.EmailMessage` and pass it to `mail_notifier.notification.build_notification(msg, "INBOX")`.

## Configuration gotchas

- `.env` was written for Django-style SMTP: `EMAIL_PORT=587` / `EMAIL_USE_TLS` / `EMAIL_USE_SSL` are **SMTP settings, used only for Telegram replies** (`mailer.py`). IMAP uses separate optional `IMAP_*` vars, defaulting to `EMAIL_HOST`, port 993, implicit SSL (`IMAP_SSL=false` → port 143 + STARTTLS). Full list in spec.md §4.
- `TELEGRAM_API` in `.env` holds a full URL `https://api.telegram.org/bot<token>`, not a bare token; `Telegram.__init__` accepts both forms.
- `.env` and `state.json` are resolved relative to `PROJECT_ROOT` (`mail_notifier/__init__.py`), not the CWD.
- Never print `.env` values — mask secrets when inspecting.

## Architecture

Layers, with dependencies pointing downward only: `__main__` (CLI/signals/`--check`) → `config` + `watcher` (IMAP lifecycle) → `state`, `notification` (→ `parser`), `replies`, `telegram`; and `__main__` → `bot` (daemon thread `reply-bot`) → `mailer`, `replies`, `telegram`. Only `watcher` talks IMAP, plus `mailer` for the `APPEND` to Sent (via `watcher.connect`). `parser`/`notification`/`replies`/`state`/`telegram` are IMAP-agnostic.

Replies (spec.md §13): `watcher` stores `message_id of notification → reply_target(msg)` in `ReplyStore` (`replies.json`, shared by both threads under a lock, capped at 1000). `ReplyBot` long-polls `getUpdates` with its own `Telegram` instance, accepts only replies to bot messages in `TELEGRAM_CHAT_ID` (optionally `TELEGRAM_ALLOWED_USERS`), and persists `last_update_id` after each update even on error — at-most-once, so an email is never sent twice. `ReplyBot.handle(message)` can be tested offline by stubbing `bot.mailer.send`/`save_to_sent` and `bot.telegram.send`.

Flow: `MailWatcher.run_forever` (reconnect loop, 5s→300s backoff) → `session()` → `connect`, `open_folder`, `process_new`, then an IDLE loop (NOOP polling if the server lacks IDLE).

Key invariants to preserve in `watcher.process_new` / `State`:

- **No message loss, no duplicates** via `state.json` (`uidvalidity`, `last_uid`). `last_uid` is advanced and saved after each message is handled. On first run or a UIDVALIDITY change, `last_uid` is set to `UIDNEXT-1`, so backlog is intentionally skipped.
- IMAP `UID N:*` always returns the highest UID even when it is < N, so results are filtered with `u > last_uid`.
- The folder is selected `readonly=True` and fetched with `BODY.PEEK[]`: the service must never mark mail as read.
- `TelegramUnavailable` (subclass of `TelegramError`) means transient failure. It propagates without advancing `last_uid`, so the message is resent after reconnect. A plain `TelegramError` (4xx) is logged and the UID is skipped to avoid an infinite loop.
- Messages larger than `MAX_BODY_FETCH` (5 MB) are fetched headers-only. This is marked with the `HEADERS_ONLY` synthetic header that `build_notification` checks.
- Notifications use Telegram `parse_mode=HTML`; all email-derived text must go through `html.escape`. Length is capped against `TELEGRAM_MAX_LEN` (4096).
