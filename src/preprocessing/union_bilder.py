import json
import os
from datetime import datetime

from ..utils.get_files_hash import get_files_hash
from ..load_data.load_file import load_file
from src.preprocessing.text_cleaner import clean_text

def load_registry(path):
    if not path.exists():
        return {}
    try:
        with open(path, 'r', encoding='utf-8') as f:
            return json.load(f)
    except Exception:
        return {}

def save_registry(data, path):
    try:
        with open(path, 'w', encoding='utf-8') as f:
            json.dump(data, f, ensure_ascii=False, indent=4)
        return True
    except Exception:
        return False

def load_json_database(path):
    if not path.exists():
        return []
    try:
        with open(path, 'r', encoding='utf-8') as f:
            return json.load(f)
    except Exception:
        return []

def save_json_database(data, path):
    try:
        with open(path, 'w', encoding='utf-8') as f:
            json.dump(data, f, ensure_ascii=False, indent=4)
        return True
    except Exception:
        return False

def build_document_collection(directory, supported_exts, db_path, registry_path):
    # 1. Сканируем папку
    current_files = get_files_hash(directory, supported_exts)
    registry = load_registry(registry_path)
    
    to_process = []
    
    # 2. Безопасно вытаскиваем имя файла и сравниваем хэши
    for f in current_files:
        # Страховка: ищем ключ 'filename', если нет - ищем 'name', если нет - берем из пути
        file_name = f.get('filename') or f.get('name') or os.path.basename(f['path'])
        
        if registry.get(file_name) != f['hash']:
            to_process.append({
                'name': file_name,
                'path': f['path'],
                'hash': f['hash']
            })
            
    if not to_process:
        return 0

    db = load_json_database(db_path)
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
            
            # ==========================================
            # ВОТ ЗДЕСЬ ЗАДАЕТСЯ СТРУКТУРА JSON БАЗЫ
            # ==========================================
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

    # 4. Сохраняем обновленные данные
    if processed > 0:
        save_json_database(updated_db, db_path)
        save_registry(registry, registry_path)
        
    return processed