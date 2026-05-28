import os
from gigachat import GigaChat
from src.llm.base_provider import BaseLLMProvider
from src.utils.logger import setup_logger

logger = setup_logger("gigachat_provider")

class GigaChatProvider(BaseLLMProvider):
    def __init__(self, model_name: str = "GigaChat-Max"):
        """
        Инициализация GigaChat. Ключ берется из переменных окружения.
        """
        self.credentials = os.getenv("GIGACHAT_CREDENTIALS")
        if not self.credentials:
            logger.error("Не найден ключ GIGACHAT_CREDENTIALS в переменных окружения!")
            raise ValueError("Укажите GIGACHAT_CREDENTIALS в файле .env")
        
        self.model_name = model_name

    def generate(self, prompt: str) -> str:
        """
        Отправляет промпт в GigaChat и возвращает ответ.
        """
        logger.info(f"Отправка запроса в {self.model_name}...")
        
        try:
            # scope="GIGACHAT_API_PERS" — обязательно для физлиц!
            # verify_ssl_certs=False отключает проверку сертификатов Минцифры, 
            # что полезно для локальной разработки.
            with GigaChat(
                credentials=self.credentials, 
                scope="GIGACHAT_API_PERS", 
                verify_ssl_certs=False
            ) as giga:
                response = giga.chat({
                    "model": self.model_name,
                    "messages": [
                        {"role": "user", "content": prompt}
                    ]
                })
                
                return response.choices[0].message.content
                
        except Exception as e:
            logger.error(f"Ошибка при обращении к GigaChat API: {e}")
            return "Извините, произошла ошибка при генерации ответа от нейросети."