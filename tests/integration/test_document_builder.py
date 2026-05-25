import json
from src.utils.get_files_hash import calculate_md5
from src.preprocessing.union_builder import  (
    build_document_collection  # Импортируем нашу главную функцию
)

# ... (здесь остаются твои предыдущие тесты для load/save) ...

def test_build_document_collection_full_cycle(tmp_path):
    """
    Интеграционный тест всего конвейера сборки.
    Проверяем первый запуск, пропуск без изменений и обновление файла.
    """
    # 1. Подготовка: создаем структуру папок
    raw_dir = tmp_path / "raw_docs"
    raw_dir.mkdir()
    
    processed_dir = tmp_path / "processed"
    processed_dir.mkdir()
    
    db_path = processed_dir / "knowledge_base.json"
    registry_path = processed_dir / "registry.json"
    supported_exts = {".txt"}
    
    # Создаем первый текстовый файл
    test_file = raw_dir / "test_doc.txt"
    test_file.write_text("Оригинальный текст документа.", encoding="utf-8")
    
    # === ЭТАП 1: Первый запуск (база пустая) ===
    count_run_1 = build_document_collection(
        str(raw_dir), supported_exts, db_path, registry_path
    )
    
    # Проверяем, что 1 файл обработан и JSON-файлы созданы
    assert count_run_1 == 1
    assert db_path.exists()
    assert registry_path.exists()
    
    # Заглянем внутрь базы
    with open(db_path, "r", encoding="utf-8") as f:
        db = json.load(f)
        assert len(db) == 1
        assert db[0]["source"] == "test_doc.txt"
        assert db[0]["content"] == "Оригинальный текст документа."

    # === ЭТАП 2: Повторный запуск (без изменений) ===
    count_run_2 = build_document_collection(
        str(raw_dir), supported_exts, db_path, registry_path
    )
    
    # Проверяем, что функция вернула 0 (ничего не изменилось)
    assert count_run_2 == 0

    # === ЭТАП 3: Обновление файла ===
    # Меняем текст в том же файле
    test_file.write_text("Обновленный текст, много новых данных.", encoding="utf-8")
    
    count_run_3 = build_document_collection(
        str(raw_dir), supported_exts, db_path, registry_path
    )
    
    # Проверяем, что файл снова ушел в обработку
    assert count_run_3 == 1
    
    # Заглянем в базу и убедимся, что старая запись заменилась новой
    with open(db_path, "r", encoding="utf-8") as f:
        updated_db = json.load(f)
        assert len(updated_db) == 1 # Файл тот же, записей не должно стать две
        assert updated_db[0]["content"] == "Обновленный текст, много новых данных."