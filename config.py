import os
from pathlib import Path

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
CHUNK_SIZE = 800     # Желаемый размер куска в символах
CHUNK_OVERLAP = 150  # Нахлест между кусками, чтобы не терять контекст

# Настройки поиска
SUPPORTED_EXTENSIONS = {'.pdf', '.docx', '.txt'}

# Создаем папки
for path in [DATA_RAW_DIR, DATA_PROCESSED_DIR, LOGS_DIR]:
    path.mkdir(parents=True, exist_ok=True)