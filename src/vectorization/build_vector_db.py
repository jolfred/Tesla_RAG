import sys
import json
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
    """Возвращает клиент Qdrant в зависимости от настроек конфига."""
    if QDRANT_MODE == "local":
        logger.info(f"Подключаемся к локальному Qdrant по пути: {QDRANT_LOCAL_PATH}")
        return QdrantClient(path=str(QDRANT_LOCAL_PATH))
    else:
        logger.info(f"Подключаемся к серверу Qdrant: {QDRANT_HOST}:{QDRANT_PORT}")
        return QdrantClient(host=QDRANT_HOST, port=QDRANT_PORT)

def create_collection_if_not_exists(client: QdrantClient):
    """Создает коллекцию (таблицу) в базе, если её там еще нет."""
    collections_response = client.get_collections()
    existing_collections = [col.name for col in collections_response.collections]

    if COLLECTION_NAME not in existing_collections:
        logger.info(f"Создаем новую коллекцию '{COLLECTION_NAME}'...")
        client.create_collection(
            collection_name=COLLECTION_NAME,
            vectors_config=VectorParams(
                size=VECTOR_SIZE, 
                distance=Distance.COSINE # Косинусное расстояние отлично подходит для текстов
            )
        )
    else:
        logger.info(f"Коллекция '{COLLECTION_NAME}' уже существует.")

def upload_chunks_to_qdrant():
    """Основная функция: читает чанки, делает векторы и грузит в Qdrant."""
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
    model = SentenceTransformer(EMBEDDING_MODEL_NAME)
    
    client = get_qdrant_client()
    create_collection_if_not_exists(client)

    logger.info(f"Начинаем векторизацию {len(chunks)} чанков. Это может занять время...")
    
    # Извлекаем только тексты для нейросети
    texts = [chunk["text"] for chunk in chunks]
    
    # Нейросеть превращает список текстов в список векторов (чисел)
    embeddings = model.encode(texts, show_progress_bar=True)

    # Формируем точки (points) для загрузки в Qdrant
    points = []
    for idx, (chunk, vector) in enumerate(zip(chunks, embeddings)):
        points.append(PointStruct(
            id=idx, # Уникальный ID чанка
            vector=vector.tolist(), # Вектор
            payload={               # Полезная нагрузка (чтобы потом показать пользователю)
                "source": chunk["source"],
                "text": chunk["text"],
                "chunk_index": chunk["chunk_index"]
            }
        ))

    logger.info("Загружаем векторы в базу Qdrant...")
    # Загружаем пачками (batch) для оптимизации
    client.upload_points(
        collection_name=COLLECTION_NAME,
        points=points
    )
    
    logger.info("Векторизация успешно завершена! База готова к поиску.")

if __name__ == "__main__":
    upload_chunks_to_qdrant()