from src.preprocessing.text_cleaner import clean_text

def test_clean_text_empty():
    assert clean_text("") == ""
    assert clean_text(None) == ""

def test_clean_text_removes_extra_spaces():
    text = "Текст    с   лишними \t пробелами"
    expected = "Текст с лишними пробелами"
    assert clean_text(text) == expected

def test_clean_text_normalizes_newlines():
    text = "Первая строка\n\n\n\nВторая строка"
    expected = "Первая строка\n\nВторая строка"
    assert clean_text(text) == expected

def test_clean_text_strips_edges():
    text = "  Текст с пробелами по краям  \n"
    expected = "Текст с пробелами по краям"
    assert clean_text(text) == expected