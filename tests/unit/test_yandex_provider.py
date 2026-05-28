import os
import pytest
from unittest.mock import patch, Mock

# Фикстура для имитации переменных окружения (.env)
# Это нужно, чтобы тест не падал, если на сервере тестирования нет реального .env файла
@pytest.fixture
def mock_env():
    with patch.dict(os.environ, {"YANDEX_API_KEY": "fake_key", "YANDEX_FOLDER_ID": "fake_folder"}):
        yield

# Тест 1: Успешный запрос к Яндексу
@patch("src.llm.yandex_provider.requests.post")
def test_yandex_provider_success(mock_post, mock_env):
    # Импортируем провайдер внутри теста, чтобы фикстура mock_env успела сработать
    from src.llm.yandex_provider import YandexGPTProvider
    
    # 1. ПОДГОТОВКА (Настраиваем фейковый ответ, имитирующий структуру JSON от Яндекса)
    mock_response = Mock()
    mock_response.json.return_value = {
        "result": {
            "alternatives": [
                {"message": {"text": "Маск основал SpaceX."}}
            ]
        }
    }
    # Имитируем, что статус запроса 200 OK (ошибок нет)
    mock_response.raise_for_status = Mock()
    mock_post.return_value = mock_response

    # 2. ДЕЙСТВИЕ
    provider = YandexGPTProvider()
    answer = provider.generate("Расскажи про SpaceX")

    # 3. ПРОВЕРКИ
    assert answer == "Маск основал SpaceX.", "Провайдер неправильно распарсил ответ от Яндекса!"
    mock_post.assert_called_once() # Убеждаемся, что post-запрос был отправлен

# Тест 2: Ошибка при запросе (например, неверный ключ или упал сервер)
@patch("src.llm.yandex_provider.requests.post")
def test_yandex_provider_api_error(mock_post, mock_env):
    from src.llm.yandex_provider import YandexGPTProvider
    
    # 1. ПОДГОТОВКА (Имитируем выброс исключения при запросе)
    mock_post.side_effect = Exception("Сервер недоступен")

    # 2. ДЕЙСТВИЕ
    provider = YandexGPTProvider()
    answer = provider.generate("Расскажи про SpaceX")

    # 3. ПРОВЕРКИ
    # Наш код должен перехватить ошибку в блоке try-except и вернуть стандартную фразу
    assert "произошла ошибка" in answer.lower(), "Код не обработал ошибку API!"