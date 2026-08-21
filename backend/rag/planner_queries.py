"""Cypher-шаблоны для интентов планировщика.

Каждая функция принимает план (dict) и возвращает (query, params) либо None
(тогда выполняется следующий кандидат / generic-фолбэк).
"""

from typing import Optional


def _limit(plan: dict) -> int:
    return int(plan.get("limit") or 20)


def units_query(plan: dict) -> Optional[tuple[str, dict]]:
    if plan.get("intent") != "units":
        return None
    return (
        """
        MATCH (h:Entity {type:"Organization"})-[r:RELATES {type:"PART_OF"}]->(u:Entity {type:"Organization"})
        WHERE ($org IS NULL OR toLower(toString(h.id)) CONTAINS toLower($org))
          AND u.org_type = 'lso'
        RETURN DISTINCT u.id AS unit, u.org_type AS org_type, u.group_domain AS group_domain,
               collect(DISTINCT r.source_post_url) AS sources
        ORDER BY u.id
        LIMIT $limit
        """,
        {"org": plan.get("org_filter"), "limit": _limit(plan)},
    )


def events_in_period_query(plan: dict) -> Optional[tuple[str, dict]]:
    if plan.get("intent") != "events_in_period":
        return None
    return (
        """
        MATCH (e:Entity {type:"Event"})-[r:RELATES]-(o:Entity)
        WHERE ($org IS NULL OR toLower(toString(o.id)) CONTAINS toLower($org))
          AND ($pstart IS NULL OR coalesce(r.date,'9999') >= $pstart)
          AND ($pend IS NULL OR coalesce(r.date,'0000') <= $pend)
        RETURN DISTINCT e.id AS event, e.description AS description,
               collect(DISTINCT {rel: coalesce(r.type,''), date: r.date,
                                  source_post_url: r.source_post_url}) AS links
        LIMIT $limit
        """,
        {
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
        MATCH (p:Entity)-[r:RELATES {type:"HOLDS_ROLE"}]->(o:Entity)
        WHERE ($org IS NULL OR toLower(toString(o.id)) CONTAINS toLower($org))
        RETURN p.id AS person, r.role_title AS role_title, r.status AS status,
               r.date AS date, r.description AS description, r.source_post_url AS source_post_url
        ORDER BY r.status = 'active' DESC, p.id
        LIMIT $limit
        """,
        {"org": plan.get("org_filter"), "limit": _limit(plan)},
    )


def members_query(plan: dict) -> Optional[tuple[str, dict]]:
    if plan.get("intent") != "members":
        return None
    return (
        """
        MATCH (p:Entity)-[r:RELATES {type:"MEMBER_OF"}]->(o:Entity)
        WHERE ($org IS NULL OR toLower(toString(o.id)) CONTAINS toLower($org))
        RETURN p.id AS person, o.id AS org, r.date AS date,
               r.description AS description, r.source_post_url AS source_post_url
        LIMIT $limit
        """,
        {"org": plan.get("org_filter"), "limit": _limit(plan)},
    )


def winners_query(plan: dict) -> Optional[tuple[str, dict]]:
    if plan.get("intent") != "winners":
        return None
    return (
        """
        MATCH (p:Entity)-[r:RELATES {type:"WON_AWARD"}]->(a:Entity)
        WHERE ($org IS NULL OR toLower(toString(p.id)) CONTAINS toLower($org)
               OR toLower(toString(a.id)) CONTAINS toLower($org))
        RETURN p.id AS person, a.id AS award, r.date AS date,
               r.description AS description, r.source_post_url AS source_post_url
        LIMIT $limit
        """,
        {"org": plan.get("org_filter"), "limit": _limit(plan)},
    )


def projects_query(plan: dict) -> Optional[tuple[str, dict]]:
    if plan.get("intent") != "projects":
        return None
    return (
        """
        MATCH (pr:Entity {type:"Project"})
        WHERE ($org IS NULL OR toLower(toString(pr.id)) CONTAINS toLower($org)
               OR toLower(toString(pr.description)) CONTAINS toLower($org))
        OPTIONAL MATCH (pr)-[r:RELATES]-(o:Entity)
        RETURN pr.id AS project, pr.description AS description,
               collect(DISTINCT {rel: coalesce(r.type,''), target: o.id,
                                  date: r.date}) AS links
        LIMIT $limit
        """,
        {"org": plan.get("org_filter"), "limit": _limit(plan)},
    )


def locations_query(plan: dict) -> Optional[tuple[str, dict]]:
    if plan.get("intent") != "locations":
        return None
    return (
        """
        MATCH (l:Entity {type:"Location"})
        RETURN l.id AS location, l.description AS description
        LIMIT $limit
        """,
        {"limit": _limit(plan)},
    )


def entity_detail_query(plan: dict) -> Optional[tuple[str, dict]]:
    if plan.get("intent") != "entity_detail" or not plan.get("target_name"):
        return None
    return (
        """
        MATCH (n:Entity {id:$name})
        OPTIONAL MATCH (n)-[r]-(m)
        RETURN n.id AS id, n.type AS type, n.description AS description,
               collect(DISTINCT {rel: coalesce(r.type,''), target: m.id,
                                  date: r.date, source_post_url: r.source_post_url}) AS links
        """,
        {"name": plan["target_name"]},
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
            MATCH (n:Entity {type:$etype})
            WHERE toLower(toString(n.id)) CONTAINS toLower($name)
            OPTIONAL MATCH (n)-[r]-(m)
            RETURN n.id AS id, n.type AS type, n.description AS description,
                   collect(DISTINCT {rel: coalesce(r.type,''), target: m.id,
                                      date: r.date}) AS links
            LIMIT $limit
            """,
            {"etype": etype, "name": tname, "limit": limit},
        ))
    if etype:
        result.append((
            """
            MATCH (n:Entity {type:$etype})
            RETURN n.id AS id, n.description AS description
            LIMIT $limit
            """,
            {"etype": etype, "limit": limit},
        ))
    if tname:
        result.append((
            """
            MATCH (n:Entity)
            WHERE toLower(toString(n.id)) CONTAINS toLower($name)
            OPTIONAL MATCH (n)-[r]-(m)
            RETURN n.id AS id, n.type AS type, n.description AS description,
                   collect(DISTINCT {rel: coalesce(r.type,''), target: m.id,
                                      date: r.date}) AS links
            LIMIT $limit
            """,
            {"name": tname, "limit": limit},
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
