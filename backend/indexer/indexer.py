import argparse
import glob as globlib
import json
import os
import uuid
from concurrent.futures import ThreadPoolExecutor, as_completed
from datetime import datetime, timezone
from pathlib import Path
from typing import Optional

from dotenv import load_dotenv
from neo4j import GraphDatabase
from openai import OpenAI
from qdrant_client import QdrantClient
from qdrant_client.http.models import Distance, PointStruct, VectorParams

from backend.config import GIGACHAT_MODEL, LLM_PROVIDER
from backend.indexer.logger import setup_indexer_logger
from backend.indexer.schemas import GraphExtractionResult
from backend.utils.gemma_client import GemmaClient
from backend.utils.gigachat_client import GigaChatClient

load_dotenv()

logger = setup_indexer_logger()

SYSTEM_PROMPT = """You are an expert Knowledge Graph Extraction Engine. Extract entities and relationships from the given social media post text according to the strict ontology below.

ALLOWED ENTITY TYPES: Person, Organization, Role, Award, Event, Project, Location, Profession.

For Organization entities, you may set org_type to one of: hq, lso, university, external, partner.

ALLOWED RELATIONSHIP TYPES: HOLDS_ROLE, WON_AWARD, MEMBER_OF, PARTICIPATED_IN, ORGANIZED, PART_OF, LOCATED_IN, HELD_AT, TRAINED_IN, SUPPORTED_BY.

Output MUST be valid JSON matching this structure:
{
  "entities": [
    {
      "id": "Canonical entity name",
      "type": "Person | Organization | Role | Award | Event | Project | Location | Profession",
      "org_type": "hq | lso | university | external | partner | null",
      "description": "Brief description or null"
    }
  ],
  "relationships": [
    {
      "source_id": "Canonical entity name",
      "target_id": "Canonical entity name",
      "relation": "HOLDS_ROLE | WON_AWARD | MEMBER_OF | PARTICIPATED_IN | ORGANIZED | PART_OF | LOCATED_IN | HELD_AT | TRAINED_IN | SUPPORTED_BY",
      "date": null,
      "source_post_url": null,
      "role_title": null,
      "status": "active",
      "description": "Brief context or null"
    }
  ]
}"""


class OpenAIExtractor:
    def __init__(self, client: OpenAI, model: str = "openai/gpt-4o-mini"):
        self._client = client
        self._model = model

    def extract_json(self, system_prompt: str, text: str, **kwargs) -> dict:
        response = self._client.chat.completions.create(
            model=self._model,
            messages=[
                {"role": "system", "content": system_prompt},
                {"role": "user", "content": text},
            ],
            response_format={"type": "json_object"},
            temperature=0.1,
            max_tokens=4096,
        )
        raw = response.choices[0].message.content.strip()
        return GraphExtractionResult.model_validate_json(raw).model_dump()


def init_clients() -> tuple[OpenAI, GraphDatabase.driver, QdrantClient]:
    openai_client = OpenAI(
        base_url=os.getenv("PROXYAPI_BASE_URL", "https://openai.api.proxyapi.ru/v1"),
        api_key=os.getenv("PROXYAPI_KEY", ""),
    )
    openai_client.models.list()

    neo4j_uri = os.getenv("NEO4J_URI", "bolt://localhost:7687")
    neo4j_user = os.getenv("NEO4J_USER", "neo4j")
    neo4j_pass = os.getenv("NEO4J_PASS", "tesla_neo4j")
    neo4j_driver = GraphDatabase.driver(neo4j_uri, auth=(neo4j_user, neo4j_pass))
    with neo4j_driver.session() as session:
        session.run("RETURN 1")

    qdrant_host = os.getenv("QDRANT_HOST", "localhost")
    qdrant_port = int(os.getenv("QDRANT_PORT", "6333"))
    qdrant_api_key = os.getenv("QDRANT_API_KEY", None)
    qdrant_client = QdrantClient(
        host=qdrant_host,
        port=qdrant_port,
        api_key=qdrant_api_key if qdrant_api_key else None,
    )
    qdrant_client.get_collections()

    logger.info("All clients initialized and connected successfully")
    return openai_client, neo4j_driver, qdrant_client


def _parse_dt(value: str) -> datetime:
    dt = datetime.fromisoformat(value.replace("Z", "+00:00"))
    if dt.tzinfo is None:
        dt = dt.replace(tzinfo=timezone.utc)
    return dt


def filter_posts(posts: list[dict], min_date: str = "2026-01-01") -> list[dict]:
    if not min_date:
        return posts
    min_dt = _parse_dt(min_date)
    result = []
    for post in posts:
        published_str = post.get("published_at")
        if not published_str:
            continue
        try:
            published_dt = _parse_dt(published_str)
        except (ValueError, TypeError):
            continue
        if published_dt >= min_dt:
            result.append(post)
    return result


def _build_post_prompt(post: dict) -> str:
    parts = []
    parts.append("--- POST METADATA ---")
    if post.get("group_name"):
        parts.append(f"Group: {post['group_name']}")
    if post.get("published_at"):
        parts.append(f"Published: {post['published_at']}")
    if post.get("post_url"):
        parts.append(f"URL: {post['post_url']}")
    if post.get("hashtags"):
        parts.append(f"Hashtags: {', '.join(post['hashtags'])}")
    if post.get("mentions"):
        mentions = [m.get("name", m.get("id", "")) for m in post["mentions"]]
        parts.append(f"Mentions: {', '.join(mentions)}")
    parts.append("")
    parts.append("--- POST TEXT ---")
    parts.append(post.get("text_clean", ""))
    return "\n".join(parts)


def _build_embedding_text(post: dict) -> str:
    group = post.get("group_name", "")
    text = post.get("text_clean", "")
    if group:
        return f"{group}: {text}"
    return text


def build_extractor(provider: str, openai_client: OpenAI):
    if provider == "gigachat":
        return GigaChatClient()
    if provider == "gemma":
        return GemmaClient()
    return OpenAIExtractor(openai_client)


def extract_graph_from_post(
    post: dict, extractor
) -> Optional[GraphExtractionResult]:
    text = post.get("text_clean", "")
    if not text:
        logger.warning("Post %s has empty text_clean, skipping extraction", post.get("post_id"))
        return GraphExtractionResult()

    try:
        data = extractor.extract_json(
            SYSTEM_PROMPT, _build_post_prompt(post), model=getattr(extractor, "_model", None) or None
        )
        result = GraphExtractionResult.model_validate(data)
        logger.info(
            "Extracted %d entities and %d relationships from post %s",
            len(result.entities),
            len(result.relationships),
            post.get("post_id"),
        )
        return result
    except Exception:
        logger.exception("Failed to extract graph from post %s", post.get("post_id"))
        return GraphExtractionResult()


def _merge_key(source_model: str, entity_id: str) -> str:
    return f"{source_model}::{entity_id}"


def migrate_neo4j_for_dual_model(driver) -> None:
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


def save_to_neo4j(driver, result: GraphExtractionResult, source_model: str) -> None:
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
                merge_key=_merge_key(source_model, entity.id),
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
                src_key=_merge_key(source_model, rel.source_id),
                tgt_key=_merge_key(source_model, rel.target_id),
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


def collection_for_model(model: str) -> str:
    if model == "gemma":
        return "posts_gemma"
    return "posts"


def save_to_qdrant(
    qclient: QdrantClient, post: dict, vector: list[float], collection_name: str
) -> None:
    collections = qclient.get_collections().collections
    if not any(c.name == collection_name for c in collections):
        qclient.create_collection(
            collection_name=collection_name,
            vectors_config=VectorParams(size=len(vector), distance=Distance.COSINE),
        )
        logger.info("Created Qdrant collection '%s'", collection_name)

    point = PointStruct(
        id=str(uuid.uuid5(uuid.NAMESPACE_URL, str(post.get("post_url", "")))),
        vector=vector,
        payload={
            "post_url": post.get("post_url", ""),
            "published_at": post.get("published_at", ""),
            "group_name": post.get("group_name", ""),
            "text_clean": post.get("text_clean", ""),
            "source_model": collection_name,
        },
    )
    qclient.upsert(collection_name=collection_name, points=[point])
    logger.info("Upserted post %s to Qdrant '%s'", post.get("post_id"), collection_name)


def get_indexed_post_urls(qclient: QdrantClient, collection_name: str) -> set[str]:
    collections = qclient.get_collections().collections
    if not any(c.name == collection_name for c in collections):
        return set()

    result: set[str] = set()
    offset = None
    while True:
        batch = qclient.scroll(
            collection_name=collection_name,
            limit=1000,
            offset=offset,
            with_payload=True,
            with_vectors=False,
        )
        points = batch[0]
        for point in points:
            url = point.payload.get("post_url")
            if url:
                result.add(url)
        if batch[1] is None:
            break
        offset = batch[1]
    logger.info(
        "Loaded %d already indexed post urls from Qdrant '%s'", len(result), collection_name
    )
    return result


def load_posts(jsonl_paths: list[str]) -> tuple[list[dict], list[str]]:
    posts_raw = []
    for pattern in jsonl_paths:
        if "*" in pattern or "?" in pattern:
            paths = sorted(globlib.glob(pattern))
        else:
            paths = [pattern]
        for path_str in paths:
            path = Path(path_str)
            if not path.exists():
                logger.warning("JSONL file not found: %s", path)
                continue
            with path.open(encoding="utf-8") as f:
                for line_num, line in enumerate(f, 1):
                    line = line.strip()
                    if not line:
                        continue
                    try:
                        posts_raw.append(json.loads(line))
                    except json.JSONDecodeError as e:
                        logger.warning(
                            "Skipping invalid JSON at line %d in %s: %s",
                            line_num,
                            path,
                            e,
                        )

    seen_urls: dict[str, dict] = {}
    for post in posts_raw:
        url = post.get("post_url", "")
        if url and url not in seen_urls:
            seen_urls[url] = post
    return list(seen_urls.values()), posts_raw


def process_indexer(
    jsonl_paths: list[str],
    model: str = "gigachat",
    min_date: str = "2026-01-01",
    parallel: int = 1,
) -> None:
    unique_posts, _ = load_posts(jsonl_paths)

    filtered = filter_posts(unique_posts, min_date=min_date)
    logger.info(
        "Loaded %d unique posts (by url), %d after date filter (min_date=%s)",
        len(unique_posts),
        len(filtered),
        min_date,
    )

    openai_client, neo4j_driver, qdrant_client = init_clients()
    migrate_neo4j_for_dual_model(neo4j_driver)

    collection_name = collection_for_model(model)
    indexed_urls = get_indexed_post_urls(qdrant_client, collection_name)

    to_process = [p for p in filtered if p.get("post_url") not in indexed_urls]
    logger.info(
        "Skipping %d already indexed posts, processing %d new posts (model=%s)",
        len(filtered) - len(to_process),
        len(to_process),
        model,
    )

    extractor = build_extractor(model, openai_client)
    total = 0
    errors = 0

    def process_one(post: dict) -> int:
        post_id = post.get("post_id", "unknown")
        text = post.get("text_clean", "")
        if not text:
            logger.warning("Post %s has no text content, skipping", post_id)
            return 0

        embedding_input = _build_embedding_text(post)
        embedding_response = openai_client.embeddings.create(
            model="text-embedding-3-small",
            input=embedding_input,
        )
        vector = embedding_response.data[0].embedding

        graph_result = extract_graph_from_post(post, extractor)

        save_to_neo4j(neo4j_driver, graph_result, source_model=model)

        save_to_qdrant(qdrant_client, post, vector, collection_name)

        logger.info("Processed post %s successfully", post_id)
        return 1

    if parallel > 1:
        with ThreadPoolExecutor(max_workers=parallel) as executor:
            futures = [executor.submit(process_one, p) for p in to_process]
            for future in as_completed(futures):
                try:
                    total += future.result()
                except Exception:
                    logger.exception("Error processing post in worker")
                    errors += 1
    else:
        for post in to_process:
            try:
                total += process_one(post)
            except Exception:
                logger.exception("Error processing post %s", post.get("post_id"))
                errors += 1

    neo4j_driver.close()
    logger.info(
        "Indexing complete (model=%s): %d succeeded, %d failed out of %d",
        model,
        total,
        errors,
        len(to_process),
    )


def main() -> None:
    parser = argparse.ArgumentParser(description="Index posts into Neo4j + Qdrant")
    parser.add_argument("paths", nargs="+", help="JSONL file(s) or glob patterns")
    parser.add_argument(
        "--model",
        choices=["gigachat", "gemma", "proxyapi"],
        default="gigachat",
        help="Extraction model/provider",
    )
    parser.add_argument(
        "--min-date",
        default="2026-01-01",
        help="Only posts published on/after this date (ISO). Empty = all",
    )
    parser.add_argument(
        "--parallel",
        type=int,
        default=1,
        help="Number of parallel workers (use with --model gemma)",
    )
    args = parser.parse_args()
    process_indexer(
        args.paths,
        model=args.model,
        min_date=args.min_date,
        parallel=args.parallel,
    )


if __name__ == "__main__":
    main()
