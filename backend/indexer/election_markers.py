"""Детерминированные маркеры событий назначения (Milestone B, пункт 6).

Правило: event_date = post.published_at ТОЛЬКО если в строке с ФИО+ролью
нашлась лемма из ELECTION_LEMMAS; иначе event_date = null.
Не просим у LLM то, что дешевле проверить кодом.

Окно — строка поста (VK-посты пишутся строками: "На должность командира
встал: - Марсель Фарвазов"), не точная фраза и не весь пост целиком.
Проверка на уровне строки: лемматизация pymorphy3 + пересечение множеств.
"""

from __future__ import annotations

import logging
import re

logger = logging.getLogger("indexer")

_TOKEN_RE = re.compile(r"[а-яёa-z0-9]+", re.IGNORECASE)
_LINE_SPLIT_RE = re.compile(r"[\r\n]+|[.!?…]+")

# Калибруется скриптом по корпусу (пересечение ФИО + ролевое существительное).
# "выбор" (ед.ч., "сделал выбор") намеренно исключён — не про должности.
ELECTION_LEMMAS: frozenset[str] = frozenset(
    {
        "выборы",
        "перевыборы",
        "избрать",
        "переизбрать",
        "назначить",
        "утвердить",
        "сложить",
        "встать",
    }
)

# Связи, для которых вообще имеет смысл искать событие назначения.
ROLE_RELATIONS: frozenset[str] = frozenset({"COMMANDED", "HOLDS_ROLE"})


def is_role_relation(relation: str, role_title: str | None = None) -> bool:
    """Ролевой ли факт (должность/командование)."""
    return relation in ROLE_RELATIONS or bool((role_title or "").strip())


_morph = None


def _get_morph():
    global _morph
    if _morph is None:
        import pymorphy3

        _morph = pymorphy3.MorphAnalyzer()
    return _morph


def lemmas_of(text: str) -> set[str]:
    """Множество лемм текста (нижний регистр)."""
    morph = _get_morph()
    out = set()
    for tok in _TOKEN_RE.findall(text or ""):
        try:
            out.add(morph.parse(tok.lower())[0].normal_form)
        except Exception:
            out.add(tok.lower())
    return out


def has_election_marker(sentence: str) -> bool:
    """Есть ли в строке маркер выборов/назначения."""
    return bool(lemmas_of(sentence) & ELECTION_LEMMAS)


def _person_tokens(person_name: str) -> list[str]:
    from backend.common.canon import normalize_id

    return [t for t in normalize_id(person_name).split() if len(t) >= 3]


def find_election_line(post_text: str, person_name: str) -> str | None:
    """Строка поста, где рядом ФИО и маркер выборов. Иначе None.

    Возвращаем строку для логов — видно, по какому основанию
    проставлен event_date.
    """
    tokens = _person_tokens(person_name)
    if not tokens or not post_text:
        return None
    for raw_line in _LINE_SPLIT_RE.split(post_text):
        line = raw_line.strip()
        if not line:
            continue
        low = line.lower()
        if any(t in low for t in tokens) and has_election_marker(line):
            return line
    return None


def compute_event_date(
    post_text: str | None, person_name: str, post_date: str | None
) -> str | None:
    """Дата события назначения или None (честный null вместо даты поста)."""
    if not post_date or not post_text:
        return None
    line = find_election_line(post_text, person_name)
    if line is None:
        return None
    logger.debug("Election marker for %r: %r", person_name, line[:120])
    return post_date
