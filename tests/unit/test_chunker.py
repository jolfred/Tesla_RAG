from src.utils.chunker import split_text

def test_split_text_empty():
    """Тест: пустой текст должен возвращать пустой список."""
    assert split_text("", size=100, overlap=10) == []
    assert split_text(None, size=100, overlap=10) == []

def test_split_text_no_overlap():
    """Тест: нарезка без перекрытия работает корректно."""
    text = "aaaa bbbb cccc dddd"
    # Режем по 4 символа (длина слова), без нахлеста
    chunks = split_text(text, size=4, overlap=0)
    # Ожидаем, что слова не порвутся
    assert "aaaa" in chunks[0]
    assert len(chunks) > 1

def test_split_text_with_overlap():
    """Тест: перекрытие (overlap) сохраняет часть предыдущего текста."""
    text = "word1 word2 word3 word4"
    # Размер 11 (вмещает "word1 word2"), нахлест 6 (вмещает "word2")
    chunks = split_text(text, size=11, overlap=6)
    
    assert len(chunks) >= 2
    # Слово word2 должно быть и в конце первого чанка, и в начале второго
    print(chunks)
    assert "word2" in chunks[0]
    assert "word2" in chunks[1]

def test_split_text_respects_spaces():
    """Тест: чанкер не должен резать слова посередине."""
    text = "hello world! this is a test."
    # Размер 9 падает ровно на середину слова "world!" (hello wor)
    chunks = split_text(text, size=9, overlap=0)
    
    # Скрипт должен отступить до пробела и выдать только "hello"
    assert chunks[0] == "hello"