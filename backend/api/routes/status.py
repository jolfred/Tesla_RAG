import os
from pathlib import Path
from fastapi import APIRouter
from backend.config import DOCUMENTS_DIR
from backend.api.schemas.common import StatusResponse
from backend.embeddings import qdrant_client as qdrant
from backend.graph.graph_builder import GraphBuilder
from backend.utils.logger import setup_logger

logger = setup_logger("status_route")

router = APIRouter()


@router.get("/api/v1/status", response_model=StatusResponse)
async def status():
    errors = []
    qdrant_points = 0
    neo4j_stats = {"total_nodes": 0, "total_relations": 0}

    # Qdrant
    try:
        qdrant_points = qdrant.count_points()
    except Exception as e:
        errors.append(f"Qdrant: {e}")

    # Neo4j
    try:
        graph = GraphBuilder()
        neo4j_stats = graph.get_stats()
        graph.close()
    except Exception as e:
        errors.append(f"Neo4j: {e}")

    # Documents
    doc_count = 0
    if DOCUMENTS_DIR.exists():
        doc_count = len([f for f in os.listdir(DOCUMENTS_DIR)
                        if os.path.isfile(os.path.join(DOCUMENTS_DIR, f))
                        and not f.startswith(".")])

    # Ollama
    ollama_ok = False
    try:
        from openai import OpenAI
        from backend.config import OLLAMA_BASE_URL, OLLAMA_MODEL
        client = OpenAI(base_url=OLLAMA_BASE_URL.rstrip("/") + "/v1", api_key="ollama")
        models = client.models.list()
        ollama_ok = any(OLLAMA_MODEL.split(":")[0] in m.id for m in models)
    except Exception:
        ollama_ok = False

    return StatusResponse(
        status="ok" if not errors else "degraded",
        qdrant_points=qdrant_points,
        neo4j_nodes=neo4j_stats["total_nodes"],
        neo4j_relations=neo4j_stats["total_relations"],
        documents_count=doc_count,
        ollama_available=ollama_ok,
        errors=errors,
    )
