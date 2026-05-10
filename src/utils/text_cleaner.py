import re

def clean_text(text: str) -> str:
    """
    Выполняет очистку текста для RAG.
    """
    if not text:
        return ""
    
    # Убираем лишние пробелы и табуляцию
    text = re.sub(r'[ \t]+', ' ', text)
    
    # Убираем множественные переносы строк (оставляем максимум один пустой разрыв)
    text = re.sub(r'\n\s*\n', '\n\n', text)
    
    # Чистим края
    return text.strip()