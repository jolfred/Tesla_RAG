"""Построение сообществ графа (упрощённый вариант) и генерация резюме."""

import json
import time
from pathlib import Path

import community as community_louvain
import networkx as nx

from backend.config import NEO4J_URI, NEO4J_USER, NEO4J_PASS, STORAGE_DIR
from backend.utils.gigachat_client import GigaChatClient
from backend.utils.logger import setup_logger

logger = setup_logger("build_communities")

COMMUNITIES_PATH = STORAGE_DIR / "communities.json"

SYSTEM_PROMPT = (
    "Ты — аналитик студенческого движения. Ниже дан список сущностей и связей "
    "одного сообщества знаний о студенческих отрядах КГЭУ «Тесла». "
    "Составь краткое резюме (5-10 предложений, русский): какие это люди/организации/события, "
    "чем сообщество отличается, ключевые связи и даты. Не выдумывай фактов, которых нет в списке."
)


def load_graph() -> tuple[nx.Graph, dict]:
    from neo4j import GraphDatabase

    driver = GraphDatabase.driver(NEO4J_URI, auth=(NEO4J_USER, NEO4J_PASS))
    g = nx.Graph()
    node_meta: dict = {}
    with driver.session() as session:
        nodes = session.run(
            "MATCH (n) RETURN n.id AS id, n.type AS type, n.description AS desc"
        )
        for rec in nodes:
            nid = rec["id"]
            g.add_node(nid)
            node_meta[nid] = {
                "id": nid,
                "type": rec["type"],
                "description": rec["desc"],
            }

        rels = session.run(
            "MATCH (a)-[r]->(b) "
            "WHERE (r.type IS NOT NULL OR type(r) IS NOT NULL) "
            "RETURN a.id AS src, b.id AS tgt, r.type AS rtype, r.date AS date, "
            "r.role_title AS role_title, r.description AS rdesc"
        )
        for rec in rels:
            src, tgt = rec["src"], rec["tgt"]
            if src and tgt and g.has_node(src) and g.has_node(tgt):
                edge = {
                    "src": src,
                    "tgt": tgt,
                    "rtype": rec["rtype"],
                    "date": rec["date"],
                    "role_title": rec["role_title"],
                    "description": rec["rdesc"],
                }
                g.add_edge(src, tgt, meta=edge)
    driver.close()
    logger.info("Loaded graph: %d nodes, %d edges", g.number_of_nodes(), g.number_of_edges())
    return g, node_meta


def cluster(g: nx.Graph) -> dict[str, int]:
    partition = community_louvain.best_partition(g)
    logger.info("Clustered into %d communities", len(set(partition.values())))
    return partition


def write_community_ids(partition: dict[str, int]) -> None:
    from neo4j import GraphDatabase

    driver = GraphDatabase.driver(NEO4J_URI, auth=(NEO4J_USER, NEO4J_PASS))
    with driver.session() as session:
        for nid, cid in partition.items():
            session.run(
                "MATCH (n {id: $id}) SET n.community_id = $cid",
                id=nid, cid=int(cid),
            )
    driver.close()
    logger.info("Community ids written to Neo4j")


def build_communities_output(
    g: nx.Graph, partition: dict[str, int], node_meta: dict
) -> list[dict]:
    communities: dict[int, list[str]] = {}
    for nid, cid in partition.items():
        communities.setdefault(int(cid), []).append(nid)

    out = []
    for cid, members in sorted(communities.items()):
        entities = []
        edges = []
        for nid in members:
            node = node_meta.get(nid) or {"id": nid, "type": None, "description": None}
            entities.append({"id": nid, "type": node.get("type"), "description": node.get("description")})
        for u, v, data in g.edges(nid, data=True):
            meta = data.get("meta") or {}
            if int(partition[u]) != cid or int(partition[v]) != cid:
                continue
            # перечисляем рёбра между участниками сообщества
        for u, v, data in g.edges(data=True):
            if int(partition[u]) == cid and int(partition[v]) == cid:
                meta = data.get("meta") or {}
                edges.append(meta)
        out.append({
            "community_id": cid,
            "members": entities,
            "edges": edges[:150],
        })
    return out


def generate_summaries(communities: list[dict]) -> list[dict]:
    gigachat = GigaChatClient()
    result = []
    for i, comm in enumerate(communities):
        entity_lines = "\n".join(
            f"- {e['id']} [{e.get('type') or '?'}]"
            + (f": {e['description']}" if e.get("description") else "")
            for e in comm["members"][:80]
        )
        if len(comm["members"]) > 80:
            entity_lines += f"\n... ещё {len(comm['members'])-80} сущностей"

        edge_lines = "\n".join(
            f"- {e['src']} --[{e.get('rtype')}]--> {e['tgt']}"
            + (f" ({e.get('date')})" if e.get("date") else "")
            + (f" :: {e['description']}" if e.get("description") and len(str(e['description']))<200 else "")
            for e in comm["edges"][:80]
        )
        if len(comm["edges"]) > 80:
            edge_lines += f"\n... ещё {len(comm['edges'])-80} связей"

        prompt = f"=== СООБЩЕСТВО {comm['community_id']} ===\nСУЩНОСТИ:\n{entity_lines}\n\nСВЯЗИ:\n{edge_lines}"
        try:
            summary = gigachat.chat(
                [
                    {"role": "system", "content": SYSTEM_PROMPT},
                    {"role": "user", "content": prompt},
                ],
                max_tokens=800,
                temperature=0.2,
            )
        except Exception as e:
            logger.warning("Summary failed for community %s: %s", comm["community_id"], e)
            summary = ""

        comm["summary"] = summary
        result.append(comm)
    return result


def main() -> None:
    start = time.time()
    g, node_meta = load_graph()
    partition = cluster(g)
    write_community_ids(partition)
    communities = build_communities_output(g, partition, node_meta)
    communities = generate_summaries(communities)

    COMMUNITIES_PATH.parent.mkdir(parents=True, exist_ok=True)
    with open(COMMUNITIES_PATH, "w", encoding="utf-8") as f:
        json.dump(communities, f, ensure_ascii=False, indent=1)
    logger.info(
        "Saved %d communities to %s in %.1fs",
        len(communities),
        COMMUNITIES_PATH,
        time.time() - start,
    )


if __name__ == "__main__":
    main()