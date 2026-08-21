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

    def execute(self, plan: dict) -> list[dict]:
        graph = self._get_graph()
        if graph is None:
            return []

        candidate = query_for_plan(plan)
        if candidate is None:
            return []
        query, params = candidate
        try:
            return graph.search_cypher(query, params)
        except Exception as e:
            logger.warning("Graph planner query failed: %s", e)
            return []

    def close(self):
        if self._graph is not None:
            self._graph.close()
            self._graph = None
