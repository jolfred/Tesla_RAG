from neo4j import GraphDatabase

from backend.indexer.logger import setup_indexer_logger
from backend.indexer.schemas import GraphExtractionResult

logger = setup_indexer_logger()


def merge_key(source_model: str, entity_id: str) -> str:
    return f"{source_model}::{entity_id}"


def migrate_neo4j_for_dual_model(driver: GraphDatabase.driver) -> None:
    with driver.session() as session:
        session.run(
            "MATCH (n:Entity) WHERE n.source_model IS NULL "
            "SET n.source_model = 'gigachat', "
            "n.merge_key = 'gigachat::' + coalesce(n.id, '')"
        )
        session.run(
            "MATCH (n:Entity) WHERE n.source_model IS NOT NULL AND n.merge_key IS NULL "
            "SET n.merge_key = n.source_model + '::' + coalesce(n.id, '')"
        )
        session.run(
            "MATCH ()-[r:RELATES]->() WHERE r.source_model IS NULL "
            "SET r.source_model = 'gigachat'"
        )
        rows = session.run(
            "SHOW CONSTRAINTS YIELD name, labelsOrTypes, properties"
        ).data()
        for row in rows:
            labels = [str(l) for l in (row.get("labelsOrTypes") or [])]
            props = [str(p) for p in (row.get("properties") or [])]
            if "Entity" in labels and props == ["id"]:
                session.run(f"DROP CONSTRAINT {row['name']} IF EXISTS")
                logger.info("Dropped old single-field constraint %s", row["name"])
        session.run(
            "CREATE CONSTRAINT IF NOT EXISTS "
            "FOR (n:Entity) REQUIRE n.merge_key IS UNIQUE"
        )
        logger.info(
            "Neo4j migrated for dual-model storage (merge_key unique per model)"
        )


def save_to_neo4j(
    driver: GraphDatabase.driver, result: GraphExtractionResult, source_model: str
) -> None:
    with driver.session() as session:
        for entity in result.entities:
            props = {"type": entity.type.value, "source_model": source_model}
            if entity.org_type:
                props["org_type"] = entity.org_type.value
            if entity.description:
                props["description"] = entity.description
            session.run(
                "MERGE (n:Entity {merge_key: $merge_key}) "
                "SET n.id = $id SET n.name = $id SET n.source_model = $source_model "
                "SET n += $props",
                merge_key=merge_key(source_model, entity.id),
                id=entity.id,
                source_model=source_model,
                props=props,
            )
        for rel in result.relationships:
            props = {"source_model": source_model}
            if rel.date:
                props["date"] = rel.date
            if rel.source_post_url:
                props["source_post_url"] = rel.source_post_url
            if rel.role_title:
                props["role_title"] = rel.role_title
            if rel.status:
                props["status"] = rel.status
            if rel.description:
                props["description"] = rel.description
            session.run(
                "MATCH (a:Entity {merge_key: $src_key}), "
                "(b:Entity {merge_key: $tgt_key}) "
                "MERGE (a)-[r:RELATES {type: $rel, source_model: $model}]->(b) "
                "SET r += $props",
                src_key=merge_key(source_model, rel.source_id),
                tgt_key=merge_key(source_model, rel.target_id),
                rel=rel.relation.value,
                model=source_model,
                props=props,
            )
    logger.info(
        "Saved to Neo4j (%s): %d entities, %d relationships",
        source_model,
        len(result.entities),
        len(result.relationships),
    )
