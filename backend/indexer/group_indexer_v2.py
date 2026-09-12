"""Сид метаданных VK-групп в граф v2 (онтология v2, source_model='llmgraph_gigachat').

Отличия от legacy group_indexer.py:
- HQ/отряды/контакты пишутся настоящими метками (:Organization/:Squad/:Person)
  и настоящими типами рёбер (PART_OF / COMMANDED / SUPPORTED_BY).
- Без описаний у узлов (решение: фактура только на рёбрах).
- HQ rso_tesla маппится на канонический узел 'штаб со кгэу тесла'
  (сливается с узлом из постов).
- Qdrant-карточка — тот же idempotent upsert (save_group_to_qdrant).
"""

from dotenv import load_dotenv

from backend.indexer.clients import init_clients
from backend.indexer.graph_schema_v2 import SOURCE_MODEL_V2
from backend.indexer.group_meta import (
    GROUP_SOURCE_PREFIX,
    clean_entity_name,
    group_card_text,
    load_group_files,
    parse_units_from_description,
)
from backend.indexer.group_qdrant import save_group_to_qdrant
from backend.indexer.logger import setup_indexer_logger
from backend.indexer.neo4j_writer_v2 import sanitize_graph, save_graph_v2
from backend.indexer.normalize import normalize_id

load_dotenv()

logger = setup_indexer_logger()

__all__ = ["build_group_graph", "process_group_indexer_v2"]

# Каноническое имя HQ для слияния с постовым узлом.
HQ_CANONICAL = {
    "rso_tesla": "Штаб СО КГЭУ «Тесла»",
}


def build_group_graph(meta: dict) -> tuple[list[dict], list[dict]]:
    """Сырые узлы/рёбра группы -> (raw_nodes, raw_rels) для sanitize_graph."""
    domain = meta.get("domain", "")
    group_name = meta.get("name", "")
    hq_display = HQ_CANONICAL.get(domain, group_name)
    hq_norm = normalize_id(hq_display)

    raw_nodes = [{"id": hq_display, "type": "Organization"}]
    raw_rels: list[dict] = []

    for contact in meta.get("contacts", []):
        person_name = (contact.get("name") or "").strip()
        if not person_name:
            continue
        raw_nodes.append({"id": person_name, "type": "Person"})
        raw_rels.append(
            {
                "source_id": person_name,
                "target_id": hq_display,
                "relation": "COMMANDED",
                "role_title": contact.get("role_title") or None,
                "status": "active",
            }
        )

    for _ref, raw_name in parse_units_from_description(meta.get("description", "")):
        unit_name = clean_entity_name(raw_name)
        if not unit_name or normalize_id(unit_name) == hq_norm:
            continue
        raw_nodes.append({"id": unit_name, "type": "Squad"})
        raw_rels.append(
            {
                "source_id": unit_name,
                "target_id": hq_display,
                "relation": "PART_OF",
                "status": "active",
            }
        )

    for link in meta.get("links", []):
        link_name = clean_entity_name(link.get("name", ""))
        if not link_name or not link.get("url"):
            continue
        raw_nodes.append({"id": link_name, "type": "Organization"})
        raw_rels.append(
            {
                "source_id": hq_display,
                "target_id": link_name,
                "relation": "SUPPORTED_BY",
                "status": "active",
            }
        )

    return raw_nodes, raw_rels


def _clear_v2_group_relations(driver) -> None:
    with driver.session() as session:
        session.run(
            "MATCH ()-[r]->() WHERE r.source_model = $model "
            "AND r.source_post_url STARTS WITH $prefix DELETE r",
            model=SOURCE_MODEL_V2,
            prefix=GROUP_SOURCE_PREFIX,
        )
    logger.info("Cleared old v2 group:// relations from Neo4j")


def process_group_indexer_v2() -> None:
    from pathlib import Path

    metas = load_group_files()
    logger.info("Loaded %d group metadata files for v2 seeding", len(metas))

    openai_client, neo4j_driver, qdrant_client = init_clients()
    _clear_v2_group_relations(neo4j_driver)

    total = errors = 0
    for meta in metas:
        domain = meta.get("domain", "unknown")
        source = f"{GROUP_SOURCE_PREFIX}{domain}"
        try:
            raw_nodes, raw_rels = build_group_graph(meta)
            nodes, rels = sanitize_graph(raw_nodes, raw_rels)
            save_graph_v2(
                neo4j_driver,
                nodes,
                rels,
                source_model=SOURCE_MODEL_V2,
                post_url=source,
                post_date=None,
                group_name=meta.get("name", ""),
            )

            embedding_response = openai_client.embeddings.create(
                model="text-embedding-3-small",
                input=group_card_text(meta),
            )
            save_group_to_qdrant(
                qdrant_client, meta, embedding_response.data[0].embedding
            )
            total += 1
            logger.info("Seeded v2 group '%s' successfully", domain)
        except Exception:
            logger.exception("Error seeding v2 group '%s'", domain)
            errors += 1

    neo4j_driver.close()
    logger.info(
        "Group v2 seeding complete: %d succeeded, %d failed out of %d",
        total,
        errors,
        len(metas),
    )


if __name__ == "__main__":
    process_group_indexer_v2()
