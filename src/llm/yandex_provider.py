import os
import requests
from src.llm.base_provider import BaseLLMProvider
from src.utils.logger import setup_logger

logger = setup_logger("yandex_provider")

class YandexGPTProvider(BaseLLMProvider):
    def __init__(self, model_name: str = "yandexgpt/latest"):
        """
        Инициализация провайдера YandexGPT.
        model_name по умолчанию использует последнюю основную модель.
        Можно также передать 'yandexgpt-lite/latest' для экономии лимитов.
        """
        self.api_key = os.getenv("YANDEX_API_KEY")
        self.folder_id = os.getenv("YANDEX_FOLDER_ID")
        
        if not self.api_key or not self.folder_id:
            logger.error("Не найдены YANDEX_API_KEY или YANDEX_FOLDER_ID в .env!")
            raise ValueError("Проверьте настройки Yandex Cloud в файле .env")
            
        self.model_name = model_name
        # Официальный URL API YandexGPT для генерации текста
        self.url = "https://llm.api.cloud.yandex.net/foundationModels/v1/completion"

    def generate(self, prompt: str) -> str:
        """
        Отправляет промпт в YandexGPT через POST-запрос и возвращает ответ.
        """
        logger.info(f"Отправка запроса в YandexGPT ({self.model_name})...")
        
        # Настраиваем заголовки для авторизации
        headers = {
            "Authorization": f"Api-Key {self.api_key}",
            "Content-Type": "application/json"
        }
        
        # Формируем тело запроса по правилам Яндекса
        payload = {
            # Адрес модели собирается из folder_id и имени модели
            "modelUri": f"gpt://{self.folder_id}/{self.model_name}",
            "completionOptions": {
                "stream": False,
                "temperature": 0.3, # Низкая температура для точных ответов в RAG
                "maxTokens": "2000"
            },
            "messages": [
                {
                    "role": "user",
                    "text": prompt
                }
            ]
        }
        
        try:
            response = requests.post(self.url, headers=headers, json=payload, timeout=30)
            
            # Если Яндекс ответил ошибкой (например, 400 или 403), это вызовет исключение
            response.raise_for_status()
            
            # Разбираем JSON-ответ от Яндекса
            result = response.json()
            answer = result["result"]["alternatives"][0]["message"]["text"]
            return answer
            
        except Exception as e:
            logger.error(f"Ошибка при обращении к YandexGPT API: {e}")
            if 'response' in locals():
                logger.error(f"Ответ сервера: {response.text}")
            return "Извините, произошла ошибка при генерации ответа от YandexGPT."