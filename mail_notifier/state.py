"""Хранение прогресса обработки между перезапусками."""

import json
import logging
from pathlib import Path

log = logging.getLogger(__name__)


class State:
    """Хранит UIDVALIDITY и последний обработанный UID, чтобы после перезапуска
    не терять письма и не присылать повторные уведомления."""

    def __init__(self, path: Path):
        self.path = path
        self.uidvalidity: int | None = None
        self.last_uid: int = 0
        if path.exists():
            try:
                data = json.loads(path.read_text(encoding="utf-8"))
                self.uidvalidity = data.get("uidvalidity")
                self.last_uid = int(data.get("last_uid", 0))
            except (ValueError, OSError) as exc:
                log.warning("Не удалось прочитать %s (%s), состояние будет создано заново", path, exc)

    def save(self) -> None:
        # Запись через временный файл, чтобы не оставить битый JSON при падении.
        tmp = self.path.with_suffix(".tmp")
        tmp.write_text(
            json.dumps({"uidvalidity": self.uidvalidity, "last_uid": self.last_uid}),
            encoding="utf-8",
        )
        tmp.replace(self.path)
