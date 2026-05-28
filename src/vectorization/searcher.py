import sys
from pathlib import Path

# Добавляем корень проекта в пути
root_dir = Path(__file__).resolve().parent.parent.parent
sys.path.append(str(root_dir))

from sentence_transformers import SentenceTransformer
from qdrant_client import QdrantClient

from config import (
    EMBEDDING_MODEL_NAME,
    QDRANT_MODE,
    QDRANT_LOCAL_PATH,
    QDRANT_HOST,
    QDRANT_PORT,
    COLLECTION_NAME
)
from src.utils.logger import setup_logger

logger = setup_logger("semantic_search")

class Searcher:
    def __init__(self):
        logger.info(f"Загрузка модели {EMBEDDING_MODEL_NAME} для поиска...")
        self.model = SentenceTransformer(EMBEDDING_MODEL_NAME)
        
        if QDRANT_MODE == "local":
            self.client = QdrantClient(path=str(QDRANT_LOCAL_PATH))
        else:
            self.client = QdrantClient(host=QDRANT_HOST, port=QDRANT_PORT)
            
    def search(self, query: str, top_k: int = 3):
        """Ищет наиболее подходящие фрагменты текста по смыслу запроса."""
        logger.info(f"Ищем ответ на запрос: '{query}'")
        
        # 1. Превращаем текстовый запрос пользователя в вектор
        query_vector = self.model.encode(query).tolist()
        
        # 2. Ищем ближайшие векторы в базе Qdrant COLLECTION_NAME
        search_result = self.client.query_points(
            collection_name=COLLECTION_NAME,
            query=query_vector,
            limit=top_k  # Сколько результатов вернуть (Top-K)
        )
        
        # 3. Красиво форматируем результат
        results = []
        for hit in search_result.points: # <-- Исправлено здесь
            payload = hit.payload or {}
            results.append({
                "score": round(hit.score, 3), 
                "source": payload.get("source", "Неизвестен"),
                "text": payload.get("text", "")
            })
            
        return results

# Блок для ручного тестирования
if __name__ == "__main__":
    searcher = Searcher()
    
    print("\n" + "="*50)
    print("Векторный поиск готов! Введи свой запрос (или 'exit' для выхода).")
    print("="*50)
    
    while True:
        user_query = input("\nТвой вопрос: ")
        if user_query.lower() in ['exit', 'выход', 'quit']:
            break
            
        if not user_query.strip():
            continue
            
        # Ищем топ-3 ответа
        answers = searcher.search(user_query, top_k=10)
        
        print("\n--- РЕЗУЛЬТАТЫ ПОИСКА ---")
        for i, ans in enumerate(answers, 1):
            print(f"\n[{i}] Точность: {ans['score']} | Источник: {ans['source']}")
            print(f"Текст: {ans['text']}")