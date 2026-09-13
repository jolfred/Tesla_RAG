"""Один способ узнавать "кто есть кто" (Milestone A, пункт 2).

Бинарное разрешение персон: либо точно совпало -> merge в существующий узел,
либо создаём новый узел + ребро POSSIBLE_DUPLICATE на каждого кандидата
("пометить уточнить"). Промежуточного "непонятно, но сольём" нет.

`person_key` — это blocking-ключ (группирует кандидатов), НЕ ключ для слияния.
Решение о слиянии принимает `resolve_person` по строковому равенству
или пересечению орг-контекста.

`backend/indexer/normalize.py` — тонкий шим для обратной совместимости.
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field

from backend.common.ontology import SOURCE_MODEL_V2

_QUOTES_RE = re.compile(r'[«»"„“”\']')
_WS_RE = re.compile(r"\s+")
_DIGITS_WS_RE = re.compile(r"(?<=\d)\s+(?=\d)")
_EX_PREFIX_RE = re.compile(r"^(экс|ex)[\s\-–—]+", re.IGNORECASE)

# Известные синонимы уже на нормализованной форме.
SYNONYMS: dict[str, str] = {
    "рт": "татарстан",
    "республика татарстан": "татарстан",
    "фгбоу во кгэу": "кгэу",
    "казанский государственный энергетический университет": "кгэу",
    "штаб студенческих отрядов тесла": "штаб со кгэу тесла",
    "штаб студенческих отрядов кгэу тесла": "штаб со кгэу тесла",
    "студенческие отряды кгэу тесла": "штаб со кгэу тесла",
    "студенческие отряды тесла": "штаб со кгэу тесла",
    "кгэу тесла": "штаб со кгэу тесла",
    "штаба студенческих отрядов тесла": "штаб со кгэу тесла",
    "штаба со кгэу тесла": "штаб со кгэу тесла",
    "снежный десант рсо": "снежный десант",
    "всероссийская патриотическая акция снежный десант": "снежный десант",
}

# Ролевые слова: отрезаются от person_key (должность — не часть имени)
# и используются parse_ex_person для role_hint. Калибруется по корпусу.
ROLE_WORDS: frozenset[str] = frozenset(
    {
        "командир",
        "комиссар",
        "мастер",
        "методист",
        "медик",
        "боец",
        "кандидат",
        "куратор",
        "руководитель",
        "наставник",
        "пресс-секретарь",
        "пресссекретарь",
    }
)


def yo_normalize(text: str) -> str:
    """Строчные + ё→е. База для всех строковых сравнений имён."""
    return (text or "").strip().lower().replace("ё", "е")


def normalize_id(raw: str) -> str:
    """Канонический ключ сущности для MERGE (не-персоны и общий случай)."""
    s = yo_normalize(raw)
    # VK-имена групп вида 'Название | Квалификатор' -> только название.
    s = s.split("|")[0].strip()
    s = _QUOTES_RE.sub("", s)
    s = _DIGITS_WS_RE.sub("", s)  # '775 000 рублей' -> '775000 рублей'
    s = _WS_RE.sub(" ", s).strip()
    return SYNONYMS.get(s, s)


def merge_key(source_model: str, norm_id: str) -> str:
    return f"{source_model}::{norm_id}"


def parse_ex_person(raw: str) -> tuple[str, str | None, bool]:
    """Разбор "экс-<роль> <ФИО>".

    Возвращает (имя, role_hint, is_former). Без экс-префикса —
    (имя_как_есть, None, False). Префикс относится к РОЛИ, не к имени:
    узел персоны всегда создаётся без "экс-", бывшесть — свойство ребра
    (role_status=former, Milestone B).
    """
    s = (raw or "").strip()
    m = _EX_PREFIX_RE.match(s)
    if not m:
        return s, None, False
    rest = s[m.end():].strip()
    tokens = rest.split()
    role_hint = None
    if tokens and yo_normalize(tokens[0]) in ROLE_WORDS:
        role_hint = tokens[0]
        rest = " ".join(tokens[1:]).strip()
    return rest, role_hint, True


def person_key(name: str) -> tuple[str, ...]:
    """Blocking-ключ персоны: отсортированные токены имени.

    "Хазиев Артем" и "Артём Хазиев" -> одинаковый ключ.
    Экс-префикс и ролевые слова в ключ не входят.
    """
    clean, _, _ = parse_ex_person(name)
    tokens = normalize_id(clean).split()
    tokens = [t for t in tokens if t not in ROLE_WORDS or len(tokens) == 1]
    # Ведущие ролевые слова ("командир Иван Петров") отрезаем всегда,
    # одиночное ролевое слово ("Комиссар" как имя узла) оставляем.
    while len(tokens) > 1 and tokens[0] in ROLE_WORDS:
        tokens.pop(0)
    return tuple(sorted(tokens))


@dataclass
class PersonResolution:
    """Исход бинарного разрешения. Ровно два исхода, без "unverified"."""

    action: str  # "merge" | "create"
    person_key: tuple[str, ...]
    name: str
    is_former: bool = False
    role_hint: str | None = None
    target_id: str | None = None  # merge_key существующего узла (action=merge)
    # merge_key кандидатов для POSSIBLE_DUPLICATE (action=create, непустой
    # только при неоднозначности — "пометить уточнить").
    possible_duplicates: list[str] = field(default_factory=list)


def _same_person_string(name_a: str, name_b: str) -> bool:
    """Строковое равенство modulo ё/регистр/кавычки/экс-префикс."""
    a, _, _ = parse_ex_person(name_a)
    b, _, _ = parse_ex_person(name_b)
    return normalize_id(a) == normalize_id(b) and bool(normalize_id(a))


def resolve_person(
    name: str,
    post_orgs: set[str],
    session,
    source_model: str = SOURCE_MODEL_V2,
) -> PersonResolution:
    """Бинарное разрешение персоны по blocking-ключу + верификация контекстом.

    post_orgs — norm_id организаций поста: группа поста + Squad/Organization,
    извлечённые в ЭТОМ ЖЕ посте. Пустое множество = контекста нет.
    session — neo4j-сессия (или mock с .run() в тестах).
    """
    clean, role_hint, is_former = parse_ex_person(name)
    key = person_key(name)
    rows = session.run(
        "MATCH (p:Person {person_key: $key, source_model: $model}) "
        "OPTIONAL MATCH (p)-[:MEMBER_OF|HOLDS_ROLE|COMMANDED]->(o) "
        "RETURN p.merge_key AS id, p.name AS name, "
        "collect(DISTINCT o.norm_id) AS orgs",
        key=list(key),
        model=source_model,
    ).data()
    candidates = [dict(r) for r in rows if r.get("id")]

    if not candidates:
        return PersonResolution(
            action="create",
            person_key=key,
            name=clean,
            is_former=is_former,
            role_hint=role_hint,
        )

    if len(candidates) == 1:
        cand = candidates[0]
        cand_orgs = set(cand.get("orgs") or []) - {None, ""}
        if _same_person_string(clean, cand.get("name") or "") or (
            post_orgs and cand_orgs & post_orgs
        ):
            return PersonResolution(
                action="merge",
                person_key=key,
                name=clean,
                is_former=is_former,
                role_hint=role_hint,
                target_id=cand["id"],
            )

    # Всё остальное — новый узел + пометка "уточнить" на каждого кандидата.
    return PersonResolution(
        action="create",
        person_key=key,
        name=clean,
        is_former=is_former,
        role_hint=role_hint,
        possible_duplicates=[c["id"] for c in candidates],
    )
