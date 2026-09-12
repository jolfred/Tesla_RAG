import argparse
from concurrent.futures import ThreadPoolExecutor, as_completed
from typing import Optional

from dotenv import load_dotenv
from neo4j import GraphDatabase
from openai import OpenAI
from qdrant_client import QdrantClient

from backend.indexer.clients import init_clients
from backend.indexer.extractors import (
    OpenAIExtractor,
    build_extractor,
    extract_graph_from_post,
)
from backend.indexer.logger import setup_indexer_logger
from backend.indexer.neo4j_writer import (
    merge_key as _merge_key,
    migrate_neo4j_for_dual_model,
    save_to_neo4j,
)
from backend.indexer.posts import (
    build_embedding_text,
    filter_posts,
    load_posts,
    parse_dt as _parse_dt,
)
from backend.indexer.prompts import SYSTEM_PROMPT, build_post_prompt as _build_post_prompt
from backend.indexer.qdrant_writer import (
    collection_for_model,
    get_indexed_post_urls,
    save_to_qdrant,
)
from backend.indexer.schemas import GraphExtractionResult

load_dotenv()

logger = setup_indexer_logger()

__all__ = [
    "SYSTEM_PROMPT",
    "OpenAIExtractor",
    "build_extractor",
    "extract_graph_from_post",
    "init_clients",
    "filter_posts",
    "load_posts",
    "migrate_neo4j_for_dual_model",
    "save_to_neo4j",
    "save_to_qdrant",
    "get_indexed_post_urls",
    "collection_for_model",
    "process_indexer",
    "main",
]


def process_indexer(
    jsonl_paths: list[str],
    model: str = "gigachat",
    min_date: str = "2026-01-01",
    parallel: int = 1,
    extractor: str = "legacy",
    force: bool = False,
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
    if force and extractor == "transformer":
        # Resume поверх --force: пропускаем посты, чей :Post уже в v2-ветке.
        from backend.indexer.graph_schema_v2 import SOURCE_MODEL_V2
        from backend.indexer.neo4j_writer_v2 import get_indexed_post_urls_v2

        graph_urls = get_indexed_post_urls_v2(neo4j_driver, SOURCE_MODEL_V2)
        to_process = [p for p in filtered if p.get("post_url") not in graph_urls]
        logger.info(
            "Force+transformer: %d posts already in graph branch '%s', "
            "processing %d remaining (model=%s)",
            len(filtered) - len(to_process),
            SOURCE_MODEL_V2,
            len(to_process),
            model,
        )
    elif force:
        to_process = list(filtered)
        logger.info(
            "Force mode: processing all %d filtered posts (model=%s, extractor=%s)",
            len(to_process),
            model,
            extractor,
        )
    else:
        indexed_urls = get_indexed_post_urls(qdrant_client, collection_name)

        to_process = [p for p in filtered if p.get("post_url") not in indexed_urls]
        logger.info(
            "Skipping %d already indexed posts, processing %d new posts (model=%s)",
            len(filtered) - len(to_process),
            len(to_process),
            model,
        )

    extractor_obj = build_extractor(model, openai_client)
    transformer = None
    if extractor == "transformer":
        from backend.indexer.graph_schema_v2 import SOURCE_MODEL_V2
        from backend.indexer.graph_transformer import build_llm, build_transformer

        transformer = build_transformer(build_llm(model))
        logger.info("Using LLMGraphTransformer (model=%s)", model)
    total = 0
    errors = 0

    def process_one(post: dict) -> int:
        post_id = post.get("post_id", "unknown")
        text = post.get("text_clean", "")
        if not text:
            logger.warning("Post %s has no text content, skipping", post_id)
            return 0

        embedding_response = openai_client.embeddings.create(
            model="text-embedding-3-small",
            input=build_embedding_text(post),
        )
        vector = embedding_response.data[0].embedding

        if transformer is not None:
            from backend.indexer.graph_transformer import (
                extract_from_documents,
                posts_to_documents,
            )
            from backend.indexer.neo4j_writer_v2 import sanitize_graph, save_graph_v2

            docs = posts_to_documents([post])
            if not docs:
                return 0
            for meta, nodes, rels in extract_from_documents(transformer, docs):
                clean_nodes, clean_rels = sanitize_graph(nodes, rels)
                save_graph_v2(
                    neo4j_driver,
                    clean_nodes,
                    clean_rels,
                    source_model=SOURCE_MODEL_V2,
                    post_url=meta.get("post_url") or post.get("post_url"),
                    post_date=meta.get("published_at") or post.get("published_at"),
                    group_name=meta.get("group_name") or post.get("group_name"),
                )
        else:
            graph_result = extract_graph_from_post(post, extractor_obj)

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
    parser.add_argument(
        "--extractor",
        choices=["legacy", "transformer"],
        default="legacy",
        help="Graph extraction engine: legacy JSON prompt or LLMGraphTransformer (v2)",
    )
    parser.add_argument(
        "--force",
        action="store_true",
        help="Reprocess all filtered posts even if already in Qdrant "
        "(Qdrant upsert is idempotent; needed for graph reindex pilots)",
    )
    args = parser.parse_args()
    process_indexer(
        args.paths,
        model=args.model,
        min_date=args.min_date,
        parallel=args.parallel,
        extractor=args.extractor,
        force=args.force,
    )


if __name__ == "__main__":
    main()
