import sys
from pathlib import Path

# Добавляем корень проекта в пути, чтобы Питон видел папку src без бубна
# Это полезно, если запускать файл напрямую
root_dir = Path(__file__).resolve().parent.parent.parent
sys.path.append(str(root_dir))

# config.py теперь лежит в корне проекта
from config import DATA_RAW_DIR, SUPPORTED_EXTENSIONS, OUTPUT_JSON_PATH, REGISTRY_PATH

# union_bilder.py переехал в папку preprocessing
from src.preprocessing.union_bilder import build_document_collection
from src.utils.logger import setup_logger



logger = setup_logger("main_pipeline")
def main():
    logger.info("Запуск пайплайна сборки документов...")
    
    try:
        # Запускаем наш дирижер
        processed_count = build_document_collection(
            directory=str(DATA_RAW_DIR),
            supported_exts=SUPPORTED_EXTENSIONS,
            db_path=OUTPUT_JSON_PATH,
            registry_path=REGISTRY_PATH
        )
        
        if processed_count > 0:
            logger.info(f"Пайплайн завершен. Обработано и обновлено файлов: {processed_count}")
        else:
            logger.info("Изменений не найдено. База в актуальном состоянии.")
            
    except Exception as e:
        logger.error(f"Пайплайн прервался из-за ошибки: {e}", exc_info=True)

if __name__ == "__main__":
    main()