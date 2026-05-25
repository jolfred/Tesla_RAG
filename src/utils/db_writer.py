import json

def save_processed_data(data, path):
    """
    Отвечает только за запись итоговой структуры в файл.
    """
    try:
        with open(path, 'w', encoding='utf-8') as f:
            json.dump(data, f, ensure_ascii=False, indent=4)
        return True
    except Exception as e:
        print(f"Ошибка при сохранении данных: {e}")
        return False