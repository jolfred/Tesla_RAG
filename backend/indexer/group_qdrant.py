"""Карточки VK-групп в Qdrant (коллекция posts)."""

import uuid

from qdrant_client import QdrantClient
from qdrant_client.http.models import Distance, PointStruct, VectorParams

from backend.indexer.group_meta import GROUP_SOURCE_PREFIX, group_card_text, today
from backend.indexer.logger import setup_indexer_logger

logger = setup_indexer_logger()

QDRANT_COLLECTION = "posts"


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
            "published_at": today(),
            "group_name": meta.get("name", ""),
            "text_clean": group_card_text(meta),
        },
    )
    qclient.upsert(collection_name=QDRANT_COLLECTION, points=[point])
    logger.info("Upserted group card %s to Qdrant", post_url)
