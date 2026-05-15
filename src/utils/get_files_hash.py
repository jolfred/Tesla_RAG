import os

import hashlib

def calculate_md5(file_path: str) -> str:
    """
    Просто считает хэш. 
    """
    hash_md5 = hashlib.md5()
    try:
        with open(file_path, "rb") as f:
            for chunk in iter(lambda: f.read(4096), b""):
                hash_md5.update(chunk)
        return hash_md5.hexdigest()
    except Exception as e:
        print(f"Ошибка при расчете хэша {file_path}: {e}")
        return ""


def get_files_hash(directory: str, supported_exts: set) -> list:
    """
    Находит все подходящие файлы и сразу вешает на них хэши.
    Возвращает список словарей данными для индексации.
    """
    if not os.path.exists(directory):
        return []

    # Собираем список файлов, которые не являются скрытыми и подходят по формату
    valid_filenames = [
        f for f in os.listdir(directory)
        if not f.startswith('.') and os.path.splitext(f)[1].lower() in supported_exts
    ]

    files_data = []
    for name in valid_filenames:
        path = os.path.join(directory, name)
        files_data.append({
            "path": path,
            "name": name,
            "hash": calculate_md5(path)
        })
            
    return files_data