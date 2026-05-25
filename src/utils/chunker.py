def split_text(text: str, size: int, overlap: int) -> list:
    """
    Разбивает текст на чанки по словам, ориентируясь на максимальное число символов (size).
    Никогда не разрывает слова и аккуратно переносит overlap.
    """
    if not text:
        return []
        
    # Разбиваем весь текст на отдельные слова
    words = text.split()
    chunks = []
    
    current_chunk = []
    current_len = 0
    
    i = 0
    while i < len(words):
        word = words[i]
        
        # Считаем длину слова + 1 символ под пробел (если это не первое слово в чанке)
        word_len = len(word) + (1 if current_chunk else 0)
        
        # Если слово влезает в лимит ИЛИ чанк пока пустой (для очень длинных слов)
        if current_len + word_len <= size or not current_chunk:
            current_chunk.append(word)
            current_len += word_len
            i += 1 # Переходим к следующему слову
        else:
            # Корзина заполнилась! Сохраняем текущий чанк, склеивая слова пробелами
            chunks.append(" ".join(current_chunk))
            
            # --- Делаем нахлест (overlap) ---
            overlap_chunk = []
            overlap_len = 0
            
            # Идем с конца текущего чанка и берем слова, пока они влезают в overlap
            if overlap > 0:
                for w in reversed(current_chunk):
                    w_len = len(w) + (1 if overlap_chunk else 0)
                    if overlap_len + w_len <= overlap:
                        overlap_chunk.insert(0, w) # Добавляем в начало, так как идем с конца
                        overlap_len += w_len
                    else:
                        break
                        
            # Начинаем собирать новую корзину, в которой уже лежат слова из нахлеста
            current_chunk = overlap_chunk
            current_len = overlap_len
            
    # Не забываем добавить последний кусочек текста, если он остался
    if current_chunk:
        chunks.append(" ".join(current_chunk))
   
    return chunks