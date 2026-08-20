from backend.config import EMBEDDING_MODEL_NAME
from backend.utils.logger import setup_logger

logger = setup_logger("embedding_model")

_model = None


def get_embedding_model():
    from sentence_transformers import SentenceTransformer

    global _model
    if _model is None:
        logger.info(f"Loading embedding model: {EMBEDDING_MODEL_NAME}")
        _model = SentenceTransformer(EMBEDDING_MODEL_NAME)
        dim = _model.get_sentence_embedding_dimension()
        logger.info(f"Model loaded, vector dimension: {dim}")
    return _model


def embed_texts(texts: list[str]) -> list[list[float]]:
    model = get_embedding_model()
    vectors = model.encode(texts, show_progress_bar=False, normalize_embeddings=True)
    return vectors.tolist()


def embed_query(text: str) -> list[float]:
    model = get_embedding_model()
    vector = model.encode(text, normalize_embeddings=True)
    return vector.tolist()
