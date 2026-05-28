import pytest
from unittest.mock import patch, MagicMock
from src.llm.client import LLMClient

# Мы "мокаем" (имитируем) и поиск, и нейросеть, чтобы тест был быстрым и бесплатным
@patch('src.vectorization.searcher.Searcher')
@patch('src.llm.base_provider.BaseLLMProvider')
def test_end_to_end_rag_flow(MockProvider, MockSearcher):
    """
    Тест проверяет всю цепочку: Вопрос -> Поиск -> Передача чанков -> Ответ
    """
    # 1. ПОДГОТОВКА (Настраиваем фейковый поиск)
    mock_searcher_instance = MockSearcher.return_value
    # Имитируем, что Qdrant нашел 2 чанка текста
    fake_chunks = [
        {"score": 0.95, "text": "В компании Tesla работают инженеры."},
        {"score": 0.88, "text": "Tesla производит электромобили."}
    ]
    mock_searcher_instance.search.return_value = fake_chunks

    # Настраиваем фейковую нейросеть
    mock_llm_instance = MockProvider.return_value
    # Имитируем, что нейросеть прочитала чанки и выдала красивый ответ
    mock_llm_instance.generate.return_value = "Tesla производит электромобили силами инженеров."

    # 2. ДЕЙСТВИЕ (Запускаем наш пайплайн)
    query = "Кто работает в Tesla и что они делают?"
    
    # Шаг поиска
    found_chunks = mock_searcher_instance.search(query=query, top_k=2)
    
    # Шаг генерации
    client = LLMClient(provider=mock_llm_instance)
    answer = client.generate_answer(query=query, context_chunks=found_chunks)

    # 3. ПРОВЕРКИ
    # Проверяем, что поиск вернул именно наши чанки
    assert len(found_chunks) == 2
    assert found_chunks[0]["text"] == "В компании Tesla работают инженеры."

    # Проверяем, что клиент отдал правильный финальный ответ
    assert answer == "Tesla производит электромобили силами инженеров."

    # САМОЕ ВАЖНОЕ: Проверяем, что в промпт для LLM попали тексты из чанков
    generated_prompt = mock_llm_instance.generate.call_args[0][0]
    assert "В компании Tesla работают инженеры." in generated_prompt, "Первый чанк не попал в промпт!"
    assert "Tesla производит электромобили." in generated_prompt, "Второй чанк не попал в промпт!"