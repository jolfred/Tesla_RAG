"""Планировщик структурных графовых запросов (STRUCT)."""

from backend.graph.graph_builder import GraphBuilder
from backend.utils.gigachat_client import GigaChatClient
from backend.utils.logger import setup_logger

logger = setup_logger("graph_planner")

PLANNER_PROMPT = """Ты — планировщик запросов к графу знаний о студенческих отрядах КГЭУ «Тесла».
Определи по вопросу пользователя параметры запроса. Доступные типы сущностей (nodes): Person, Organization, Role, Award, Event, Project, Location, Profession.
Типы связей (edges): HOLDS_ROLE, WON_AWARD, MEMBER_OF, PARTICIPATED_IN, ORGANIZED, PART_OF, LOCATED_IN, HELD_AT, TRAINED_IN, SUPPORTED_BY.

Ответь строго JSON:
{
  "intent": "units | events_in_period | commanders | members | winners | projects | locations | entity_detail | general",
  "entity_type": null,
  "target_name": null,
  "period_start": "YYYY-MM-DD | null",
  "period_end": "YYYY-MM-DD | null",
  "org_filter": null,
  "relation": null,
  "limit": 20
}

Правила:
- "units": вопрос о списке отрядов/подразделений, входящих в штаб или организацию (напр. "перечисли все отряды штаба", "какие отряды входят в штаб"). org_filter задавайте по штабу.
- "events_in_period": вопрос о мероприятиях/событиях (в т.ч. с датой/периодом).
- "commanders": вопрос о командирах/комиссарах/руководителях/ролях/контактах/составе штаба или отряда (напр. "кто командир", "какие контакты", "перечисли комсостав"). org_filter задавайте по названию штаба/отряда.
- "members": вопрос об участниках/членах отрядов.
- "winners": вопрос о победителях/наградах.
- "projects": вопрос о проектах/трудовых семестрах.
- "locations": вопрос о местах/локациях.
- "entity_detail": вопрос о конкретной сущности (target_name задан) и НЕ о командирах/контактах/составе.
- "general": всё остальное — вернуть 0,0 в period если период не указан.
- org_filter: "Тесла" если вопрос о штабе/отрядах Тесла, иначе null.
- period_start/period_end только если вопрос явно указывает период (например "с начала 2026" -> "2026-01-01").
- limit: число результатов (обычно 20, для "назови всех" — 100)."""

PLANNER_SCHEMA = {
    "type": "object",
    "properties": {
        "intent": {"type": "string"},
        "entity_type": {"type": ["string", "null"]},
        "target_name": {"type": ["string", "null"]},
        "period_start": {"type": ["string", "null"]},
        "period_end": {"type": ["string", "null"]},
        "org_filter": {"type": ["string", "null"]},
        "relation": {"type": ["string", "null"]},
        "limit": {"type": "integer"},
    },
    "required": [
        "intent", "entity_type", "target_name",
        "period_start", "period_end", "org_filter", "relation", "limit",
    ],
}


class GraphPlanner:
    def __init__(self):
        self._llm = None
        self._graph = None

    def _get_llm(self) -> GigaChatClient:
        if self._llm is None:
            self._llm = GigaChatClient()
        return self._llm

    def _get_graph(self) -> GraphBuilder | None:
        if self._graph is None:
            try:
                self._graph = GraphBuilder()
            except Exception as e:
                logger.warning("GraphBuilder init failed: %s", e)
                self._graph = None
        return self._graph

    def plan(self, question: str) -> dict:
        llm = self._get_llm()
        try:
            data = llm.extract_json(PLANNER_PROMPT, question, schema=PLANNER_SCHEMA)
        except Exception as e:
            logger.warning("Planner LLM failed: %s", e)
            return {"intent": "general", "limit": 20}
        defaults = {
            "entity_type": None,
            "target_name": None,
            "period_start": None,
            "period_end": None,
            "org_filter": None,
            "relation": None,
            "limit": 20,
        }
        for k, v in defaults.items():
            data.setdefault(k, v)
        return data

    def execute(self, plan: dict) -> list[dict]:
        graph = self._get_graph()
        if graph is None:
            return []

        intent = plan.get("intent", "general")
        etype = plan.get("entity_type")
        tname = plan.get("target_name")
        pstart = plan.get("period_start")
        pend = plan.get("period_end")
        org = plan.get("org_filter")
        rel = plan.get("relation")
        limit = int(plan.get("limit") or 20)

        try:
            if intent == "units":
                return graph.search_cypher(
                    """
                    MATCH (h:Entity {type:"Organization"})-[r:RELATES {type:"PART_OF"}]->(u:Entity {type:"Organization"})
                    WHERE ($org IS NULL OR toLower(toString(h.id)) CONTAINS toLower($org))
                      AND u.org_type = 'lso'
                    RETURN DISTINCT u.id AS unit, u.org_type AS org_type, u.group_domain AS group_domain,
                           collect(DISTINCT r.source_post_url) AS sources
                    ORDER BY u.id
                    LIMIT $limit
                    """,
                    {"org": org, "limit": limit},
                )

            if intent == "events_in_period":
                return graph.search_cypher(
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
                    {"org": org, "pstart": pstart, "pend": pend, "limit": limit},
                )

            if intent == "commanders":
                return graph.search_cypher(
                    """
                    MATCH (p:Entity)-[r:RELATES {type:"HOLDS_ROLE"}]->(o:Entity)
                    WHERE ($org IS NULL OR toLower(toString(o.id)) CONTAINS toLower($org))
                    RETURN p.id AS person, r.role_title AS role_title, r.status AS status,
                           r.date AS date, r.description AS description, r.source_post_url AS source_post_url
                    ORDER BY r.status = 'active' DESC, p.id
                    LIMIT $limit
                    """,
                    {"org": org, "limit": limit},
                )

            if intent == "members":
                return graph.search_cypher(
                    """
                    MATCH (p:Entity)-[r:RELATES {type:"MEMBER_OF"}]->(o:Entity)
                    WHERE ($org IS NULL OR toLower(toString(o.id)) CONTAINS toLower($org))
                    RETURN p.id AS person, o.id AS org, r.date AS date,
                           r.description AS description, r.source_post_url AS source_post_url
                    LIMIT $limit
                    """,
                    {"org": org, "limit": limit},
                )

            if intent == "winners":
                return graph.search_cypher(
                    """
                    MATCH (p:Entity)-[r:RELATES {type:"WON_AWARD"}]->(a:Entity)
                    WHERE ($org IS NULL OR toLower(toString(p.id)) CONTAINS toLower($org)
                           OR toLower(toString(a.id)) CONTAINS toLower($org))
                    RETURN p.id AS person, a.id AS award, r.date AS date,
                           r.description AS description, r.source_post_url AS source_post_url
                    LIMIT $limit
                    """,
                    {"org": org, "limit": limit},
                )

            if intent == "projects":
                return graph.search_cypher(
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
                    {"org": org, "limit": limit},
                )

            if intent == "locations":
                return graph.search_cypher(
                    """
                    MATCH (l:Entity {type:"Location"})
                    RETURN l.id AS location, l.description AS description
                    LIMIT $limit
                    """,
                    {"limit": limit},
                )

            if intent == "entity_detail" and tname:
                return graph.search_cypher(
                    """
                    MATCH (n:Entity {id:$name})
                    OPTIONAL MATCH (n)-[r]-(m)
                    RETURN n.id AS id, n.type AS type, n.description AS description,
                           collect(DISTINCT {rel: coalesce(r.type,''), target: m.id,
                                              date: r.date, source_post_url: r.source_post_url}) AS links
                    """,
                    {"name": tname},
                )

            if etype and tname:
                return graph.search_cypher(
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
                )

            if etype:
                return graph.search_cypher(
                    """
                    MATCH (n:Entity {type:$etype})
                    RETURN n.id AS id, n.description AS description
                    LIMIT $limit
                    """,
                    {"etype": etype, "limit": limit},
                )

            if tname:
                return graph.search_cypher(
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
                )

        except Exception as e:
            logger.warning("Graph planner query failed: %s", e)

        return []

    def close(self):
        if self._graph is not None:
            self._graph.close()
            self._graph = None