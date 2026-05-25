import json

def load_processed_data(path):
    """
    Отвечает только за чтение текущего состояния базы из JSON.
    """
    if not path.exists():
        return []
    
    try:
        with open(path, 'r', encoding='utf-8') as f:
            return json.load(f)
    except Exception as e:
        print(f"Критическая ошибка при чтении базы: {e}")
        return []