"""Append-only журнал качества выдачи (Фаза 2/6 плана упрощения пайплайна).

Минимальная версия: каждый промах классификации/резолюции — одна JSON-строка
в storage/logs/quality_log.jsonl. Еженедельный аудит — grep'ом по stage.
Никакой БД и ротации на этом этапе: файл дешёвый, structured-логирование
уже есть в backend/utils/logger.py для операционных событий.
"""

from __future__ import annotations

import json
from datetime import datetime, timezone
from pathlib import Path

from backend.utils.logger import setup_logger

logger = setup_logger("quality_log")

_LOG_PATH = Path(__file__).resolve().parent.parent.parent / "storage" / "logs" / "quality_log.jsonl"


def log_zero_result(question: str, stage: str, detail: str = "") -> None:
    """Промах пайплайна: пустой результат или неразрешённая сущность."""
    entry = {
        "ts": datetime.now(timezone.utc).isoformat(timespec="seconds"),
        "question": question,
        "stage": stage,
        "detail": detail,
    }
    try:
        _LOG_PATH.parent.mkdir(parents=True, exist_ok=True)
        with _LOG_PATH.open("a", encoding="utf-8") as f:
            f.write(json.dumps(entry, ensure_ascii=False) + "\n")
    except OSError as e:
        logger.warning("quality_log write failed: %s", e)
