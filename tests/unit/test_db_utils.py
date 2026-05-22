import json
from src.utils.db_reader import load_processed_data
from src.utils.db_writer import save_processed_data

def test_load_not_exists(tmp_path):
    """Тест: если файла нет, должен вернуться пустой список (безопасное поведение)."""
    fake_path = tmp_path / "missing_data.json"
    result = load_processed_data(fake_path)
    assert result == []
    assert isinstance(result, list)

def test_save_and_load_data(tmp_path):
    """Тест: проверяем цикл успешного сохранения и загрузки данных."""
    db_path = tmp_path / "test_db.json"
    
    # Можем сохранять словари (для реестра) или списки (для базы)
    test_data = [
        {"source": "doc1.txt", "content": "hello world"}
    ]
    
    # Проверяем сохранение
    success = save_processed_data(test_data, db_path)
    assert success is True
    assert db_path.exists()
    
    # Проверяем чтение
    loaded_data = load_processed_data(db_path)
    assert loaded_data == test_data
    assert loaded_data[0]["source"] == "doc1.txt"

def test_load_corrupted_json(tmp_path):
    """Тест: если JSON сломан, программа не должна падать, а вернуть пустой список."""
    corrupted_path = tmp_path / "bad_data.json"
    corrupted_path.write_text("[broken array", encoding="utf-8")
    
    result = load_processed_data(corrupted_path)
    assert result == []