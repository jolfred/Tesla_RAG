import uuid

from qdrant_client import QdrantClient
from qdrant_client.http.models import Distance, PointStruct, VectorParams

from backend.indexer.logger import setup_indexer_logger

logger = setup_indexer_logger()


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
