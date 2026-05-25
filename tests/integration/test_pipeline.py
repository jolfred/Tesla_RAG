import json
from unittest.mock import patch
from src.preprocessing.pipeline import main

def test_full_pipeline_execution(tmp_path):
    """
    Проверяет весь цикл от чтения сырого файла до создания чанков.
    """
    # 1. Подготовка: создаем временные папки
    raw_dir = tmp_path / "raw"
    raw_dir.mkdir()
    
    processed_dir = tmp_path / "processed"
    processed_dir.mkdir()
    
    # Создаем фейковые пути для файлов базы
    mock_db_path = processed_dir / "knowledge_base.json"
    mock_registry_path = processed_dir / "file_registry.json"
    mock_chunks_path = processed_dir / "chunks.json"

    # Создаем тестовый текстовый файл (делаем его длинным, чтобы он точно нарезался на чанки)
    test_file = raw_dir / "test_musk.txt"
    test_text = "Илон Маск основал SpaceX. " * 50  # Искусственно удлиняем текст
    test_file.write_text(test_text, encoding="utf-8")

    # 2. Действие: подменяем константы в pipeline.py на наши временные пути и запускаем
    with patch("src.preprocessing.pipeline.DATA_RAW_DIR", raw_dir), \
         patch("src.preprocessing.pipeline.OUTPUT_JSON_PATH", mock_db_path), \
         patch("src.preprocessing.pipeline.REGISTRY_PATH", mock_registry_path), \
         patch("src.preprocessing.pipeline.CHUNKS_JSON_PATH", mock_chunks_path):
        
        # Запускаем главную функцию пайплайна
        main()

    # 3. Проверки (Asserts)
    # Проверяем, что все три файла успешно создались
    assert mock_registry_path.exists(), "Реестр не создался!"
    assert mock_db_path.exists(), "База документов не создалась!"
    assert mock_chunks_path.exists(), "Файл с чанками не создался!"

    # Проверяем содержимое чанков
    with open(mock_chunks_path, "r", encoding="utf-8") as f:
        chunks = json.load(f)
        
        # Убеждаемся, что чанки есть и они привязаны к нашему файлу
        assert len(chunks) > 0, "Чанки не нарезались!"
        assert chunks[0]["source"] == "test_musk.txt"
        assert "Илон Маск" in chunks[0]["text"]