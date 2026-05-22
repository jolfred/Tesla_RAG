import os
from datetime import datetime

from src.utils.get_files_hash import get_files_hash
from src.load_data.load_file import load_file
from src.preprocessing.text_cleaner import clean_text

# Импортируем твои готовые утилиты!
from src.utils.db_reader import load_processed_data
from src.utils.db_writer import save_processed_data

def build_document_collection(directory, supported_exts, db_path, registry_path):
    # 1. Сканируем папку
    current_files = get_files_hash(directory, supported_exts)
    
    # Загружаем реестр через твою утилиту. 
    # Если файла нет, утилита вернет [], поэтому принудительно делаем {} (словарь)
    registry = load_processed_data(registry_path)
    if not isinstance(registry, dict):
        registry = {}
        
    to_process = []
    
    # 2. Ищем измененные или новые файлы
    for f in current_files:
        file_name = f.get('filename') or f.get('name') or os.path.basename(f['path'])
        if registry.get(file_name) != f['hash']:
            to_process.append({
                'name': file_name,
                'path': f['path'],
                'hash': f['hash']
            })
            
    if not to_process:
        return 0

    # Загружаем базу документов
    db = load_processed_data(db_path)
    if not isinstance(db, list):
        db = []
        
    updated_db = list(db)
    processed = 0
    
    # 3. Обрабатываем измененные файлы
    for file in to_process:
        name = file['name']
        
        # Вычищаем старую версию документа из базы
        updated_db = [doc for doc in updated_db if doc.get('source') != name]
        
        content = load_file(file['path'])
        if content:
            cleaned = clean_text(content)
            
            # Собираем структуру документа
            doc_structure = {
                "source": name,
                "hash": file['hash'],
                "content": cleaned,
                "metadata": {
                    "updated_at": datetime.now().isoformat(),
                    "size": len(cleaned)
                }
            }
            
            updated_db.append(doc_structure)
            registry[name] = file['hash']
            processed += 1

    # 4. Сохраняем обновленные данные через твои утилиты
    if processed > 0:
        save_processed_data(updated_db, db_path)
        save_processed_data(registry, registry_path)
        
    return processed