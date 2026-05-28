import os
from dotenv import load_dotenv
from src.utils.logger import setup_logger

# Импортируем наши классы
from src.vectorization.searcher import Searcher
from src.llm.client import LLMClient
from src.llm.yandex_provider import YandexGPTProvider
# from src.llm.gigachat_provider import GigaChatProvider # (если захочешь вернуть Сбер)

# Инициализируем настройки
load_dotenv()
logger = setup_logger("main")

def main():
    print("🤖 Добро пожаловать в RAG-систему!")
    
    # Задаем тестовый вопрос
    query = "Выпиши в хранологии командиров штаба тесла"
    logger.info(f"1. Получен вопрос от пользователя: {query}")

    # --- ЭТАП 1: ПОИСК ЧАНКОВ ---
    logger.info("2. Ищем релевантные документы в базе знаний...")
    searcher = Searcher()
    # Предполагаем, что у твоего Searcher есть метод search. 
    # Если он называется иначе, поправь название метода ниже.
    found_chunks = searcher.search(query=query, top_k=15)
    
    if not found_chunks:
        logger.warning("Чанки не найдены! Возможно, база Qdrant пуста.")
        # Мы все равно продолжим, чтобы посмотреть, как ответит LLM без контекста

    # --- ЭТАП 2: ГЕНЕРАЦИЯ ОТВЕТА ---
    logger.info("3. Подключаем нейросеть...")
    # Выбираем провайдера (сейчас это Яндекс)
    yandex_provider = YandexGPTProvider()
    llm_client = LLMClient(provider=yandex_provider)

    logger.info("4. Передаем найденные чанки в нейросеть...")
    # МАГИЯ ЗДЕСЬ: Мы передаем вопрос и найденные куски текста в клиент
    # answer = llm_client.generate_answer(query=query, context_chunks=found_chunks)

    # --- ВЫВОД РЕЗУЛЬТАТА ---
    print("\n" + "="*50)
    print("👤 ВОПРОС ПОЛЬЗОВАТЕЛЯ:")
    print(query)
    print("-" * 50)
    
    print("📄 НАЙДЕННЫЕ ЧАНКИ (Что нашел Qdrant):")
    if found_chunks:
        for i, chunk in enumerate(found_chunks, 1):
            text = chunk.get('text', '')
            score = chunk.get('score', 0.0)
            print(f"[{i}] (Совпадение: {score}): {text[:100]}...") # Выводим первые 100 символов
    else:
        print("Ничего не найдено.")
    print("-" * 50)
    
    print("✨ ОТВЕТ НЕЙРОСЕТИ:")
    # print(answer)
    print("="*50 + "\n")

if __name__ == "__main__":
    main()