# GraphRAG API — Штаб Тесла

GraphRAG API Service для цифровой платформы Штаба СО КГЭУ «Тесла».

## Быстрый старт

```bash
# Установка зависимостей
pip install -r backend/requirements.txt

# Запуск локально (нужны Qdrant + Neo4j + Ollama)
cd backend
uvicorn backend.main:app --reload

# Запуск через Docker
docker compose up --build
```

## API

| Метод | Путь | Аутентификация | Описание |
|-------|------|---------------|----------|
| POST | `/api/v1/chat` | User | Задать вопрос AI-ассистенту |
| POST | `/api/v1/documents/upload` | Admin | Загрузить документ (PDF/DOCX/TXT/JSON) |
| POST | `/api/v1/index/rebuild` | Admin | Перестроить векторный индекс и граф |
| GET  | `/api/v1/status` | — | Статус сервиса |

## Переменные окружения (.env)

- `ADMIN_API_KEY` — ключ для admin-эндпоинтов
- `USER_API_KEY` — ключ для user-эндпоинтов
- `OLLAMA_MODEL` — модель LLM (по умолч. `qwen2.5:7b-instruct-q4_k_m`)
- `QDRANT_MODE` — `local` или `server`
- `NEO4J_URI` — адрес Neo4j
