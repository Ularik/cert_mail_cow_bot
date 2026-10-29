"""Сервис уведомлений: следит за почтовым ящиком mailcow по IMAP и пересылает
сведения о новых письмах в Telegram."""

from pathlib import Path

# Корень проекта: здесь лежат .env и state.json.
PROJECT_ROOT = Path(__file__).resolve().parent.parent
