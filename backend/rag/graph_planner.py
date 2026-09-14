"""Планировщик структурных графовых запросов (STRUCT)."""

from backend.graph.graph_builder import GraphBuilder
from backend.rag.planner_prompts import PLANNER_PROMPT, PLANNER_SCHEMA
from backend.rag.planner_queries import query_for_plan
from backend.utils.gigachat_client import GigaChatClient
from backend.utils.logger import setup_logger

logger = setup_logger("graph_planner")

_DEFAULTS = {
    "entity_type": None,
    "target_name": None,
    "period_start": None,
    "period_end": None,
    "org_filter": None,
    "relation": None,
    "limit": 20,
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
            return {"intent": "general", **_DEFAULTS}
        for k, v in _DEFAULTS.items():
            data.setdefault(k, v)
        return data

    def resolve_org_exact(self, org_filter: str | None) -> str | None:
        """Точная резолюция организации через canon (C4).

        Возвращает norm_id существующего узла или None (тогда запросы
        используют legacy CONTAINS-фолбэк). Никакого молчаливого склеивания.
        """
        if not org_filter:
            return None
        from backend.common.canon import normalize_id
        from backend.rag.planner_queries import MODEL

        norm = normalize_id(org_filter)
        if not norm:
            return None
        graph = self._get_graph()
        if graph is None:
            return None
        try:
            rows = graph.search_cypher(
                "MATCH (o:Entity {source_model:$m}) WHERE o.norm_id = $n "
                "RETURN o.norm_id AS n LIMIT 1",
                {"m": MODEL, "n": norm},
            )
        except Exception as e:
            logger.warning("org resolve failed: %s", e)
            return None
        return rows[0]["n"] if rows else None

    def execute(self, plan: dict) -> tuple[list[dict], dict]:
        """Выполнение плана. Возвращает (строки, debug).

        debug = {"cypher": str|None, "params": dict} — для панели «Рентген»:
        видно, какой запрос к графу построил планировщик.
        """
        graph = self._get_graph()
        if graph is None:
            return [], {"cypher": None, "params": {}}

        candidate = query_for_plan(plan)
        if candidate is None:
            return [], {"cypher": None, "params": {}}
        query, params = candidate
        try:
            return graph.search_cypher(query, params), {"cypher": query, "params": params}
        except Exception as e:
            logger.warning("Graph planner query failed: %s", e)
            return [], {"cypher": query, "params": params}

    def close(self):
        if self._graph is not None:
            self._graph.close()
            self._graph = None
