import os
from pathlib import Path

# Пути к данным
BASE_DIR = Path(__file__).resolve().parent.parent
DATA_RAW_DIR = os.path.join(BASE_DIR, "data", "raw")
DATA_PROCESSED_DIR = os.path.join(BASE_DIR, "data", "processed")
OUTPUT_JSON_PATH = os.path.join(DATA_PROCESSED_DIR, "knowledge_base.json")
REGISTRY_PATH = os.path.join(DATA_PROCESSED_DIR, "file_registry.json")
# Настройки обработки
SUPPORTED_EXTENSIONS = {'.pdf', '.docx', '.txt'}


# Логирование
LOGS_DIR = os.path.join(BASE_DIR,"logs")
LOG_FILE = os.path.join(LOGS_DIR, "app.log")

# Параметры нарезки (Chunking)
CHUNK_SIZE = 800     # Желаемый размер куска в символах
CHUNK_OVERLAP = 150  # Нахлест между кусками, чтобы не терять контекст


# Создаем папки
for path in [DATA_RAW_DIR, DATA_PROCESSED_DIR, LOGS_DIR]:
    path.mkdir(parents=True, exist_ok=True)