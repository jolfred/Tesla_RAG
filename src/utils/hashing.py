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