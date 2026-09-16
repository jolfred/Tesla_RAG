"""Слой 1: бесплатные детерминированные проверки ответа.

Логика — та же, что была в самописной наблюдаемости; меняется только
адресат: результат пишется Score в Langfuse (см. run_layer1).
Проверки не вероятностные и не заменяются LLM-судьёй.
"""
from __future__ import annotations

import re

from backend.observability import langfuse_client as _lf
from backend.utils.logger import setup_logger

logger = setup_logger("lf_checks")

_ISO_RE = re.compile(r"\b(20\d{2})-(\d{2})-(\d{2})\b")
_DMY_RE = re.compile(r"\b(\d{1,2})\.(\d{1,2})\.(19|20\d{2})\b")
_YEAR_RE = re.compile(r"\b((?:19|20)\d{2})\b")

_HIERARCHY_RE = re.compile(
    r"входит в состав|подчиня(ет|ют)ся|подразделение|дочерн|филиал|"
    r"подчинен|подчинён|структурное подразделение",
    re.IGNORECASE,
)
_HIERARCHY_EVIDENCE_RELS = {"PART_OF", "MEMBER_OF"}

_EMPTY_RE = re.compile(r"в архивах нет данных", re.IGNORECASE)


def _dates_in_text(text: str | None) -> tuple[set[str], set[str]]:
    """(полные даты ISO, годы) из произвольного текста."""
    full, years = set(), set()
    for m in _ISO_RE.finditer(text or ""):
        full.add(m.group(0))
        years.add(m.group(1))
    for m in _DMY_RE.finditer(text or ""):
        years.add(m.group(3))
    for m in _YEAR_RE.finditer(text or ""):
        years.add(m.group(1))
    return full, years


def _fact_dates(facts: list[dict]) -> tuple[set[str], set[str]]:
    """(полные даты ISO, годы) из строк фактов."""
    full, years = set(), set()
    for f in facts or []:
        for key in ("event_date", "observed_at", "date"):
            v = (f.get(key) or "") if isinstance(f, dict) else ""
            if not v:
                continue
            m = _ISO_RE.search(v)
            if m:
                full.add(m.group(0))
                years.add(m.group(1))
                continue
            m = _DMY_RE.search(v)
            if m:
                years.add(m.group(3))
                continue
            m = _YEAR_RE.search(v)
            if m:
                years.add(m.group(1))
    return full, years


def check_groundedness_of_dates(answer: str, facts: list[dict],
                                context_texts: list[str] | None = None) -> bool:
    """Каждая дата/год в ответе подтверждается фактами или контекстом,
    который получила модель (блок фактов + тексты постов).

    Модель цитирует не только строки графа: год истории штаба из карточки
    группы — не галлюцинация, если он был в её контексте. Ловит только
    выдуманные из ниоткуда даты. Точные ISO-даты строже bare-годов лишь
    тем, что требуют полного совпадения, а не года.
    """
    full, years = _fact_dates(facts)
    for t in context_texts or []:
        f2, y2 = _dates_in_text(t)
        full |= f2
        years |= y2
    for m in _ISO_RE.finditer(answer or ""):
        if m.group(0) not in full:
            return False
    for m in _DMY_RE.finditer(answer or ""):
        if m.group(3) not in years:
            return False
    for m in _YEAR_RE.finditer(answer or ""):
        if m.group(1) not in years:
            return False
    return True


def check_hierarchy_claim(answer: str, facts: list[dict]) -> bool:
    """Фраза иерархии в ответе без PART_OF/MEMBER_OF в фактах → нарушение."""
    if not _HIERARCHY_RE.search(answer or ""):
        return True
    for f in facts or []:
        if isinstance(f, dict) and f.get("relation") in _HIERARCHY_EVIDENCE_RELS:
            return True
    return False


def check_empty_but_confident(facts: list[dict], answer: str) -> bool:
    """Пустые факты + уверенный ответ (без признания тишины) → нарушение."""
    if facts:
        return True
    if _EMPTY_RE.search(answer or ""):
        return True
    return False


def run_layer1(trace_id: str | None, answer: str, facts: list[dict],
               context_texts: list[str] | None = None) -> dict:
    """Все три проверки → Score на трейс. Возвращает {имя: bool}."""
    results = {
        "date_groundedness": check_groundedness_of_dates(
            answer, facts, context_texts),
        "hierarchy_claim_ok": check_hierarchy_claim(answer, facts),
        "empty_but_confident_ok": check_empty_but_confident(facts, answer),
    }
    for name, value in results.items():
        _lf.score(trace_id, name, value, data_type="BOOLEAN")
    bad = [n for n, v in results.items() if not v]
    if bad:
        logger.warning("Слой 1: нарушения %s (trace %s)", bad, trace_id)
    return results
