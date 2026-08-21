"""Индексация метаданных VK-групп в Neo4j + Qdrant."""

from dotenv import load_dotenv

from backend.indexer.clients import init_clients
from backend.indexer.group_meta import (
    GROUPS_DIR,
    GROUP_SOURCE_PREFIX,
    group_card_text,
    load_group_files,
)
from backend.indexer.group_neo4j import save_group_to_neo4j
from backend.indexer.group_qdrant import save_group_to_qdrant
from backend.indexer.logger import setup_indexer_logger

load_dotenv()

logger = setup_indexer_logger()

__all__ = ["process_group_indexer"]


def _clear_old_relations(driver) -> None:
    with driver.session() as session:
        session.run(
            "MATCH ()-[r:RELATES]->() WHERE r.source_post_url STARTS WITH $prefix DETACH DELETE r",
            prefix=GROUP_SOURCE_PREFIX,
        )
    logger.info("Cleared old group:// relations from Neo4j")


def process_group_indexer() -> None:
    metas = load_group_files()
    logger.info("Loaded %d group metadata files from %s", len(metas), GROUPS_DIR)

    openai_client, neo4j_driver, qdrant_client = init_clients()
    _clear_old_relations(neo4j_driver)

    total = 0
    errors = 0
    for meta in metas:
        domain = meta.get("domain", "unknown")
        try:
            save_group_to_neo4j(neo4j_driver, meta)

            embedding_response = openai_client.embeddings.create(
                model="text-embedding-3-small",
                input=group_card_text(meta),
            )
            vector = embedding_response.data[0].embedding
            save_group_to_qdrant(qdrant_client, meta, vector)

            total += 1
            logger.info("Indexed group '%s' successfully", domain)
        except Exception:
            logger.exception("Error indexing group '%s'", domain)
            errors += 1

    neo4j_driver.close()
    logger.info(
        "Group indexing complete: %d succeeded, %d failed out of %d",
        total,
        errors,
        len(metas),
    )


if __name__ == "__main__":
    process_group_indexer()
