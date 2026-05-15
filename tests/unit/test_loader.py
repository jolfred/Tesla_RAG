from src.load_data.load_file import load_file

def test_load_txt_file(tmp_path):
    # 1. Подготовка (Arrange)
    # tmp_path — это встроенная магия pytest, создает временную папку
    fake_file = tmp_path / "dummy.txt"
    fake_file.write_text("Это тестовый документ про Илона Маска.", encoding="utf-8")
    
    # 2. Действие (Act)
    # Передаем путь к нашему фейковому файлу в твою функцию
    result = load_file(str(fake_file))
    
    # 3. Проверка (Assert)
    assert result == "Это тестовый документ про Илона Маска."

def test_load_unsupported_file(tmp_path):
    # Проверим, как система реагирует на левый формат (например, картинку)
    fake_image = tmp_path / "photo.jpg"
    fake_image.write_text("fake bytes")
    
    result = load_file(str(fake_image))
    
    # Мы ожидаем, что функция вернет пустую строку и не крашнется
    assert result == ""