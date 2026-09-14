import os
from pathlib import Path
from dotenv import load_dotenv

load_dotenv()

BASE_DIR = Path(__file__).resolve().parent.parent

# Paths
STORAGE_DIR = BASE_DIR / "storage"
DOCUMENTS_DIR = STORAGE_DIR / "documents"
IMAGES_DIR = STORAGE_DIR / "images"
SCHEMA_DIR = BASE_DIR / "schema"
SESSIONS_DB = STORAGE_DIR / "sessions.db"
FRONTEND_DIST = BASE_DIR / "frontend" / "dist"

for p in [DOCUMENTS_DIR, IMAGES_DIR]:
    p.mkdir(parents=True, exist_ok=True)

# Embedding model
EMBEDDING_MODEL_NAME = "intfloat/multilingual-e5-small"
VECTOR_SIZE = 384

# Qdrant
QDRANT_MODE = os.getenv("QDRANT_MODE", "local")
QDRANT_LOCAL_PATH = STORAGE_DIR / "qdrant_db"
QDRANT_HOST = os.getenv("QDRANT_HOST", "localhost")
QDRANT_PORT = int(os.getenv("QDRANT_PORT", "6333"))
QDRANT_API_KEY = os.getenv("QDRANT_API_KEY", "")
COLLECTION_NAME = "tesla_knowledge"

# Neo4j
NEO4J_URI = os.getenv("NEO4J_URI", "bolt://localhost:7687")
NEO4J_USER = os.getenv("NEO4J_USER", "neo4j")
NEO4J_PASS = os.getenv("NEO4J_PASS", "tesla_neo4j")

# LLM Provider
LLM_PROVIDER = os.getenv("LLM_PROVIDER", "ollama")  # ollama | proxyapi | llamacpp

# Ollama (local)
OLLAMA_BASE_URL = os.getenv("OLLAMA_BASE_URL", "http://localhost:11434")
OLLAMA_MODEL = os.getenv("OLLAMA_MODEL", "qwen2.5:7b-instruct-q4_k_m")

# ProxyAPI (https://proxyapi.ru — доступ к Gemini, GPT и др. из РФ, рубли)
PROXYAPI_KEY = os.getenv("PROXYAPI_KEY", "")
PROXYAPI_BASE_URL = os.getenv("PROXYAPI_BASE_URL", "https://openai.api.proxyapi.ru/v1")

# Google AI Studio — ключ для Gemma-клиента
GOOGLE_AI_STUDIO_KEY = os.getenv("GOOGLE_AI_STUDIO_KEY", "")

# Gemma (Google AI Studio, OpenAI-совместимый эндпоинт)
GEMMA_BASE_URL = os.getenv("GEMMA_BASE_URL", "https://generativelanguage.googleapis.com/v1beta/openai/")
GEMMA_MODEL = os.getenv("GEMMA_MODEL", "gemma-4-31b-it")
GEMMA_RPM = int(os.getenv("GEMMA_RPM", "30"))

# GigaChat (Сбер, OpenAI-совместимый)
GIGACHAT_AUTH_KEY = os.getenv("GIGACHAT_AUTH_KEY", "")
GIGACHAT_MODEL = os.getenv("GIGACHAT_MODEL", "GigaChat-2-Pro")

# API Keys
ADMIN_API_KEY = os.getenv("ADMIN_API_KEY", "admin-secret-key-change-me")
USER_API_KEY = os.getenv("USER_API_KEY", "user-secret-key-change-me")

# Пайплайн вопрос-ответ: v1 (роутер+планировщик, 2 LLM-вызова) | v2
# (единый classify+plan, детерминированные шаблоны, 0-1 вызов).
# Откат на v1 одной переменной окружения.
QUERY_PIPELINE_VERSION = os.getenv("QUERY_PIPELINE_VERSION", "v1")

# Sessions (opaque Bearer-токены)
SESSION_TTL = int(os.getenv("SESSION_TTL", "30"))  # суток
# Фаза 0 (план упрощения пайплайна): ПрогрессLAB — аффилированная структура.
# Факты из корпуса, а не предположения:
# - пост rso_tesla#6902 (2024-04-04): "на базе Штаба КГЭУ СО «Тесла» создался
#   Проектный центр «ПрогрессLAB»";
# - имя группы club225166105: "Проектный центр Штаба СО «Тесла» - «ПрогрессLAB»".
# Явной формулировки "входит в состав"/"структурное подразделение"/PART_OF
# в корпусе НЕТ (grep по корпусу — только нерелевантные совпадения).
# True = создан на базе Штаба, формулировки "проектный центр Штаба" допустимы;
# при этом это НЕ отряд — в список units из карточки rso_tesla не входит.
PROGRESSLAB_IS_SUBORDINATE = os.getenv("PROGRESSLAB_IS_SUBORDINATE", "1") == "1"
# TEMP(ALL_ADMIN): пока все новые сессии — админские (панель «Рентген» без
# отдельного admin-входа). ОТКАТИТЬ перед продакшеном: удалить из .env + тесты.
TESLA_ALL_ADMIN = os.getenv("TESLA_ALL_ADMIN", "") == "1"
VK_APP_ID = os.getenv("VK_APP_ID", "")
VK_APP_SECRET = os.getenv("VK_APP_SECRET", "")
VK_ADMIN_IDS = {x.strip() for x in os.getenv("VK_ADMIN_IDS", "").split(",") if x.strip()}

if QDRANT_MODE == "local":
    QDRANT_LOCAL_PATH.mkdir(parents=True, exist_ok=True)
