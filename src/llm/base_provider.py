from abc import ABC, abstractmethod

class BaseLLMProvider(ABC):
    """
    Базовый класс (Интерфейс) для всех LLM-провайдеров.
    """
    
    @abstractmethod
    def generate(self, prompt: str) -> str:
        """
        Принимает готовый текстовый промпт и возвращает ответ от нейросети.
        Любой новый провайдер обязан реализовать этот метод.
        """
        pass