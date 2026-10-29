"""Запуск сервиса из корня проекта: python main.py [--check]
(то же самое, что python -m mail_notifier)."""

import sys

from mail_notifier.__main__ import main

if __name__ == "__main__":
    sys.exit(main())
