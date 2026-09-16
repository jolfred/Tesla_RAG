"""Строгие Cypher-шаблоны для интентов планировщика (граф v2).

Онтология v2: настоящие метки (:Person/:Squad/...) и настоящие типы рёбер
([:MEMBER_OF], [:PART_OF], ...), ветка source_model='llmgraph_gigachat'.
Равенство norm_id, без CONTAINS-фолбэка. Legacy-шаблоны (CONTAINS) —
в planner_queries_legacy.py, используются только как запасной путь.
"""

from typing import Optional

from backend.rag.planner_common import (
    MODEL,
    _V3_LINKS,
    _V3_PROPS,
    _limit,
    _params,
)
from backend.rag.planner_queries_legacy import query_for_plan





# --- Строгие запросы v2 (Фаза 2): равенство norm_id, без CONTAINS-фолбэка ---
# Утечка ПрогрессLAB шла через CONTAINS по имени («Тесла» содержится и в
# "Проектный центр Штаба СО «Тесла»"). После честной резолюции (norm_id
# существующего узла) строгого равенства достаточно; молчаливый фолбэк
# запрещён — без org_norm_id запрос не строим (None = сигнал на fallback).


def commanders_query_strict(plan: dict) -> Optional[tuple[str, dict]]:
    if plan.get("intent") != "commanders":
        return None
    org_norm_id = plan.get("org_norm_id")
    if not org_norm_id:
        return None
    return (
        """
        MATCH (p:Person {source_model:$model})-[r:COMMANDED|HOLDS_ROLE]->(o)
        WHERE o.source_model = $model AND o.norm_id = $org_norm_id
        RETURN p.name AS person, r.role_title AS role_title, r.status AS status,
                type(r) AS relation, r.date AS date, """ + _V3_PROPS + """,
                r.description AS description,
                r.source_post_url AS source_post_url
        ORDER BY p.name
        LIMIT $limit
        """,
        {"model": MODEL, "org_norm_id": org_norm_id, "limit": _limit(plan)},
    )


def units_query_strict(plan: dict) -> Optional[tuple[str, dict]]:
    if plan.get("intent") != "units":
        return None
    org_norm_id = plan.get("org_norm_id")
    if not org_norm_id:
        return None
    return (
        """
        MATCH (u:Squad {source_model:$model})-[r:PART_OF]->(h)
        WHERE h.source_model = $model AND h.norm_id = $org_norm_id
        RETURN DISTINCT u.name AS unit,
                collect(DISTINCT r.source_post_url) AS sources
        ORDER BY u.name
        LIMIT $limit
        """,
        {"model": MODEL, "org_norm_id": org_norm_id, "limit": _limit(plan)},
    )


def query_for_plan_v2(plan: dict) -> Optional[tuple[str, dict]]:
    """Диспетчер v2: строгие запросы для commanders/units/partners, остальное —
    legacy-хендлеры с org_exact=org_norm_id (exact-first, без правок)."""
    plan = dict(plan)
    if plan.get("org_norm_id") and not plan.get("org_exact"):
        plan["org_exact"] = plan["org_norm_id"]
    for strict in (commanders_query_strict, units_query_strict,
                   partners_query_strict):
        result = strict(plan)
        if result is not None:
            return result
    return query_for_plan(plan)


def partners_query_strict(plan: dict) -> Optional[tuple[str, dict]]:
    """Строгие партнёры (п.4 отзыва): направленный запрос от самой организации,
    внутренние пары вырезаны кодом, а не надеждой.

    Исключаем: саму организацию и её подразделения (o-PART_OF->hq).
    Вышестоящие структуры (КГЭУ, РСО) НЕ исключаем — университет как
    работодатель и есть целевой партнёр (п.4 отзыва).
    Двунаправленные дубли (штаб<->ПрогрессLAB) исчезают сами: субъект
    зафиксирован строго, обратные рёбра не матчатся.
    """
    if plan.get("intent") != "partners":
        return None
    org_norm_id = plan.get("org_norm_id")
    if not org_norm_id:
        return None
    return (
        """
        MATCH (s)-[r:SUPPORTED_BY]->(o)
        WHERE s.source_model = $model AND o.source_model = $model
          AND s.norm_id = $org_norm_id
          AND o.norm_id <> $org_norm_id
          AND NOT EXISTS {
            (o)-[:PART_OF]->(h)
            WHERE h.source_model = $model AND h.norm_id = $org_norm_id
          }
        RETURN DISTINCT s.name AS subject, o.name AS partner,
                r.date AS date, """ + _V3_PROPS + """,
                r.description AS description,
                r.source_post_url AS source_post_url
        ORDER BY o.name
        LIMIT $limit
        """,
        {"model": MODEL, "org_norm_id": org_norm_id, "limit": _limit(plan)},
    )


def person_roles_query(target_name: str) -> Optional[tuple[str, dict]]:
    """Роли конкретной персоны (Фаза 5, read-only lookup).

    CONTAINS здесь допустим: ищется явно названная сущность, а не
    склейка организации. Возвращает и o.name AS org — рендеру персон
    нужна организация каждой роли.
    """
    if not target_name:
        return None
    return (
        """
        MATCH (p:Person {source_model:$model})-[r:COMMANDED|HOLDS_ROLE|MEMBER_OF]->(o)
        WHERE o.source_model = $model
          AND toLower(toString(p.name)) CONTAINS toLower($name)
        RETURN p.name AS person, o.name AS org, r.role_title AS role_title,
                type(r) AS relation, r.date AS date, """ + _V3_PROPS + """,
                r.description AS description,
                r.source_post_url AS source_post_url
        ORDER BY o.name
        LIMIT 50
        """,
        {"model": MODEL, "name": target_name},
    )
