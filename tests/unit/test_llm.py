import pytest
from unittest.mock import patch
from src.llm.client import LLMClient

@patch.object(LLMClient, '_send_to_model')
def test_llm_client_prompt_building(mock_send_to_model):
    """
    Тест: проверяем, что LLMClient правильно склеивает найденные тексты
    с вопросом пользователя и передает этот промпт в модель.
    """
    # 1. ПОДГОТОВКА
    # Имитируем ответ от нейросети
    mock_send_to_model.return_value = "Маск основал SpaceX в 2002 году."
    
    # Фейковые результаты из нашего векторного поиска
    fake_search_results = [
        {"score": 0.95, "source": "doc1.txt", "text": "Илон Маск основал SpaceX в 2002 году."},
        {"score": 0.85, "source": "doc2.txt", "text": "SpaceX строит ракеты Falcon."}
    ]
    
    # Инициализируем нашего клиента
    llm = LLMClient()

    # 2. ДЕЙСТВИЕ
    # Запрашиваем ответ на основе вопроса и контекста
    answer = llm.generate_answer(
        query="Что строит SpaceX?", 
        context_chunks=fake_search_results
    )

    # 3. ПРОВЕРКИ
    assert answer == "Маск основал SpaceX в 2002 году.", "LLMClient не вернул ответ от модели!"
    
    # Проверяем, что метод вызова модели был вызван 1 раз
    mock_send_to_model.assert_called_once()
    
    # Получаем промпт, который наш код попытался отправить в LLM
    generated_prompt = mock_send_to_model.call_args[0][0]
    
    # Промпт ОБЯЗАН содержать и вопрос пользователя, и куски текста из контекста
    assert "Что строит SpaceX?" in generated_prompt, "В промпте нет вопроса пользователя!"
    assert "Илон Маск основал SpaceX в 2002 году." in generated_prompt, "В промпте нет первого контекста!"
    assert "SpaceX строит ракеты Falcon." in generated_prompt, "В промпте нет второго контекста!"