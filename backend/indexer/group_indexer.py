import glob as globlib
import json
import re
import uuid
from datetime import datetime, timezone
from pathlib import Path

from dotenv import load_dotenv
from neo4j import GraphDatabase
from openai import OpenAI
from qdrant_client import QdrantClient
from qdrant_client.http.models import Distance, PointStruct, VectorParams

from backend.indexer.indexer import init_clients
from backend.indexer.logger import setup_indexer_logger

load_dotenv()

logger = setup_indexer_logger()

GROUPS_DIR = Path(__file__).resolve().parent.parent.parent / "storage" / "groups"
QDRANT_COLLECTION = "posts"
GROUP_SOURCE_PREFIX = "group://"

_FROM_DESC_RE = re.compile(r"\[(club\d+|[^|\]]+)\|([^|\]]+)\]")


def _today() -> str:
    return datetime.now(timezone.utc).date().isoformat() + "T00:00:00Z"


def _load_group_files() -> list[dict]:
    metas = []
    for pattern in [str(GROUPS_DIR / "groups_*.json")]:
        for path_str in sorted(globlib.glob(pattern)):
            path = Path(path_str)
            try:
                with path.open(encoding="utf-8") as f:
                    metas.append(json.load(f))
            except (json.JSONDecodeError, OSError) as e:
                logger.warning("Cannot load %s: %s", path, e)
    return metas


def _parse_units_from_description(description: str) -> list[tuple[str, str]]:
    """Из описания: [club144172595|«Монолит»] → (club_id_or_url, name)."""
    return [(clean, name) for clean, name in _FROM_DESC_RE.findall(description)]


def _clean_entity_name(name: str) -> str:
    return name.strip().strip('«»"').strip()


def save_group_to_neo4j(driver, meta: dict) -> None:
    domain = meta.get("domain", "")
    group_name = meta.get("name", "")
    description = meta.get("description", "")
    org_type = "hq" if domain == "rso_tesla" else "lso"

    props = {
        "type": "Organization",
        "org_type": org_type,
        "group_domain": domain,
    }
    if description:
        props["description"] = description
    if meta.get("members_count"):
        props["members_count"] = meta["members_count"]
    if meta.get("status"):
        props["status"] = meta["status"]
    if meta.get("site"):
        props["site"] = meta["site"]

    with driver.session() as session:
        session.run(
            "CREATE CONSTRAINT IF NOT EXISTS FOR (n:Entity) REQUIRE n.merge_key IS UNIQUE"
        )

        session.run(
            "MERGE (n:Entity {merge_key: $merge_key}) SET n.id = $id SET n.name = $id "
            "SET n.source_model = 'gigachat' SET n += $props",
            merge_key=f"gigachat::{group_name}",
            id=group_name,
            props=props,
        )

        for contact in meta.get("contacts", []):
            person_name = contact.get("name", "").strip()
            if not person_name:
                continue
            role_title = contact.get("role_title", "")
            profile_url = contact.get("profile_url", "")
            person_props = {"type": "Person"}
            session.run(
                "MERGE (n:Entity {merge_key: $merge_key}) SET n.id = $id SET n.name = $id "
                "SET n.source_model = 'gigachat' SET n += $props",
                merge_key=f"gigachat::{person_name}",
                id=person_name,
                props=person_props,
            )
            relation_props = {
                "role_title": role_title,
                "status": "active",
                "source_post_url": f"{GROUP_SOURCE_PREFIX}{domain}",
            }
            if profile_url:
                relation_props["profile_url"] = profile_url
            session.run(
                "MATCH (a:Entity {merge_key: $person_key}), (b:Entity {merge_key: $group_key}) "
                "MERGE (a)-[r:RELATES {type: 'HOLDS_ROLE', source_post_url: $src, source_model: 'gigachat'}]->(b) "
                "SET r += $props",
                person_key=f"gigachat::{person_name}",
                group_key=f"gigachat::{group_name}",
                src=f"{GROUP_SOURCE_PREFIX}{domain}",
                props=relation_props,
            )

        for unit_ref, raw_name in _parse_units_from_description(description):
            unit_name = _clean_entity_name(raw_name)
            if not unit_name:
                continue
            unit_props = {"type": "Organization", "org_type": "lso"}
            session.run(
                "MERGE (n:Entity {merge_key: $merge_key}) SET n.id = $id SET n.name = $id "
                "SET n.source_model = 'gigachat' SET n += $props",
                merge_key=f"gigachat::{unit_name}",
                id=unit_name,
                props=unit_props,
            )
            session.run(
                "MATCH (a:Entity {merge_key: $group_key}), (b:Entity {merge_key: $unit_key}) "
                "MERGE (a)-[r:RELATES {type: 'PART_OF', source_post_url: $src, source_model: 'gigachat'}]->(b)",
                group_key=f"gigachat::{group_name}",
                unit_key=f"gigachat::{unit_name}",
                src=f"{GROUP_SOURCE_PREFIX}{domain}",
            )
            logger.debug("Unit from description: %s -> %s", unit_ref, unit_name)

        for link in meta.get("links", []):
            link_name = _clean_entity_name(link.get("name", ""))
            link_url = link.get("url", "")
            if not link_name or not link_url:
                continue
            link_props = {"type": "Organization", "org_type": "external"}
            session.run(
                "MERGE (n:Entity {merge_key: $merge_key}) SET n.id = $id SET n.name = $id "
                "SET n.source_model = 'gigachat' SET n += $props",
                merge_key=f"gigachat::{link_name}",
                id=link_name,
                props=link_props,
            )
            session.run(
                "MATCH (a:Entity {merge_key: $group_key}), (b:Entity {merge_key: $link_key}) "
                "MERGE (a)-[r:RELATES {type: 'PART_OF', source_post_url: $src, source_model: 'gigachat'}]->(b) SET r.url = $url",
                group_key=f"gigachat::{group_name}",
                link_key=f"gigachat::{link_name}",
                src=f"{GROUP_SOURCE_PREFIX}{domain}",
                url=link_url,
            )

    logger.info(
        "Saved group '%s' to Neo4j: %d contacts, %d units, %d links",
        group_name,
        len(meta.get("contacts", [])),
        len(_parse_units_from_description(description)),
        len(meta.get("links", [])),
    )


def _group_card_text(meta: dict) -> str:
    parts = [f"Группа: {meta.get('name', '')}"]
    if meta.get("status"):
        parts.append(f"Статус: {meta['status']}")
    if meta.get("members_count"):
        parts.append(f"Участников: {meta['members_count']}")
    if meta.get("description"):
        parts.append(f"Описание: {meta['description']}")
    if meta.get("contacts"):
        contacts = "; ".join(
            f"{c.get('name', '')} — {c.get('role_title', '')}"
            for c in meta["contacts"]
        )
        parts.append(f"Контакты: {contacts}")
    if meta.get("links"):
        links = ", ".join(link.get("name", "") for link in meta["links"])
        parts.append(f"Связанные сообщества: {links}")
    return "\n".join(parts)


def save_group_to_qdrant(qclient: QdrantClient, meta: dict, vector: list[float]) -> None:
    domain = meta.get("domain", "")
    collections = qclient.get_collections().collections
    if not any(c.name == QDRANT_COLLECTION for c in collections):
        qclient.create_collection(
            collection_name=QDRANT_COLLECTION,
            vectors_config=VectorParams(size=len(vector), distance=Distance.COSINE),
        )
        logger.info("Created Qdrant collection '%s'", QDRANT_COLLECTION)

    post_url = f"{GROUP_SOURCE_PREFIX}{domain}"
    point = PointStruct(
        id=str(uuid.uuid5(uuid.NAMESPACE_URL, post_url)),
        vector=vector,
        payload={
            "post_url": post_url,
            "published_at": _today(),
            "group_name": meta.get("name", ""),
            "text_clean": _group_card_text(meta),
        },
    )
    qclient.upsert(collection_name=QDRANT_COLLECTION, points=[point])
    logger.info("Upserted group card %s to Qdrant", post_url)


def process_group_indexer() -> None:
    metas = _load_group_files()
    logger.info("Loaded %d group metadata files from %s", len(metas), GROUPS_DIR)

    openai_client, neo4j_driver, qdrant_client = init_clients()

    with neo4j_driver.session() as session:
        session.run(
            "MATCH ()-[r:RELATES]->() WHERE r.source_post_url STARTS WITH $prefix DETACH DELETE r",
            prefix=GROUP_SOURCE_PREFIX,
        )
    logger.info("Cleared old group:// relations from Neo4j")

    total = 0
    errors = 0
    for meta in metas:
        domain = meta.get("domain", "unknown")
        try:
            save_group_to_neo4j(neo4j_driver, meta)

            card_text = _group_card_text(meta)
            embedding_response = openai_client.embeddings.create(
                model="text-embedding-3-small",
                input=card_text,
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