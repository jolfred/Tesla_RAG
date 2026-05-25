import sys
from pathlib import Path

# 1. СНАЧАЛА добавляем корень проекта в системные пути
root_dir = Path(__file__).resolve().parent.parent.parent
sys.path.append(str(root_dir))

# 2. ТОЛЬКО ПОСЛЕ ЭТОГО импортируем наш конфиг и модули
from config import (
    DATA_RAW_DIR, 
    SUPPORTED_EXTENSIONS, 
    OUTPUT_JSON_PATH, 
    REGISTRY_PATH, 
    CHUNKS_JSON_PATH,
    CHUNK_SIZE,
    CHUNK_OVERLAP
)

# Убедись, что файл называется именно union_builder.py
from src.preprocessing.union_builder import build_document_collection
from src.preprocessing.chunker_processor import build_chunks_database
from src.utils.logger import setup_logger

logger = setup_logger("main_pipeline")

def main():
    logger.info("Запуск пайплайна сборки документов...")
    
    try:
        # Шаг 1: Сборка базы
        processed_count = build_document_collection(
            directory=str(DATA_RAW_DIR),
            supported_exts=SUPPORTED_EXTENSIONS,
            db_path=OUTPUT_JSON_PATH,
            registry_path=REGISTRY_PATH
        )
        
        if processed_count > 0:
            logger.info(f"Сборка завершена. Обработано файлов: {processed_count}")
        else:
            logger.info("Изменений не найдено. База в актуальном состоянии.")
            
        # Шаг 2: Нарезка на чанки
        logger.info("Начинаем нарезку документов на чанки...")
        build_chunks_database(
            db_path=OUTPUT_JSON_PATH,
            chunks_path=CHUNKS_JSON_PATH,
            chunk_size=CHUNK_SIZE,
            chunk_overlap=CHUNK_OVERLAP
        )
        logger.info("Пайплайн успешно завершен!")
            
    except Exception as e:
        logger.error(f"Пайплайн прервался из-за ошибки: {e}", exc_info=True)

if __name__ == "__main__":
    main()