import json
import os
import uuid as uuid_lib
from pathlib import Path

from backend.config import DOCUMENTS_DIR, CHUNK_SIZE, CHUNK_OVERLAP
from backend.utils.chunker import split_text
from backend.utils.logger import setup_logger
from backend.rag.preprocessing.text_cleaner import clean_text
from backend.rag.loaders.load_file import load_file
from backend.graph.entity_extractor import EntityExtractor
from backend.graph.graph_builder import GraphBuilder

logger = setup_logger("pipeline")

REGISTRY_PATH = Path(__file__).resolve().parent.parent.parent / "storage" / "file_registry.json"


def _load_registry() -> dict:
    if REGISTRY_PATH.exists():
        with open(REGISTRY_PATH, "r", encoding="utf-8") as f:
            return json.load(f)
    return {}


def _save_registry(registry: dict):
    REGISTRY_PATH.parent.mkdir(parents=True, exist_ok=True)
    with open(REGISTRY_PATH, "w", encoding="utf-8") as f:
        json.dump(registry, f, ensure_ascii=False, indent=2)


def _file_hash(file_path: str) -> str:
    import hashlib
    h = hashlib.md5()
    with open(file_path, "rb") as f:
        for block in iter(lambda: f.read(65536), b""):
            h.update(block)
    return h.hexdigest()


def process_document(file_path: str, builder: GraphBuilder = None, extractor: EntityExtractor = None) -> dict:
    name = os.path.basename(file_path)
    registry = _load_registry()
    fhash = _file_hash(file_path)

    if registry.get(name) == fhash:
        return {"status": "skipped", "reason": "unchanged"}

    content = load_file(file_path)
    if not content:
        return {"status": "error", "error": "failed to extract text"}

    cleaned = clean_text(content)
    chunks_text = split_text(cleaned, size=CHUNK_SIZE, overlap=CHUNK_OVERLAP)

    ext = Path(file_path).suffix.lower()
    is_json = ext == ".json"
    meta = {}
    pub_id = None

    if is_json:
        meta = parse_publication_meta(file_path) or {}
        pub_id = meta.get("id", name)

    source_name = meta.get("title") or meta.get("source") or name

    chunks = []
    for i, text in enumerate(chunks_text):
        chunks.append({
            "source": source_name,
            "chunk_index": i,
            "text": text,
            "type": meta.get("type", "document"),
            "title": meta.get("title", ""),
            "date": meta.get("date", ""),
            "url": meta.get("url", ""),
        })

    # Entity extraction + graph (full text once, not per-chunk)
    if builder and extractor and len(cleaned) > 20:
        try:
            extraction = extractor.extract(cleaned, source=source_name)
            if extraction.get("entities"):
                builder.build_from_extraction(extraction)
        except Exception as e:
            logger.warning(f"Extraction failed for '{source_name}': {e}")

    # Update registry
    registry[name] = fhash
    _save_registry(registry)

    return {
        "status": "processed",
        "chunks": len(chunks),
        "source": source_name,
        "document_id": pub_id or str(uuid_lib.uuid4()),
    }


def process_all_documents() -> dict:
    DOCUMENTS_DIR.mkdir(parents=True, exist_ok=True)
    processed = []
    errors = []

    # Init GraphBuilder + EntityExtractor once for all files
    builder = None
    extractor = None
    try:
        builder = GraphBuilder()
        builder.search_cypher("RETURN 1 AS ok")
        builder.create_constraints()
        extractor = EntityExtractor()
        logger.info("Neo4j connected, graph extraction enabled")
    except Exception as e:
        logger.warning(f"Neo4j unavailable, skipping graph: {e}")

    for fname in sorted(os.listdir(DOCUMENTS_DIR)):
        if fname.startswith("."):
            continue
        fpath = os.path.join(DOCUMENTS_DIR, fname)
        if not os.path.isfile(fpath):
            continue

        ext = Path(fname).suffix.lower()
        if ext not in (".pdf", ".docx", ".txt", ".json"):
            continue

        result = process_document(fpath, builder, extractor)
        if result["status"] == "error":
            errors.append({"file": fname, "error": result["error"]})
        elif result["status"] == "processed":
            processed.append({"file": fname, "chunks": result["chunks"]})

    if builder:
        builder.close()

    return {
        "processed": processed,
        "errors": errors,
        "total_processed": len(processed),
        "total_errors": len(errors),
    }
