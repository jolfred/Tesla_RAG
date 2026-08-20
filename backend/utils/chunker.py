from transformers import AutoTokenizer
from backend.config import CHUNK_SIZE, CHUNK_OVERLAP
from backend.utils.logger import setup_logger

logger = setup_logger("chunker")

_tokenizer = None


def _get_tokenizer():
    global _tokenizer
    if _tokenizer is None:
        _tokenizer = AutoTokenizer.from_pretrained("intfloat/multilingual-e5-small")
    return _tokenizer


def split_text(text: str, size: int = None, overlap: int = None) -> list[str]:
    if size is None:
        size = CHUNK_SIZE
    if overlap is None:
        overlap = CHUNK_OVERLAP

    tokenizer = _get_tokenizer()
    tokens = tokenizer.encode(text, add_special_tokens=False)
    total = len(tokens)

    if total <= size:
        return [text]

    chunks = []
    start = 0
    while start < total:
        end = min(start + size, total)
        chunk_tokens = tokens[start:end]
        chunk_text = tokenizer.decode(chunk_tokens, skip_special_tokens=True)
        if chunk_text.strip():
            chunks.append(chunk_text)
        start += size - overlap

    logger.debug(f"Split {total} tokens into {len(chunks)} chunks")
    return chunks
