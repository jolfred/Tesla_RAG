"""Индексация в namespace проекта: имена веток + документы как псевдо-посты."""

from __future__ import annotations

import json
from datetime import datetime, timezone
from pathlib import Path

from backend.admin.db import get_connection
from backend.config import BASE_DIR, DOCUMENTS_DIR
from backend.utils.logger import setup_logger

logger = setup_logger("admin_indexing")

POSTS_DIR = BASE_DIR / "storage" / "posts"
DOC_TEXT_CAP = 8000


def project_source_model(slug: str) -> str:
    return f"proj_{slug}"


def project_collection(slug: str) -> str:
    return f"posts_proj_{slug}"


def project_composition(slug: str) -> dict:
    """Состав проекта: vk_group-домены + doc_id."""
    conn = get_connection()
    try:
        rows = conn.execute(
            "SELECT item_type, item_id FROM project_items WHERE project_slug = ?",
            (slug,),
        ).fetchall()
    finally:
        conn.close()
    groups = sorted({r["item_id"] for r in rows if r["item_type"] == "vk_group"})
    docs = sorted({r["item_id"] for r in rows if r["item_type"] == "doc"})
    return {"vk_groups": groups, "docs": docs}


def project_posts_paths(slug: str) -> list[str]:
    paths = []
    for domain in project_composition(slug)["vk_groups"]:
        p = POSTS_DIR / f"posts_{domain}.jsonl"
        if p.exists():
            paths.append(str(p))
        else:
            logger.warning("No posts file for group %s (project %s)", domain, slug)
    return paths


def _doc_text(path: Path) -> str:
    ext = path.suffix.lower()
    if ext == ".txt":
        return path.read_text(encoding="utf-8", errors="replace")
    if ext == ".json":
        try:
            data = json.loads(path.read_text(encoding="utf-8", errors="replace"))
        except Exception:
            return ""
        if isinstance(data, dict):
            for key in ("text", "content", "body", "description"):
                val = data.get(key)
                if isinstance(val, str) and val.strip():
                    return val
        return ""
    return ""


def load_doc_posts(doc_ids: list[str]) -> list[dict]:
    """Документы -> псевдо-посты для process_indexer (только txt/json)."""
    posts = []
    for doc_id in doc_ids:
        matches = sorted(DOCUMENTS_DIR.glob(f"{doc_id}.*"))
        if not matches:
            logger.warning("Document file not found: %s", doc_id)
            continue
        path = matches[0]
        text = _doc_text(path).strip()
        if not text:
            logger.warning("Document %s has no indexable text, skipping", doc_id)
            continue
        if len(text) > DOC_TEXT_CAP:
            logger.info("Document %s truncated to %d chars", doc_id, DOC_TEXT_CAP)
            text = text[:DOC_TEXT_CAP]
        mtime = datetime.fromtimestamp(path.stat().st_mtime, tz=timezone.utc)
        posts.append(
            {
                "post_id": f"doc_{doc_id}",
                "post_url": f"doc://{doc_id}",
                "published_at": mtime.isoformat(),
                "group_name": f"Документ: {path.name}",
                "text_clean": text,
                "hashtags": [],
                "mentions": [],
                "attachments": {},
            }
        )
    return posts


def project_stats(slug: str) -> dict:
    """Счётчики namespace проекта (best-effort, без падений)."""
    out: dict = {
        "source_model": project_source_model(slug),
        "collection": project_collection(slug),
        "neo4j_nodes": 0,
        "neo4j_relations": 0,
        "qdrant_points": 0,
        "error": "",
    }
    try:
        from neo4j import GraphDatabase

        from backend.config import NEO4J_PASS, NEO4J_URI, NEO4J_USER

        driver = GraphDatabase.driver(
            NEO4J_URI,
            auth=(NEO4J_USER, NEO4J_PASS),
            connection_timeout=3,
            max_transaction_retry_time=5,
        )
        try:
            with driver.session() as session:
                rec = session.run(
                    "MATCH (n) WHERE n.source_model = $m RETURN count(n) AS c",
                    m=out["source_model"],
                ).single()
                out["neo4j_nodes"] = rec["c"] if rec else 0
                rec = session.run(
                    "MATCH (a)-[r]->(b) WHERE a.source_model = $m OR b.source_model = $m "
                    "RETURN count(r) AS c",
                    m=out["source_model"],
                ).single()
                out["neo4j_relations"] = rec["c"] if rec else 0
        finally:
            driver.close()
    except Exception as e:
        out["error"] = f"Neo4j: {e}"
    try:
        from qdrant_client import QdrantClient

        from backend.config import QDRANT_API_KEY, QDRANT_HOST, QDRANT_PORT

        qc = QdrantClient(
            host=QDRANT_HOST, port=QDRANT_PORT, api_key=QDRANT_API_KEY or None
        )
        names = [c.name for c in qc.get_collections().collections]
        if out["collection"] in names:
            out["qdrant_points"] = qc.count(out["collection"]).count
    except Exception as e:
        out["error"] = (out["error"] + f" Qdrant: {e}").strip()
    return out
