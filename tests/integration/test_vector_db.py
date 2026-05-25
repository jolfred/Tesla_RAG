import json
import numpy as np
from unittest.mock import patch
from src.vectorization.build_vector_db import upload_chunks_to_qdrant

# Создаем фейковую нейросеть для тестов, чтобы не грузить процессор
class FakeModel:
    def __init__(self, model_name=None):
        pass
        
    def encode(self, texts, **kwargs):
        # Возвращаем фейковые векторы нужного размера (312 для rubert-tiny2)
        res = []
        for _ in texts:
            vec = np.zeros(312, dtype=np.float32)
            vec[0] = 0.9  # Просто какое-то число для имитации данных
            res.append(vec)
        return np.array(res)

def test_upload_chunks_to_qdrant(tmp_path):
    """Тест: проверяем только загрузку чанков в локальную базу Qdrant."""
    
    # 1. Создаем фейковый файл с чанками во временной папке
    chunks_path = tmp_path / "chunks.json"
    fake_chunks = [
        {"source": "doc1.txt", "chunk_index": 0, "text": "Илон Маск основал SpaceX."},
        {"source": "doc2.txt", "chunk_index": 0, "text": "Сегодня отличная погода."}
    ]
    with open(chunks_path, 'w', encoding='utf-8') as f:
        json.dump(fake_chunks, f)

    # Указываем временную папку для базы
    qdrant_path = tmp_path / "qdrant_db"

    # 2. Подменяем пути и саму нейросеть на нашу FakeModel
    with patch("src.vectorization.build_vector_db.CHUNKS_JSON_PATH", chunks_path), \
         patch("src.vectorization.build_vector_db.QDRANT_LOCAL_PATH", qdrant_path), \
         patch("src.vectorization.build_vector_db.SentenceTransformer", return_value=FakeModel()):

        # Запускаем функцию сборки базы
        upload_chunks_to_qdrant()

        # 3. Проверки
        # Проверяем, что папка базы создалась
        assert qdrant_path.exists(), "Папка с базой Qdrant не создалась!"
        
        # Проверяем, что папка не пустая (Qdrant создал там свои служебные файлы)
        assert any(qdrant_path.iterdir()), "База Qdrant пустая, данные не сохранились!"