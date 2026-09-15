"""Промахи пайплайна (миграция в стор трейсов, Фаза 1).

Тот же интерфейс, что раньше (log_zero_result), но пишет в таблицу
quality_log внутри storage/traces.db, а не в отдельный JSONL.
Старый файл storage/logs/quality_log.jsonl остаётся как история.
"""

from __future__ import annotations

from backend.observability.store import TraceStore
from backend.utils.logger import setup_logger

logger = setup_logger("quality_log")

_store: TraceStore | None = None


def _get_store() -> TraceStore:
    global _store
    if _store is None:
        try:
            _store = TraceStore()
        except Exception as e:
            logger.warning("TraceStore unavailable: %s", e)
            _store = None
    return _store


def log_zero_result(question: str, stage: str, detail: str = "") -> None:
    """Промах пайплайна: пустой результат или неразрешённая сущность."""
    store = _get_store()
    if store is not None:
        store.log_quality(question, stage, detail)
