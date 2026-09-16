from neo4j import GraphDatabase
from backend.config import NEO4J_URI, NEO4J_USER, NEO4J_PASS
from backend.utils.logger import setup_logger

logger = setup_logger("graph_builder")

import logging


class _EventDateNoticeFilter(logging.Filter):
    """Глушит известное безвредное уведомление Neo4j.

    Строгие запросы читают r.event_date, которого нет на старых рёбрах
    (null — норма, см. planner_common._V3_PROPS). Сервер шлёт WARNING
    на каждый такой запрос — спам без пользы. Глушим ТОЛЬКО это
    уведомление по точному тексту; остальные проходят.
    """

    def filter(self, record: logging.LogRecord) -> bool:
        try:
            msg = record.getMessage()
        except Exception:
            return True
        return "property `event_date` does not exist" not in msg


logging.getLogger("neo4j").addFilter(_EventDateNoticeFilter())


class GraphBuilder:
    def __init__(self):
        self.driver = GraphDatabase.driver(NEO4J_URI, auth=(NEO4J_USER, NEO4J_PASS))

    def close(self):
        self.driver.close()

    def create_constraints(self):
        with self.driver.session() as session:
            session.run(
                "CREATE CONSTRAINT IF NOT EXISTS FOR (n:Entity) REQUIRE n.merge_key IS UNIQUE"
            )
            logger.info("Graph constraints created (Entity)")

    def build_from_extraction(self, extraction: dict):
        entities = extraction.get("entities", [])
        relationships = extraction.get("relationships", [])

        with self.driver.session() as session:
            for e in entities:
                props = {}
                if e.get("org_type"):
                    props["org_type"] = e["org_type"]
                if e.get("description"):
                    props["description"] = e["description"]
                session.run(
                    "MERGE (n:Entity {id: $id}) SET n.name = $id SET n += $props",
                    id=e["id"], props=props,
                )
            for r in relationships:
                props = {}
                if r.get("date"):
                    props["date"] = r["date"]
                if r.get("role_title"):
                    props["role_title"] = r["role_title"]
                if r.get("status"):
                    props["status"] = r["status"]
                if r.get("description"):
                    props["description"] = r["description"]
                session.run(
                    "MATCH (a:Entity {id: $src}), (b:Entity {id: $tgt}) "
                    "MERGE (a)-[rel:RELATIONSHIP {type: $rel}]->(b) SET rel += $props",
                    src=r["source_id"], tgt=r["target_id"], rel=r["relation"], props=props,
                )

        logger.info(
            f"Graph updated: {len(entities)} entities, "
            f"{len(relationships)} relationships"
        )

    def delete_by_source(self, source: str):
        with self.driver.session() as session:
            session.run(
                "MATCH (n) WHERE n.source = $source DETACH DELETE n",
                source=source,
            )
            logger.info(f"Deleted nodes for source '{source}'")

    def find_related(self, entity_type: str, entity_id: str, max_depth: int = 2) -> list[str]:
        with self.driver.session() as session:
            result = session.run(
                f"MATCH path = (n:{entity_type} {{id: $entity_id}})-[*1..{max_depth}]-(related) "
                f"RETURN path LIMIT 50",
                entity_id=entity_id,
            )
            return [str(record["path"]) for record in result]

    def search_cypher(self, query: str, params: dict = None) -> list[dict]:
        with self.driver.session() as session:
            result = session.run(query, params or {})
            return [record.data() for record in result]

    def search_by_query(self, query: str, top_k: int = 20) -> list[dict]:
        cypher = """
        MATCH (n)
        WHERE any(key IN keys(n) WHERE n[key] CONTAINS $query)
        OPTIONAL MATCH (n)-[r]-(m)
        RETURN n.id AS id, labels(n) AS type,
               properties(n) AS properties,
               collect({type: type(r), direction: CASE WHEN startNode(r) = n THEN 'out' ELSE 'in' END,
                        target_id: m.id, target_type: labels(m)}) AS relations
        LIMIT $limit
        """
        return self.search_cypher(cypher, {"query": query, "limit": top_k})

    def get_stats(self) -> dict:
        stats = {"total_nodes": 0, "total_relations": 0, "nodes_by_type": {}, "relations_by_type": {}}
        try:
            node_result = self.search_cypher("MATCH (n) RETURN labels(n) AS type, count(n) AS cnt")
            for row in node_result:
                label = row["type"][0] if row["type"] else "Unknown"
                stats["nodes_by_type"][label] = row["cnt"]
                stats["total_nodes"] += row["cnt"]

            rel_result = self.search_cypher("MATCH ()-[r]->() RETURN type(r) AS type, count(r) AS cnt")
            for row in rel_result:
                stats["relations_by_type"][row["type"]] = row["cnt"]
                stats["total_relations"] += row["cnt"]
        except Exception:
            pass
        return stats
