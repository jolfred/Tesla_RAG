import uuid
from qdrant_client import QdrantClient as QClient
from qdrant_client.models import VectorParams, Distance, PointStruct, Filter, FieldCondition, MatchValue
from backend.config import (
    QDRANT_MODE, QDRANT_LOCAL_PATH, QDRANT_HOST, QDRANT_PORT,
    COLLECTION_NAME, VECTOR_SIZE,
)
from backend.embeddings.model import embed_texts, embed_query
from backend.utils.logger import setup_logger

logger = setup_logger("qdrant_client")


def get_client() -> QClient:
    if QDRANT_MODE == "local":
        return QClient(path=str(QDRANT_LOCAL_PATH))
    return QClient(host=QDRANT_HOST, port=QDRANT_PORT)


def ensure_collection():
    client = get_client()
    collections = client.get_collections().collections
    names = [c.name for c in collections]
    if COLLECTION_NAME not in names:
        logger.info(f"Creating collection '{COLLECTION_NAME}' with size {VECTOR_SIZE}")
        client.create_collection(
            collection_name=COLLECTION_NAME,
            vectors_config=VectorParams(size=VECTOR_SIZE, distance=Distance.COSINE),
        )
    return client


def upload_chunks(chunks: list[dict]):
    if not chunks:
        return

    client = ensure_collection()
    texts = [c["text"] for c in chunks]
    vectors = embed_texts(texts)

    scroll_result = client.scroll(
        collection_name=COLLECTION_NAME,
        limit=100000,
        with_payload=["source", "chunk_index"],
    )
    existing = {(p.payload.get("source"), p.payload.get("chunk_index")) for p in scroll_result[0]}

    points = []
    for chunk, vector in zip(chunks, vectors):
        key = (chunk.get("source"), chunk.get("chunk_index"))
        if key in existing:
            continue
        points.append(PointStruct(
            id=str(uuid.uuid4()),
            vector=vector,
            payload={
                "source": chunk.get("source", ""),
                "text": chunk.get("text", ""),
                "chunk_index": chunk.get("chunk_index", 0),
                "type": chunk.get("type", "publication"),
                "title": chunk.get("title", ""),
                "date": chunk.get("date", ""),
                "url": chunk.get("url", ""),
            },
        ))

    if points:
        client.upload_points(collection_name=COLLECTION_NAME, points=points)
        logger.info(f"Uploaded {len(points)} new points to Qdrant")
    else:
        logger.info("No new points to upload")


def search(query: str, top_k: int = 10, source_filter: str = None) -> list[dict]:
    client = ensure_collection()
    query_vector = embed_query(query)

    search_filter = None
    if source_filter:
        search_filter = Filter(
            must=[FieldCondition(key="source", match=MatchValue(value=source_filter))]
        )

    result = client.query_points(
        collection_name=COLLECTION_NAME,
        query=query_vector,
        query_filter=search_filter,
        limit=top_k,
    )
    return [
        {
            "score": hit.score,
            "source": hit.payload.get("source", ""),
            "text": hit.payload.get("text", ""),
            "type": hit.payload.get("type", "publication"),
            "title": hit.payload.get("title", ""),
            "date": hit.payload.get("date", ""),
            "url": hit.payload.get("url", ""),
            "chunk_index": hit.payload.get("chunk_index", 0),
        }
        for hit in result.points
    ]


def count_points() -> int:
    client = ensure_collection()
    result = client.count(collection_name=COLLECTION_NAME)
    return result.count
