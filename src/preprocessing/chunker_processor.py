import json
from src.utils.chunker import split_text
from src.utils.logger import setup_logger

logger = setup_logger("chunker_processor")

def build_chunks_database(db_path, chunks_path, chunk_size, chunk_overlap):
    """
    Читает базу документов, нарезает их на чанки и сохраняет в отдельный JSON.
    Теперь функция получает все пути снаружи, что делает её идеальной для тестов!
    """
    logger.info("Начинаю нарезку документов на чанки...")
    
    if not db_path.exists():
        logger.warning("База документов не найдена. Нечего нарезать.")
        return

    # Загружаем собранные документы
    with open(db_path, 'r', encoding='utf-8') as f:
        documents = json.load(f)

    all_chunks = []
    
    # Нарезаем каждый документ
    for doc in documents:
        source_name = doc.get("source", "unknown")
        content = doc.get("content", "")
        
        chunks_list = split_text(content, size=chunk_size, overlap=chunk_overlap)
        
        for i, chunk_text in enumerate(chunks_list):
            all_chunks.append({
                "source": source_name,
                "chunk_index": i,
                "text": chunk_text
            })

    # Сохраняем результат
    with open(chunks_path, 'w', encoding='utf-8') as f:
        json.dump(all_chunks, f, ensure_ascii=False, indent=4)
        
    logger.info(f"Нарезка завершена! Создано {len(all_chunks)} чанков. Сохранено в {chunks_path.name}")