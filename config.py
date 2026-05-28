import os
from pathlib import Path
from dotenv import load_dotenv

# Загружаем переменные окружения из .env файла
load_dotenv()
# Корень проекта
BASE_DIR = Path(__file__).resolve().parent

# Папки для данных
DATA_RAW_DIR = BASE_DIR / "data" / "raw"
DATA_PROCESSED_DIR = BASE_DIR / "data" / "processed"

# Файлы базы, реестра и чанков
OUTPUT_JSON_PATH = DATA_PROCESSED_DIR / "knowledge_base.json"
CHUNKS_JSON_PATH = DATA_PROCESSED_DIR / "chunks.json"
REGISTRY_PATH = DATA_PROCESSED_DIR / "file_registry.json"

# Логирование
LOGS_DIR = BASE_DIR / "logs"
LOG_FILE = LOGS_DIR / "app.log"

# Параметры нарезки (Chunking)
CHUNK_SIZE = 400     # Желаемый размер куска в символах
CHUNK_OVERLAP = 50  # Нахлест между кусками, чтобы не терять контекст

SUPPORTED_EXTENSIONS = {'.pdf', '.docx', '.txt'}

# Создаем папки
for path in [DATA_RAW_DIR, DATA_PROCESSED_DIR, LOGS_DIR]:
    path.mkdir(parents=True, exist_ok=True)

    # --- НАСТРОЙКИ ВЕКТОРНОЙ БАЗЫ И EMBEDDINGS ---

# Выбор модели
EMBEDDING_MODEL_NAME = str(BASE_DIR / "models" / "rubert-tiny2")
# EMBEDDING_MODEL_NAME = "cointegrated/rubert-tiny2"
VECTOR_SIZE = 312  # Для rubert-tiny2 размер вектора всегда 312

# Настройки Qdrant
QDRANT_MODE = "local"  # Поменяй на "server", когда перейдешь на Docker
QDRANT_LOCAL_PATH = BASE_DIR / "data" / "qdrant_db"
QDRANT_HOST = "localhost"
QDRANT_PORT = 6333
COLLECTION_NAME = "knowledge_base"

# Убедимся, что папка для локального Qdrant существует
if QDRANT_MODE == "local":
    QDRANT_LOCAL_PATH.mkdir(parents=True, exist_ok=True)

