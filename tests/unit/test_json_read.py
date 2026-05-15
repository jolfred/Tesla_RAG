import json
from src.preprocessing.union_bilder import (
    load_registry, 
    save_registry, 
    load_json_database, 
    save_json_database
)

# === ТЕСТЫ ДЛЯ РЕЕСТРА (Registry) ===
# === Тесты для Registry (Словарь) ===

def test_load_registry_not_exists(tmp_path):
    """Если файла реестра нет, должен вернуться пустой словарь."""
    fake_path = tmp_path / "missing_registry.json"
    result = load_registry(fake_path)                                                                                                                                                                                                                                                                                                                                 
    assert result == {}
    assert isinstance(result, dict)
 
def test_save_and_load_registry(tmp_path):
    """Проверяем цикл сохранения и загрузки реестра."""
    reg_path = tmp_path / "reg.json"
    test_data = {"file1.txt": "hash123", "file2.pdf": "hash456"}
    
    # Сохраняем
    save_registry(test_data, reg_path)
    assert reg_path.exists()
    
    # Загружаем и сверяем
    loaded_data = load_registry(reg_path)
    assert loaded_data == test_data
    assert loaded_data["file1.txt"] == "hash123"

def test_load_registry_corrupted(tmp_path):
    """Если JSON сломан, функция не должна крашить программу."""
    corrupted_path = tmp_path / "bad_reg.json"
    corrupted_path.write_text("{bad json data", encoding="utf-8")
    
    result = load_registry(corrupted_path)
    assert result == {} # Ожидаем пустой словарь при ошибке

# === Тесты для Main Database (Список) ===

def test_load_main_db_not_exists(tmp_path):
    """Если файла базы нет, должен вернуться пустой список."""
    fake_path = tmp_path / "missing_db.json"
    result = load_json_database(fake_path)
    assert result == []
    assert isinstance(result, list)

def test_save_and_load_main_db(tmp_path):
    """Проверяем цикл сохранения и загрузки базы знаний."""
    db_path = tmp_path / "db.json"
    test_data = [
        {"source": "doc1.txt", "content": "hello world"},
        {"source": "doc2.pdf", "content": "test text"}
    ]
    
    # Сохраняем
    success = save_json_database(test_data, db_path)
    # Если твоя функция не возвращает True/False, убери эту проверку, 
    # просто проверь, что файл существует
    assert db_path.exists()
    
    # Загружаем и сверяем
    loaded_data = load_json_database(db_path)
    assert loaded_data == test_data
    assert len(loaded_data) == 2
    assert loaded_data[0]["source"] == "doc1.txt"

def test_load_main_db_corrupted(tmp_path):
    """Если JSON базы сломан, возвращаем пустой список."""
    corrupted_path = tmp_path / "bad_db.json"
    corrupted_path.write_text("[broken array", encoding="utf-8")
    
    result = load_json_database(corrupted_path)
    assert result == [] # Ожидаем пустой список