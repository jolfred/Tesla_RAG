from src.llm.base_provider import BaseLLMProvider
from src.llm.gigachat_provider import GigaChatProvider
from src.llm.yandex_provider import YandexGPTProvider
from src.utils.logger import setup_logger

logger = setup_logger("llm_client")

class LLMClient:
    def __init__(self, provider: BaseLLMProvider = None):
        """
        Инициализируем клиента. Если провайдер не передан, 
        по умолчанию используем GigaChatProvider.
        """
        self.provider = provider or GigaChatProvider()
        

    def _send_to_model(self, prompt: str) -> str:
        """
        Внутренний метод-обертка. 
        Оставлен специально, чтобы твои тесты с @patch.object работали корректно.
        """
        return self.provider.generate(prompt)

    def generate_answer(self, query: str, context_chunks: list) -> str:
        """
        Формирует системный промпт (RAG) на основе найденного контекста 
        и вопроса пользователя, затем передает его в модель.
        """
        if not context_chunks:
            logger.warning("Контекст пуст. Отправляем вопрос без базы знаний.")
            return self._send_to_model(query)

        # 1. Извлекаем тексты из чанков
        context_texts = [chunk.get("text", "") for chunk in context_chunks]
        context_joined = "\n---\n".join(context_texts)

        # 2. Собираем строгий RAG-промпт
        prompt = (
            "Ты — умный помощник. Ответь на вопрос пользователя, опираясь ТОЛЬКО на предоставленный контекст. "
            "Если в контексте нет ответа, так и скажи: 'В базе знаний нет информации по этому вопросу', "
            "не придумывай ничего от себя.\n\n"
            f"КОНТЕКСТ:\n{context_joined}\n\n"
            f"ВОПРОС ПОЛЬЗОВАТЕЛЯ: {query}\n\n"
            "ОТВЕТ:"
        )

        logger.info("Промпт сформирован. Ожидаем ответ от LLM...")
        
        # 3. Отправляем промпт через выбранного провайдера
        return self._send_to_model(prompt)
    

if __name__ == "__main__":
    # Импортируем нужного провайдера для теста
    from src.llm.yandex_provider import YandexGPTProvider
    from dotenv import load_dotenv
    
    # Загружаем ключи из .env для ручного запуска
    load_dotenv()

    # 1. Создаем стратегию для Яндекса
    yandex_strategy = YandexGPTProvider()

    # 2. Передаем её в клиент
    llm_client = LLMClient(provider=yandex_strategy)

    # 3. Создаем ПРАВИЛЬНЫЙ фейковый контекст (список словарей)
    fake_context = [
        {"score": 0.99, "source": "doc1", "text": "Илон Маск основал SpaceX в 2002 году."},
        {"score": 0.85, "source": "doc2", "text": "SpaceX занимается производством космической техники."}
    ]

    print("\n--- Тест YandexGPT ---")
    print("Отправляем запрос...\n")
    
    # 4. Вызываем метод с правильными данными
    answer = llm_client.generate_answer(
        query="Чем занимается SpaceX и когда она была основана?", 
        context_chunks=fake_context
    )
    
    print("ОТВЕТ НЕЙРОСЕТИ:")
    print(answer)