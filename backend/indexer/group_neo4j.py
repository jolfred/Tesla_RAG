"""Запись карточек VK-групп в Neo4j."""

from neo4j import GraphDatabase

from backend.indexer.group_meta import (
    GROUP_SOURCE_PREFIX,
    clean_entity_name,
    parse_units_from_description,
)
from backend.indexer.logger import setup_indexer_logger

logger = setup_indexer_logger()

_MERGE_ENTITY = (
    "MERGE (n:Entity {merge_key: $merge_key}) SET n.id = $id SET n.name = $id "
    "SET n.source_model = 'gigachat' SET n += $props"
)


def _merge_entity(session, name: str, props: dict) -> None:
    session.run(
        _MERGE_ENTITY,
        merge_key=f"gigachat::{name}",
        id=name,
        props=props,
    )


def _relate(session, src_name: str, dst_name: str, rel_type: str, **extra) -> None:
    session.run(
        f"MATCH (a:Entity {{merge_key: $src_key}}), (b:Entity {{merge_key: $dst_key}}) "
        f"MERGE (a)-[r:RELATES {{type: '{rel_type}', source_post_url: $src, source_model: 'gigachat'}}]->(b) "
        f"SET r += $props",
        src_key=f"gigachat::{src_name}",
        dst_key=f"gigachat::{dst_name}",
        src=extra.pop("source"),
        props=extra,
    )


def save_group_to_neo4j(driver: GraphDatabase.driver, meta: dict) -> None:
    domain = meta.get("domain", "")
    group_name = meta.get("name", "")
    description = meta.get("description", "")
    org_type = "hq" if domain == "rso_tesla" else "lso"
    source = f"{GROUP_SOURCE_PREFIX}{domain}"

    props = {
        "type": "Organization",
        "org_type": org_type,
        "group_domain": domain,
    }
    if description:
        props["description"] = description
    for key in ("members_count", "status", "site"):
        if meta.get(key):
            props[key] = meta[key]

    with driver.session() as session:
        session.run(
            "CREATE CONSTRAINT IF NOT EXISTS FOR (n:Entity) REQUIRE n.merge_key IS UNIQUE"
        )
        _merge_entity(session, group_name, props)

        for contact in meta.get("contacts", []):
            person_name = contact.get("name", "").strip()
            if not person_name:
                continue
            _merge_entity(session, person_name, {"type": "Person"})
            relation_props = {
                "role_title": contact.get("role_title", ""),
                "status": "active",
            }
            if contact.get("profile_url"):
                relation_props["profile_url"] = contact["profile_url"]
            _relate(session, person_name, group_name, "HOLDS_ROLE", source=source, **relation_props)

        for unit_ref, raw_name in parse_units_from_description(description):
            unit_name = clean_entity_name(raw_name)
            if not unit_name:
                continue
            _merge_entity(session, unit_name, {"type": "Organization", "org_type": "lso"})
            _relate(session, group_name, unit_name, "PART_OF", source=source)
            logger.debug("Unit from description: %s -> %s", unit_ref, unit_name)

        for link in meta.get("links", []):
            link_name = clean_entity_name(link.get("name", ""))
            link_url = link.get("url", "")
            if not link_name or not link_url:
                continue
            _merge_entity(session, link_name, {"type": "Organization", "org_type": "external"})
            _relate(session, group_name, link_name, "PART_OF", source=source, url=link_url)

    logger.info(
        "Saved group '%s' to Neo4j: %d contacts, %d units, %d links",
        group_name,
        len(meta.get("contacts", [])),
        len(parse_units_from_description(description)),
        len(meta.get("links", [])),
    )
