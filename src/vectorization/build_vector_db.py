import sys
import json
import uuid  # Добавляем для уникальных ID
from pathlib import Path

# Добавляем корень проекта в пути
root_dir = Path(__file__).resolve().parent.parent.parent
sys.path.append(str(root_dir))

from sentence_transformers import SentenceTransformer
from qdrant_client import QdrantClient
from qdrant_client.models import VectorParams, Distance, PointStruct

from config import (
    CHUNKS_JSON_PATH,
    EMBEDDING_MODEL_NAME,
    VECTOR_SIZE,
    QDRANT_MODE,
    QDRANT_LOCAL_PATH,
    QDRANT_HOST,
    QDRANT_PORT,
    COLLECTION_NAME
)
from src.utils.logger import setup_logger

logger = setup_logger("vector_db_builder")

def get_qdrant_client():
    if QDRANT_MODE == "local":
        logger.info(f"Подключаемся к локальному Qdrant по пути: {QDRANT_LOCAL_PATH}")
        return QdrantClient(path=str(QDRANT_LOCAL_PATH))
    else:
        logger.info(f"Подключаемся к серверу Qdrant: {QDRANT_HOST}:{QDRANT_PORT}")
        return QdrantClient(host=QDRANT_HOST, port=QDRANT_PORT)

def recreate_collection(client: QdrantClient):
    """Принудительно пересоздает коллекцию, чтобы избежать каши и дублей."""
    collections_response = client.get_collections()
    existing_collections = [col.name for col in collections_response.collections]

    if COLLECTION_NAME in existing_collections:
        logger.info(f"Удаляем старую коллекцию '{COLLECTION_NAME}' для чистой перезаписи...")
        client.delete_collection(collection_name=COLLECTION_NAME)
        
    logger.info(f"Создаем чистую коллекцию '{COLLECTION_NAME}'...")
    client.create_collection(
        collection_name=COLLECTION_NAME,
        vectors_config=VectorParams(
            size=VECTOR_SIZE, 
            distance=Distance.COSINE
        )
    )

def upload_chunks_to_qdrant():
    if not CHUNKS_JSON_PATH.exists():
        logger.error(f"Файл {CHUNKS_JSON_PATH} не найден. Сначала запусти пайплайн нарезки.")
        return

    logger.info("Загружаем чанки из файла...")
    with open(CHUNKS_JSON_PATH, 'r', encoding='utf-8') as f:
        chunks = json.load(f)

    if not chunks:
        logger.warning("Файл с чанками пуст.")
        return

    logger.info(f"Загружаем AI-модель: {EMBEDDING_MODEL_NAME}...")
    # Префикс 'query: ' или 'passage: ' помогает некоторым моделям лучше сопоставлять длины,
    # но для rubert-tiny2 мы используем нормализацию векторов под капотом.
    model = SentenceTransformer(EMBEDDING_MODEL_NAME)
    
    client = get_qdrant_client()
    recreate_collection(client)  # <-- ТЕПЕРЬ СБРАСЫВАЕМ СТАРУЮ БАЗУ

    logger.info(f"Начинаем векторизацию {len(chunks)} чанков...")
    texts = [chunk["text"] for chunk in chunks]
    
    # normalize_embeddings=True заставляет векторы быть одной длины,
    # значительно повышая точность косинусного сходства (Cosine Similarity)
    embeddings = model.encode(texts, show_progress_bar=True, normalize_embeddings=True)

    points = []
    for chunk, vector in zip(chunks, embeddings):
        # Генерируем случайный, гарантированно уникальный UUID для каждой точки!
        chunk_id = str(uuid.uuid4())
        
        points.append(PointStruct(
            id=chunk_id,  # <-- ТЕПЕРЬ СЮДА ПИШЕТСЯ СТРОКА UUID, А НЕ ИНДЕКС
            vector=vector.tolist(),
            payload={               
                "source": chunk["source"],
                "text": chunk["text"],
                "chunk_index": chunk["chunk_index"]
            }
        ))

    logger.info(f"Загружаем {len(points)} уникальных векторов в базу Qdrant...")
    client.upload_points(
        collection_name=COLLECTION_NAME,
        points=points
    )
    
    logger.info("Векторизация успешно завершена! База полностью обновлена.")

if __name__ == "__main__":
    upload_chunks_to_qdrant()