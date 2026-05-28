import pytest
import numpy as np
from unittest.mock import patch, MagicMock
from src.vectorization.searcher import Searcher

@patch("src.vectorization.searcher.SentenceTransformer")
@patch("src.vectorization.searcher.QdrantClient")
def test_semantic_search_top_k(mock_qdrant_class, mock_transformer_class):
    """
    Тест: проверяем, что ядро поиска корректно кодирует запрос,
    передает правильные параметры (Top-K) в Qdrant и форматирует ответ.
    """
    # 1. ПОДГОТОВКА (Mocks)
    mock_model = MagicMock()
    mock_model.encode.return_value = np.array([0.1, 0.2, 0.3], dtype=np.float32)
    mock_transformer_class.return_value = mock_model

    mock_qdrant = MagicMock()
    
    fake_hit_1 = MagicMock()
    fake_hit_1.score = 0.95
    fake_hit_1.payload = {"source": "doc1.txt", "text": "Первый ответ"}
    
    fake_hit_2 = MagicMock()
    fake_hit_2.score = 0.82
    fake_hit_2.payload = {"source": "doc2.txt", "text": "Второй ответ"}
    
    mock_qdrant.search.return_value = [fake_hit_1, fake_hit_2]
    mock_qdrant_class.return_value = mock_qdrant

    # 2. ДЕЙСТВИЕ
    searcher = Searcher()
    results = searcher.search(query="Тестовый запрос", top_k=2)

    # 3. ПРОВЕРКИ
    mock_model.encode.assert_called_once_with("Тестовый запрос")
    
    mock_qdrant.search.assert_called_once()
    call_args = mock_qdrant.search.call_args[1]
    
    assert call_args["limit"] == 2, "Параметр top_k не передался в Qdrant как limit!"
    
    # === ИСПОЛЬЗУЕМ pytest.approx ДЛЯ ИГНОРИРОВАНИЯ ПОГРЕШНОСТИ МАТЕМАТИКИ ===
    assert call_args["query_vector"] == pytest.approx([0.1, 0.2, 0.3]), "Вектор запроса передан неверно!"
    
    assert len(results) == 2
    assert results[0]["score"] == 0.95
    assert results[0]["source"] == "doc1.txt"
    assert results[1]["text"] == "Второй ответ"