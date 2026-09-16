"""Legacy Cypher-шаблоны (CONTAINS-фолбэк по имени).

Используются только как запасной путь внутри query_for_plan_v2:
строгая ветвь молчит без org_norm_id. Отдельным файлом, чтобы не
смешиваться со строгими запросами.
"""

from typing import Optional

from backend.rag.planner_common import (
    MODEL,
    _V3_LINKS,
    _V3_PROPS,
    _exact_first,
    _limit,
    _org_cond,
    _params,
)


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
