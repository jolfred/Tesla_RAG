from src.load_data.discover import get_files_hash

def test_get_files_hash(tmp_path):
    """Тест: сканер должен находить только нужные форматы и игнорировать скрытые."""
    
    # Создаем тестовые файлы во временной директории
    (tmp_path / "doc1.pdf").write_text("pdf content")
    (tmp_path / "doc2.TXT").write_text("txt content") # Проверяем регистр
    (tmp_path / "image.png").write_text("image")      # Левый формат
    (tmp_path / ".hidden.pdf").write_text("hidden")   # Скрытый файл
    
    supported = {".pdf", ".txt"}
    
    # Запускаем сканер
    results = get_files_hash(str(tmp_path), supported)
    
    # Проверяем результаты
    assert len(results) == 2
    
    # Вытаскиваем имена найденных файлов
    found_names = [res["name"] for res in results]
    assert "doc1.pdf" in found_names
    assert "doc2.TXT" in found_names
    
    # Проверяем, что хэши посчитались
    assert all(res["hash"] != "" for res in results)

def test_get_files_hash_empty_dir(tmp_path):
    """Тест: пустая директория возвращает пустой список."""
    results = get_files_hash(str(tmp_path), {".pdf"})
    assert results == []

def test_get_files_hash_invalid_dir():
    """Тест: несуществующая директория возвращает пустой список."""
    results = get_files_hash("/path/that/does/not/exist", {".pdf"})
    assert results == []