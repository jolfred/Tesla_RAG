import os

from openai import OpenAI
from qdrant_client import QdrantClient

from backend.config import QDRANT_HOST, QDRANT_PORT, QDRANT_API_KEY
from backend.utils.logger import setup_logger

logger = setup_logger("vec_search")

POSTS_COLLECTION = "posts"
EMBEDDING_MODEL = "text-embedding-3-small"  # должна совпадать с индексером


class VectorSearcher:
    def __init__(self):
        self._qdrant = None
        self._openai = None

    def _get_qdrant(self) -> QdrantClient:
        if self._qdrant is None:
            api_key = os.getenv("QDRANT_API_KEY") or QDRANT_API_KEY or None
            self._qdrant = QdrantClient(host=QDRANT_HOST, port=QDRANT_PORT, api_key=api_key)
        return self._qdrant

    def _get_openai(self) -> OpenAI:
        if self._openai is None:
            self._openai = OpenAI(
                base_url=os.getenv("PROXYAPI_BASE_URL", "https://openai.api.proxyapi.ru/v1"),
                api_key=os.getenv("PROXYAPI_KEY", ""),
            )
        return self._openai

    def _embed(self, text: str) -> list[float]:
        client = self._get_openai()
        resp = client.embeddings.create(model=EMBEDDING_MODEL, input=text)
        return resp.data[0].embedding

    def search(self, query: str, top_k: int = 10, collection: str | None = None) -> list[dict]:
        qclient = self._get_qdrant()
        coll = collection or POSTS_COLLECTION
        collections = [c.name for c in qclient.get_collections().collections]
        if coll not in collections:
            logger.warning("Qdrant collection '%s' not found", coll)
            return []

        vector = self._embed(query)
        result = qclient.query_points(
            collection_name=coll,
            query=vector,
            limit=top_k,
        )
        hits = []
        for hit in result.points:
            payload = hit.payload or {}
            hits.append({
                "score": hit.score,
                "post_url": payload.get("post_url", ""),
                "published_at": payload.get("published_at", ""),
                "group_name": payload.get("group_name", ""),
                "text": payload.get("text_clean", "") or payload.get("text", ""),
                "photos": [p for p in (payload.get("photos") or [])
                           if isinstance(p, str) and p.startswith("http")],
            })
        return hits

    def count(self) -> int:
        qclient = self._get_qdrant()
        return qclient.count(POSTS_COLLECTION).count