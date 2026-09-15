"""Cypher-шаблоны для интентов планировщика (граф v2).

Онтология v2: настоящие метки (:Person/:Squad/...) и настоящие типы рёбер
([:MEMBER_OF], [:PART_OF], ...), ветка source_model='llmgraph_gigachat'.
Legacy-стиль (:Entity {type:...} + [:RELATES {type:...}]) больше не используется:
ветка 'gigachat' удалена.
"""

from typing import Optional

MODEL = "llmgraph_gigachat"


def _limit(plan: dict) -> int:
    return int(plan.get("limit") or 20)


def _org_cond(alias: str = "o") -> str:
    """Условие по организации (C4, union-форма).

    Точное совпадение norm_id — первым, CONTAINS — следом. Строгая ветвь
    БЕЗ фолбэка давала тишину, когда org_exact указывал не на тот узел
    (кейс D: org_exact='тесла' = Squad СПрО, а не штаб → 0 фактов при живых
    сидовых данных). Union не молчит никогда.
    """
    return (
        f"($org IS NULL OR "
        f"($org_exact IS NOT NULL AND {alias}.norm_id = $org_exact) "
        f"OR toLower(toString({alias}.name)) CONTAINS toLower($org))"
    )


def _exact_first(alias: str = "o") -> str:
    """Точные совпадения первыми (защита от усечения LIMIT'ом)."""
    return (
        f"CASE WHEN $org_exact IS NOT NULL AND {alias}.norm_id = $org_exact "
        f"THEN 0 ELSE 1 END"
    )


def _params(plan: dict, **extra) -> dict:
    p = {
        "model": MODEL,
        "org": plan.get("org_filter"),
        "org_exact": plan.get("org_exact"),
        "limit": _limit(plan),
    }
    p.update(extra)
    return p


# Новые свойства рёбер v3 (пункт 6): пробрасываем в факты, чтобы отвечающий
# различал дату события и дату упоминания. У старых данных — null, это нормально.
_V3_PROPS = "r.observed_at AS observed_at, r.event_date AS event_date, r.role_status AS role_status"
_V3_LINKS = ("rel: type(r), date: r.date, observed_at: r.observed_at, "
             "event_date: r.event_date, role_status: r.role_status, "
             "source_post_url: r.source_post_url")


def units_query(plan: dict) -> Optional[tuple[str, dict]]:
    if plan.get("intent") != "units":
        return None
    return (
        """
        MATCH (u:Squad {source_model:$model})-[r:PART_OF]->(h)
        WHERE h.source_model = $model
          AND (""" + _org_cond("h") + """)
        RETURN DISTINCT u.name AS unit,
                collect(DISTINCT r.source_post_url) AS sources,
                max(CASE WHEN $org_exact IS NOT NULL AND h.norm_id = $org_exact
                         THEN 0 ELSE 1 END) AS exact_rank
        ORDER BY exact_rank, u.name
        LIMIT $limit
        """,
        _params(plan),
    )


def events_in_period_query(plan: dict) -> Optional[tuple[str, dict]]:
    if plan.get("intent") != "events_in_period":
        return None
    return (
        """
        MATCH (e:Event {source_model:$model})-[r]-(o)
        WHERE (""" + _org_cond("o") + """)
          AND ($pstart IS NULL OR coalesce(r.date,'9999') >= $pstart)
          AND ($pend IS NULL OR coalesce(r.date,'0000') <= $pend)
        RETURN DISTINCT e.name AS event,
                collect(DISTINCT {""" + _V3_LINKS + """, target: o.name}) AS links
        LIMIT $limit
        """,
        _params(
            plan,
            pstart=plan.get("period_start"),
            pend=plan.get("period_end"),
        ),
    )


def commanders_query(plan: dict) -> Optional[tuple[str, dict]]:
    if plan.get("intent") != "commanders":
        return None
    return (
        """
        MATCH (p:Person {source_model:$model})-[r:COMMANDED|HOLDS_ROLE]->(o)
        WHERE (""" + _org_cond("o") + """)
        RETURN p.name AS person, r.role_title AS role_title, r.status AS status,
                type(r) AS relation, r.date AS date, """ + _V3_PROPS + """,
                r.description AS description,
                r.source_post_url AS source_post_url
        ORDER BY """ + _exact_first("o") + """, p.name
        LIMIT $limit
        """,
        _params(plan),
    )


def members_query(plan: dict) -> Optional[tuple[str, dict]]:
    if plan.get("intent") != "members":
        return None
    return (
        """
        MATCH (p:Person {source_model:$model})-[r:MEMBER_OF]->(o)
        WHERE (""" + _org_cond("o") + """)
        RETURN p.name AS person, o.name AS org, type(r) AS relation,
                r.date AS date,
                """ + _V3_PROPS + """,
                r.description AS description, r.source_post_url AS source_post_url
        ORDER BY """ + _exact_first("o") + """, p.name
        LIMIT $limit
        """,
        _params(plan),
    )


def winners_query(plan: dict) -> Optional[tuple[str, dict]]:
    if plan.get("intent") != "winners":
        return None
    # Вторая ветвь UNION: участия в конкурсах, matching org, — не победы,
    # но их посты-источники называют призёров (кейс РКТ: пост 10023).
    # Различение — по колонке relation (WON_AWARD vs PARTICIPATED_IN),
    # правило атрибуции наград — в BASE_PROMPT п.13.
    return (
        """
        MATCH (p:Person {source_model:$model})-[r:WON_AWARD]->(a)
        WHERE ($org IS NULL
               OR ($org_exact IS NOT NULL
                   AND (p.norm_id = $org_exact OR a.norm_id = $org_exact))
               OR toLower(toString(p.name)) CONTAINS toLower($org)
               OR toLower(toString(a.name)) CONTAINS toLower($org))
        RETURN p.name AS person, a.name AS award, type(r) AS relation,
                r.date AS date, r.observed_at AS observed_at,
                r.event_date AS event_date, r.role_status AS role_status,
                r.description AS description, r.source_post_url AS source_post_url
        UNION
        MATCH (s:Entity {source_model:$model})-[r2:PARTICIPATED_IN]->(e:Event)
        WHERE ($org IS NULL
               OR ($org_exact IS NOT NULL
                   AND (s.norm_id = $org_exact OR e.norm_id = $org_exact))
               OR toLower(toString(e.name)) CONTAINS toLower($org))
        RETURN s.name AS person, e.name AS award, type(r2) AS relation,
                r2.date AS date, r2.observed_at AS observed_at,
                r2.event_date AS event_date, r2.role_status AS role_status,
                r2.description AS description, r2.source_post_url AS source_post_url
        LIMIT $limit
        """,
        _params(plan),
    )


def projects_query(plan: dict) -> Optional[tuple[str, dict]]:
    if plan.get("intent") != "projects":
        return None
    return (
        """
        MATCH (pr:Project {source_model:$model})
        WHERE (""" + _org_cond("pr") + """)
        OPTIONAL MATCH (pr)-[r]-(o)
        RETURN pr.name AS project,
                collect(DISTINCT {""" + _V3_LINKS + """, target: o.name}) AS links
        LIMIT $limit
        """,
        _params(plan),
    )


def partners_query(plan: dict) -> Optional[tuple[str, dict]]:
    """Б4: партнёры штаба/отряда (Squad|Organization)-[:SUPPORTED_BY]-(Organization)."""
    if plan.get("intent") != "partners":
        return None
    return (
        """
        MATCH (s:Entity {source_model:$model})-[r:SUPPORTED_BY]-(o:Organization)
        WHERE (s:Squad OR s:Organization) AND o.source_model = $model
          AND (""" + _org_cond("s") + """)
        RETURN DISTINCT s.name AS subject, s.norm_id AS subject_norm,
                o.name AS partner, type(r) AS relation,
                r.date AS date, """ + _V3_PROPS + """,
                r.description AS description,
                r.source_post_url AS source_post_url
        ORDER BY CASE WHEN $org_exact IS NOT NULL AND subject_norm = $org_exact
                      THEN 0 ELSE 1 END, o.name
        LIMIT $limit
        """,
        _params(plan),
    )


def locations_query(plan: dict) -> Optional[tuple[str, dict]]:
    if plan.get("intent") != "locations":
        return None
    return (
        """
        MATCH (l:Location {source_model:$model})
        RETURN l.name AS location
        LIMIT $limit
        """,
        {"model": MODEL, "limit": _limit(plan)},
    )


def entity_detail_query(plan: dict) -> Optional[tuple[str, dict]]:
    if plan.get("intent") != "entity_detail" or not plan.get("target_name"):
        return None
    return (
        """
        MATCH (n:Entity {source_model:$model})
        WHERE toLower(toString(n.name)) CONTAINS toLower($name)
        OPTIONAL MATCH (n)-[r]-(m)
        RETURN n.name AS id, n.type AS type,
                collect(DISTINCT {""" + _V3_LINKS + """, target: m.name}) AS links
        """,
        {"model": MODEL, "name": plan["target_name"]},
    )


def _generic_queries(plan: dict) -> list[tuple[str, dict]]:
    """Фолбэки по entity_type/target_name для неспецифичных планов."""
    etype = plan.get("entity_type")
    tname = plan.get("target_name")
    limit = _limit(plan)
    result = []
    if etype and tname:
        result.append((
            """
            MATCH (n:Entity {source_model:$model, type:$etype})
            WHERE toLower(toString(n.name)) CONTAINS toLower($name)
            OPTIONAL MATCH (n)-[r]-(m)
            RETURN n.name AS id, n.type AS type,
                    collect(DISTINCT {""" + _V3_LINKS + """, target: m.name}) AS links
            LIMIT $limit
            """,
            {"model": MODEL, "etype": etype, "name": tname, "limit": limit},
        ))
    if etype:
        result.append((
            """
            MATCH (n:Entity {source_model:$model, type:$etype})
            RETURN n.name AS id
            LIMIT $limit
            """,
            {"model": MODEL, "etype": etype, "limit": limit},
        ))
    if tname:
        result.append((
            """
            MATCH (n:Entity {source_model:$model})
            WHERE toLower(toString(n.name)) CONTAINS toLower($name)
            OPTIONAL MATCH (n)-[r]-(m)
            RETURN n.name AS id, n.type AS type,
                    collect(DISTINCT {""" + _V3_LINKS + """, target: m.name}) AS links
            LIMIT $limit
            """,
            {"model": MODEL, "name": tname, "limit": limit},
        ))
    return result


_INTENT_HANDLERS = [
    units_query,
    events_in_period_query,
    commanders_query,
    members_query,
    winners_query,
    partners_query,
    projects_query,
    locations_query,
    entity_detail_query,
]


def query_for_plan(plan: dict) -> Optional[tuple[str, dict]]:
    for handler in _INTENT_HANDLERS:
        result = handler(plan)
        if result is not None:
            return result
    generic = _generic_queries(plan)
    return generic[0] if generic else None


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

    Исключаем: саму организацию, её подразделения (o-PART_OF->hq) и её
    вышестоящую структуру (s-PART_OF->o). Отряды штаба — не партнёры.
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
          AND NOT EXISTS { (s)-[:PART_OF]->(o) }
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
