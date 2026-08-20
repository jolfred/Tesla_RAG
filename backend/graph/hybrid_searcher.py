from backend.graph.graph_builder import GraphBuilder
from backend.embeddings import qdrant_client as qdrant
from backend.utils.logger import setup_logger

logger = setup_logger("hybrid_searcher")


class HybridSearcher:
    def __init__(self):
        self._graph = None

    def _get_graph(self):
        if self._graph is None:
            try:
                self._graph = GraphBuilder()
            except Exception:
                self._graph = None
        return self._graph

    def search(self, query: str, top_k: int = 10) -> list[dict]:
        vector_results = qdrant.search(query, top_k=top_k * 2)
        graph = self._get_graph()

        if graph is None:
            return vector_results[:top_k]

        graph_results = []
        try:
            cypher = """
            MATCH (n)
            WHERE any(key IN keys(n) WHERE toString(n[key]) CONTAINS $query)
            RETURN n.id AS id, labels(n) AS type,
                   properties(n) AS properties LIMIT 20
            """
            rows = graph.search_cypher(cypher, {"query": query[:50]})

            for r in rows:
                props = r.get("properties", {})
                name = props.get("name") or props.get("title") or r.get("id", "")
                graph_results.append({
                    "score": 0.9,
                    "source": name,
                    "text": f"{r['type']}: {name}",
                    "type": "graph",
                })
        except Exception as e:
            logger.warning(f"Hybrid graph search failed: {e}")

        if not graph_results:
            return vector_results[:top_k]

        fused = self._reciprocal_rank_fusion(vector_results, graph_results)
        return fused[:top_k]

    def _reciprocal_rank_fusion(self, vector_results: list, graph_results: list, k: int = 60) -> list:
        scores = {}
        for rank, item in enumerate(vector_results):
            source = item.get("source", "")
            scores[source] = scores.get(source, 0) + 1 / (k + rank + 1)
        for rank, item in enumerate(graph_results):
            source = item.get("source", "")
            scores[source] = scores.get(source, 0) + 1 / (k + rank + 1)

        sorted_sources = sorted(scores.items(), key=lambda x: x[1], reverse=True)
        all_results = vector_results + graph_results
        seen = set()
        fused = []
        for source, _score in sorted_sources:
            for item in all_results:
                if item.get("source") == source and source not in seen:
                    item["fusion_score"] = round(_score, 3)
                    fused.append(item)
                    seen.add(source)
                    break
        return fused
