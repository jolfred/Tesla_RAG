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


def units_query(plan: dict) -> Optional[tuple[str, dict]]:
    if plan.get("intent") != "units":
        return None
    return (
        """
        MATCH (u:Squad {source_model:$model})-[r:PART_OF]->(h)
        WHERE h.source_model = $model
          AND ($org IS NULL OR toLower(toString(h.name)) CONTAINS toLower($org))
        RETURN DISTINCT u.name AS unit,
               collect(DISTINCT r.source_post_url) AS sources
        ORDER BY u.name
        LIMIT $limit
        """,
        {"model": MODEL, "org": plan.get("org_filter"), "limit": _limit(plan)},
    )


def events_in_period_query(plan: dict) -> Optional[tuple[str, dict]]:
    if plan.get("intent") != "events_in_period":
        return None
    return (
        """
        MATCH (e:Event {source_model:$model})-[r]-(o)
        WHERE ($org IS NULL OR toLower(toString(o.name)) CONTAINS toLower($org))
          AND ($pstart IS NULL OR coalesce(r.date,'9999') >= $pstart)
          AND ($pend IS NULL OR coalesce(r.date,'0000') <= $pend)
        RETURN DISTINCT e.name AS event,
               collect(DISTINCT {rel: type(r), date: r.date,
                                  source_post_url: r.source_post_url}) AS links
        LIMIT $limit
        """,
        {
            "model": MODEL,
            "org": plan.get("org_filter"),
            "pstart": plan.get("period_start"),
            "pend": plan.get("period_end"),
            "limit": _limit(plan),
        },
    )


def commanders_query(plan: dict) -> Optional[tuple[str, dict]]:
    if plan.get("intent") != "commanders":
        return None
    return (
        """
        MATCH (p:Person {source_model:$model})-[r:COMMANDED|HOLDS_ROLE]->(o)
        WHERE ($org IS NULL OR toLower(toString(o.name)) CONTAINS toLower($org))
        RETURN p.name AS person, r.role_title AS role_title, r.status AS status,
               r.date AS date, r.description AS description,
               r.source_post_url AS source_post_url
        ORDER BY p.name
        LIMIT $limit
        """,
        {"model": MODEL, "org": plan.get("org_filter"), "limit": _limit(plan)},
    )


def members_query(plan: dict) -> Optional[tuple[str, dict]]:
    if plan.get("intent") != "members":
        return None
    return (
        """
        MATCH (p:Person {source_model:$model})-[r:MEMBER_OF]->(o)
        WHERE ($org IS NULL OR toLower(toString(o.name)) CONTAINS toLower($org))
        RETURN p.name AS person, o.name AS org, r.date AS date,
               r.description AS description, r.source_post_url AS source_post_url
        LIMIT $limit
        """,
        {"model": MODEL, "org": plan.get("org_filter"), "limit": _limit(plan)},
    )


def winners_query(plan: dict) -> Optional[tuple[str, dict]]:
    if plan.get("intent") != "winners":
        return None
    return (
        """
        MATCH (p:Person {source_model:$model})-[r:WON_AWARD]->(a)
        WHERE ($org IS NULL OR toLower(toString(p.name)) CONTAINS toLower($org)
               OR toLower(toString(a.name)) CONTAINS toLower($org))
        RETURN p.name AS person, a.name AS award, r.date AS date,
               r.description AS description, r.source_post_url AS source_post_url
        LIMIT $limit
        """,
        {"model": MODEL, "org": plan.get("org_filter"), "limit": _limit(plan)},
    )


def projects_query(plan: dict) -> Optional[tuple[str, dict]]:
    if plan.get("intent") != "projects":
        return None
    return (
        """
        MATCH (pr:Project {source_model:$model})
        WHERE ($org IS NULL OR toLower(toString(pr.name)) CONTAINS toLower($org))
        OPTIONAL MATCH (pr)-[r]-(o)
        RETURN pr.name AS project,
               collect(DISTINCT {rel: type(r), target: o.name,
                                  date: r.date,
                                  source_post_url: r.source_post_url}) AS links
        LIMIT $limit
        """,
        {"model": MODEL, "org": plan.get("org_filter"), "limit": _limit(plan)},
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
               collect(DISTINCT {rel: type(r), target: m.name,
                                  date: r.date,
                                  source_post_url: r.source_post_url}) AS links
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
                   collect(DISTINCT {rel: type(r), target: m.name,
                                      date: r.date}) AS links
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
                   collect(DISTINCT {rel: type(r), target: m.name,
                                      date: r.date}) AS links
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
