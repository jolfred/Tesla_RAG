"""Исполнитель графовых запросов (единый путь, Фаза 2+)."""

from backend.graph.graph_builder import GraphBuilder
from backend.rag.planner_queries import query_for_plan_v2
from backend.utils.logger import setup_logger

logger = setup_logger("graph_planner")


class GraphPlanner:
    def __init__(self):
        self._graph = None

    def _get_graph(self) -> GraphBuilder | None:
        if self._graph is None:
            try:
                self._graph = GraphBuilder()
            except Exception as e:
                logger.warning("GraphBuilder init failed: %s", e)
                self._graph = None
        return self._graph

    def execute_v2(self, plan: dict) -> tuple[list[dict], dict]:
        """Выполнение плана: строгие запросы по org_norm_id. Возвращает
        (строки, debug) — debug виден в панели «Рентген»."""
        graph = self._get_graph()
        if graph is None:
            return [], {"cypher": None, "params": {}}

        candidate = query_for_plan_v2(plan)
        if candidate is None:
            return [], {"cypher": None, "params": {}}
        query, params = candidate
        try:
            return graph.search_cypher(query, params), {"cypher": query, "params": params}
        except Exception as e:
            logger.warning("Graph planner v2 query failed: %s", e)
            return [], {"cypher": query, "params": params}

    def close(self):
        if self._graph is not None:
            self._graph.close()
            self._graph = None
