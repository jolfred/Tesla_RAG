"""Шим обратной совместимости (Milestone A).

Канонизация имён живёт в backend/common/canon.py.
Этот модуль только реэкспортирует имена, чтобы не трогать writer,
indexer и тесты в рамках Milestone A.
Новых импортов отсюда не добавлять — импортируйте из backend.common.canon.
"""

from backend.common.canon import (
    ROLE_WORDS,
    SYNONYMS,
    merge_key,
    normalize_id,
    parse_ex_person,
    person_key,
    yo_normalize,
)

__all__ = [
    "ROLE_WORDS",
    "SYNONYMS",
    "merge_key",
    "normalize_id",
    "parse_ex_person",
    "person_key",
    "yo_normalize",
]
