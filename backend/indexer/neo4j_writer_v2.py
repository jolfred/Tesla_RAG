"""Запись графа v2 в Neo4j: настоящие метки, батчи, provenance из кода.

Отличия от legacy neo4j_writer.py:
- Узлы получают настоящую метку (:Person, :Squad, ...) + :Entity для совместимости.
  Тип больше не лежит только в свойстве n.type.
- Рёбра — настоящими типами [:MEMBER_OF], а не [:RELATES {type: ...}].
- Batch-запись через UNWIND (один round-trip на пост, а не N).
- source_post_url/date дописываются из метаданных поста детерминированно
  (legacy просил их у LLM -> 72% null).
- MERGE узлов по нормализованному norm_id (см. normalize.py).
- :Post-узел + (:Post)-[:DESCRIBES]-> для обратного индекса по посту.
"""

from neo4j import GraphDatabase

from backend.indexer.graph_schema_v2 import (
    ALLOWED_NODES,
    ALLOWED_REL_TYPES,
    STOP_NODES,
)
from backend.indexer.logger import setup_indexer_logger
from backend.indexer.normalize import merge_key, normalize_id

logger = setup_indexer_logger()

_ALLOWED_NODE_SET = set(ALLOWED_NODES)
_ALLOWED_REL_SET = set(ALLOWED_REL_TYPES)


def sanitize_graph(
    nodes: list[dict], rels: list[dict]
) -> tuple[list[dict], list[dict]]:
    """Пост-фильтр после LLM: strict-онтология, стоп-лист, синонимы.

    Узлы хранят только {norm_id, name, type} — описаний у узлов нет
    (вся фактура на рёбрах). Дубли схлопываются по norm_id.
    nodes: [{id, type, ...}], rels: [{source_id, target_id, relation, ...}]
    Возвращает очищенные списки. Узлы без рёбер (орфаны) дропаются.
    """
    kept_nodes: dict[str, dict] = {}
    for n in nodes:
        raw_id = (n.get("id") or "").strip()
        ntype = (n.get("type") or "").strip()
        if not raw_id or ntype not in _ALLOWED_NODE_SET:
            continue
        norm = normalize_id(raw_id)
        if not norm or norm in STOP_NODES:
            logger.debug("Dropping stop/garbage node %r (%s)", raw_id, ntype)
            continue
        if norm in kept_nodes:
            # Дубли: первое имя побеждает, тип дополняем при конфликте позже (мультиметка).
            if kept_nodes[norm]["type"] != ntype:
                logger.debug(
                    "Type conflict for %r: %s vs %s",
                    raw_id,
                    kept_nodes[norm]["type"],
                    ntype,
                )
        else:
            kept_nodes[norm] = {"norm_id": norm, "name": raw_id, "type": ntype}

    kept_rels: list[dict] = []
    linked: set[str] = set()
    for r in rels:
        rel = (r.get("relation") or r.get("type") or "").strip()
        s = normalize_id((r.get("source_id") or "").strip())
        t = normalize_id((r.get("target_id") or "").strip())
        if not rel or rel not in _ALLOWED_REL_SET:
            continue
        if s not in kept_nodes or t not in kept_nodes:
            continue  # висячее ребро
        if s == t:
            continue  # петля на себя
        kept_rels.append(
            {
                "src": s,
                "tgt": t,
                "relation": rel,
                "role_title": r.get("role_title"),
                "status": r.get("status") or "active",
                "description": (r.get("description") or "").strip() or None,
            }
        )
        linked.add(s)
        linked.add(t)

    # Дроп орфанов: узел без рёбер в граф не пишем.
    final_nodes = [n for k, n in kept_nodes.items() if k in linked]
    if len(final_nodes) < len(kept_nodes):
        logger.debug(
            "Dropping %d orphan nodes", len(kept_nodes) - len(final_nodes)
        )
    return final_nodes, kept_rels


def get_indexed_post_urls_v2(driver, source_model: str) -> set[str]:
    """URL постов, уже записанных веткой v2 (для resume поверх --force)."""
    with driver.session() as session:
        rows = session.run(
            "MATCH (p:Post {source_model: $m}) RETURN p.url AS url", m=source_model
        )
        return {r["url"] for r in rows if r["url"]}


def save_graph_v2(
    driver: GraphDatabase.driver,
    nodes: list[dict],
    rels: list[dict],
    source_model: str,
    post_url: str | None = None,
    post_date: str | None = None,
    group_name: str | None = None,
) -> tuple[int, int]:
    """Batch-запись одного поста. Возвращает (n_nodes, n_rels)."""
    if not nodes:
        return 0, 0

    node_rows = []
    for n in nodes:
        node_rows.append(
            {
                "merge_key": merge_key(source_model, n["norm_id"]),
                "norm_id": n["norm_id"],
                "name": n["name"],
                "label": n["type"],
                "source_model": source_model,
            }
        )

    rel_rows = []
    for r in rels:
        rel_rows.append(
            {
                "src_key": merge_key(source_model, r["src"]),
                "tgt_key": merge_key(source_model, r["tgt"]),
                "relation": r["relation"],
                "source_model": source_model,
                "source_post_url": post_url,
                "date": post_date,
                "role_title": r.get("role_title"),
                "status": r.get("status") or "active",
                "description": r.get("description"),
            }
        )

    with driver.session() as session:
        # Узлы: MERGE по merge_key + настоящая метка.
        # Метку параметризовать в Cypher нельзя -> один запрос на тип узла
        # (типов <= 9, вместо N запросов в legacy).
        by_label: dict[str, list[dict]] = {}
        for r in node_rows:
            by_label.setdefault(r["label"], []).append(r)
        for label, rows in by_label.items():
            if label not in _ALLOWED_NODE_SET:
                continue
            session.run(
                f"""
                UNWIND $rows AS row
                MERGE (n:Entity {{merge_key: row.merge_key}})
                SET n:{label},
                    n.norm_id = row.norm_id,
                    n.id = row.name,
                    n.name = row.name,
                    n.type = row.label,
                    n.source_model = row.source_model
                """,
                rows=rows,
            )
        # Рёбра настоящими типами: тип параметризовать нельзя -> один
        # запрос на тип связи (типов ~14, постов тысячи: всё равно выигрыш).
        by_type: dict[str, list[dict]] = {}
        for row in rel_rows:
            by_type.setdefault(row["relation"], []).append(row)
        n_rels = 0
        for rel_type, rows in by_type.items():
            res = session.run(
                f"""
                UNWIND $rows AS row
                MATCH (a:Entity {{merge_key: row.src_key}}),
                      (b:Entity {{merge_key: row.tgt_key}})
                MERGE (a)-[r:{rel_type} {{source_model: row.source_model}}]->(b)
                SET r.type = row.relation,
                    r.source_post_url = coalesce(row.source_post_url, r.source_post_url),
                    r.date = coalesce(row.date, r.date),
                    r.role_title = coalesce(row.role_title, r.role_title),
                    r.status = coalesce(row.status, r.status),
                    r.description = coalesce(row.description, r.description)
                """,
                rows=[{k: v for k, v in r.items() if k != "relation"} for r in rows],
            )
            n_rels += (res.consume().counters.relationships_created or 0)
        # :Post-узел + обратный индекс.
        if post_url:
            session.run(
                """
                MERGE (p:Post {url: $url})
                SET p.published_at = coalesce($date, p.published_at),
                    p.group_name = coalesce($group, p.group_name),
                    p.source_model = $model
                WITH p
                UNWIND $keys AS k
                MATCH (n:Entity {merge_key: k})
                MERGE (p)-[:DESCRIBES]->(n)
                """,
                url=post_url,
                date=post_date,
                group=group_name,
                model=source_model,
                keys=[r["merge_key"] for r in node_rows],
            )

    logger.info(
        "Saved v2 to Neo4j (%s): %d entities, %d relationships (post %s)",
        source_model,
        len(node_rows),
        len(rel_rows),
        post_url,
    )
    return len(node_rows), len(rel_rows)
