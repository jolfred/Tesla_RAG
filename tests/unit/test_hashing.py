from src.utils.hashing import calculate_md5

def test_calculate_md5_valid_file(tmp_path):
    """Тест: хэш одинакового контента должен совпадать."""
    # Создаем временный файл
    test_file = tmp_path / "test.txt"
    test_file.write_text("Hello, RAG!", encoding="utf-8")
    
    hash1 = calculate_md5(str(test_file))
    
    # Считаем еще раз
    hash2 = calculate_md5(str(test_file))
    
    assert hash1 == hash2
    assert len(hash1) == 32 # MD5 всегда 32 символа

def test_calculate_md5_detects_changes(tmp_path):
    """Тест: при изменении файла хэш должен измениться."""
    test_file = tmp_path / "test.txt"
    
    test_file.write_text("Version 1", encoding="utf-8")
    hash_v1 = calculate_md5(str(test_file))
    
    test_file.write_text("Version 2", encoding="utf-8")
    hash_v2 = calculate_md5(str(test_file))
    
    assert hash_v1 != hash_v2

def test_calculate_md5_missing_file():
    """Тест: для несуществующего файла возвращается пустая строка."""
    assert calculate_md5("non_existent_file.txt") == ""