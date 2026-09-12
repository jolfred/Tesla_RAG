"""Метрики пилота LLMGraphTransformer: ветка source_model vs legacy.

Usage:
  .venv/bin/python -m backend.scripts.pilot_metrics --model llmgraph_gigachat
  .venv/bin/python -m backend.scripts.pilot_metrics --model gigachat
"""

import argparse
import os

from dotenv import load_dotenv
from neo4j import GraphDatabase

load_dotenv()


def metrics(driver, model: str) -> dict:
    with driver.session() as s:
        total_nodes = s.run(
            "MATCH (n:Entity {source_model: $m}) RETURN count(*) AS c", m=model
        ).single()["c"]
        orphans = s.run(
            "MATCH (n:Entity {source_model: $m}) WHERE NOT (n)--() RETURN count(*) AS c",
            m=model,
        ).single()["c"]
        total_rels = s.run(
            "MATCH ()-[r]->() WHERE r.source_model = $m RETURN count(*) AS c", m=model
        ).single()["c"]
        with_url = s.run(
            "MATCH ()-[r]->() WHERE r.source_model = $m "
            "AND r.source_post_url IS NOT NULL AND r.source_post_url <> '' "
            "RETURN count(*) AS c",
            m=model,
        ).single()["c"]
        with_date = s.run(
            "MATCH ()-[r]->() WHERE r.source_model = $m AND r.date IS NOT NULL "
            "RETURN count(*) AS c",
            m=model,
        ).single()["c"]
        by_label = {
            r["label"]: r["c"]
            for r in s.run(
                "MATCH (n:Entity {source_model: $m}) "
                "RETURN coalesce(n.type, 'NULL') AS label, count(*) AS c "
                "ORDER BY c DESC",
                m=model,
            )
        }
        generic = s.run(
            "MATCH (n:Entity {source_model: $m}) "
            "WHERE n.description IS NOT NULL "
            "RETURN count(*) AS c",
            m=model,
        ).single()["c"]
        rel_desc = s.run(
            "MATCH ()-[r]->() WHERE r.source_model = $m "
            "AND r.description IS NOT NULL AND r.description <> '' "
            "RETURN count(*) AS c",
            m=model,
        ).single()["c"]
        post_nodes = s.run("MATCH (p:Post {source_model: $m}) RETURN count(*) AS c", m=model).single()["c"]
        typed_rels = s.run(
            "MATCH ()-[r]->() WHERE r.source_model = $m AND type(r) <> 'RELATES' "
            "RETURN count(*) AS c",
            m=model,
        ).single()["c"]
    return {
        "model": model,
        "nodes": total_nodes,
        "orphans": orphans,
        "orphan_rate": round(orphans / total_nodes, 3) if total_nodes else 0,
        "rels": total_rels,
        "typed_rels": typed_rels,
        "url_coverage": round(with_url / total_rels, 3) if total_rels else 0,
        "date_coverage": round(with_date / total_rels, 3) if total_rels else 0,
        "nodes_with_desc": generic,
        "rels_with_desc": rel_desc,
        "post_nodes": post_nodes,
        "by_label": by_label,
    }


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--model", default="llmgraph_gigachat")
    args = parser.parse_args()
    driver = GraphDatabase.driver(
        os.getenv("NEO4J_URI", "bolt://localhost:7687"),
        auth=(os.getenv("NEO4J_USER", "neo4j"), os.getenv("NEO4J_PASS", "tesla_neo4j")),
    )
    import json

    print(json.dumps(metrics(driver, args.model), ensure_ascii=False, indent=2))
    driver.close()


if __name__ == "__main__":
    main()
