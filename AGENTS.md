# AGENTS.md

GraphRAG-сервис для Штаба СО КГЭУ «Тесла». VK-посты → граф (Neo4j) + векторный индекс (Qdrant) → Louvain-сообщества → ответы через GigaChat. Работает только с серверами Docker (`docker compose up -d qdrant neo4j`); Python-venv в `.venv`.

## Команды

```bash
# API (порт 8000)
.venv/bin/python -m uvicorn backend.main:app --host 0.0.0.0 --port 8000

# Индексация постов в Neo4j + Qdrant (ресюм: пропускает уже проиндексированные)
.venv/bin/python -m backend.indexer.indexer storage/posts/posts_*.jsonl --model gigachat --min-date ''

# Фоновый запуск (без setsid процесс умирает вместе с терминалом!)
setsid nohup .venv/bin/python -m backend.indexer.indexer $(ls storage/posts/posts_*.jsonl | grep -v kgeu_official | tr '\n' ' ') --model gigachat --min-date '' > storage/logs/index_all_gigachat.log 2>&1 < /dev/null & disown

# Сообщества (медленно: 1 запрос GigaChat на сообщество, ~890 шт)
.venv/bin/python -m backend.scripts.build_communities

# Тесты (моковые, сервисы не нужны)
.venv/bin/python -m pytest backend/indexer/test_indexer.py

# Бенчмарк RAG-ответов (нужны Neo4j + Qdrant + GigaChat; оценка 0/1/2 через GigaChat)
.venv/bin/python -m backend.scripts.benchmark.runner --mode searcher
# через HTTP API (uvicorn запущен на 8000):
.venv/bin/python -m backend.scripts.benchmark.runner --mode api --api-url http://localhost:8000
# только собрать ответы без оценки; подмножество тестов: --ids q1,q2
# продолжение прерванного прогона (пропускает вопросы с ответом): --resume
# Прогресс сохраняется инкрементально после каждого вопроса в storage/benchmark/report_latest.json.

# Скрапер (метаданные групп и посты VK)
.venv/bin/python -m scraper.main --url-file storage/posts/group_links.txt --meta

# Фронтенд (сборка ТОЛЬКО через Docker, Node на хосте не ставится)
docker run --rm -v $PWD/frontend:/app -v graphrag_npm_cache:/root/.npm -w /app node:20-alpine sh -c "npm ci && npm run build"
# локальная разработка (Vite на 5173, прокси /api -> :8000):
docker run --rm -p 5173:5173 -v $PWD/frontend:/app -v graphrag_npm_cache:/root/.npm -w /app node:20-alpine sh -c "npm ci && npm run dev"
# тесты фронтенда (Vitest, jsdom):
docker run --rm -v $PWD/frontend:/app -v graphrag_npm_cache:/root/.npm -w /app node:20-alpine sh -c "npm ci && npm test"
```

## M1: Сессии и фронтенд (bearer-токены)

- **Авторизация** — opaque-токен (не cookie/JWT). Сервер хранит только SHA-256 хэш в SQLite `storage/sessions.db` (таблица `sessions`), TTL = `SESSION_TTL` суток (по умолчанию 30). Клиент шлёт токен в заголовке `Authorization: Bearer <token>`. X-API-Key (USER/ADMIN) продолжает работать на `/api/v1/chat` без изменений.
- **Эндпоинты /auth** (модуль `backend/api/sessions.py`, роут `backend/api/routes/auth.py`):
  - `POST /api/v1/auth/guest` → `{token, role:"user", expires_at}` — вход без логина (FR-1.1).
  - `POST /api/v1/auth/admin {api_key}` → токен `role="admin"` при совпадении с `ADMIN_API_KEY` (hmac.compare_digest), иначе 401 (FR-1.2).
  - `GET /api/v1/auth/me` (Bearer) → `{role, vk_user_id, expires_at}`; невалидный/истёкший → 401 (FR-1.3). Фронтенд при 401 тихо перевыдаёт гостевой токен.
  - `POST /api/v1/auth/logout` (Bearer) → отзыв токена (удаление из БД) (FR-1.4).
  - `POST /api/v1/auth/vk {params, sign}` → VK-вход с проверкой подписи launch-параметров (HMAC-SHA256 на `VK_APP_SECRET`, официальный алгоритм VK); роль по allowlist `VK_ADMIN_IDS`; при пустом секрете → 501 (FR-1.8, «спит» до создания приложения в dev.vk.com).
- **Фронтенд**: `frontend/` (Vite + React + TS + VKUI + vk-bridge). Сборка только через Docker (`npm ci && npm run build`), готовая статика в `frontend/dist/`. FastAPI раздаёт `/assets/*` и отдаёт `index.html` для не-API GET-путей (SPA-fallback); `/api/*`, `/docs`, `/openapi.json`, `/redoc` не перехватываются. Собранную статику в docker-compose можно смонтировать: `./frontend/dist:/app/frontend/dist`.
- **Модуль аутентификации фронта**: `frontend/src/auth/` (authContext + `localStorage`), `frontend/src/api/client.ts` (Bearer-инжекция + авто-перевыдача гостя при 401), `frontend/src/types.ts` (единый источник истины контрактов API). Экраны: Чат (`src/pages/ChatPage.tsx`), Статус (`src/pages/StatusPage.tsx`, вход/выход админа).
- **Новые переменные .env**: `SESSION_TTL` (30), `VK_APP_ID` (пусто), `VK_APP_SECRET` (пусто → VK-вход неактивен), `VK_ADMIN_IDS` (CSV).
- **Тесты M1**: `backend/api/test_sessions.py`, `backend/api/test_auth.py` (вкл. тест-векторы VK sign, Bearer vs X-API-Key на `/chat`). Админ-роуты (`documents/index/communities`) по-прежнему только X-API-Key; Bearer-зависимость `verify_admin_session` готова к M2.

## Критические нюансы

- **Два разных Qdrant.** В `.env` `QDRANT_MODE=local`, но **индексатор и `vec_search.py` ходят в серверный Qdrant на порту 6333 напрямую** (коллекция `posts`), игнорируя `QDRANT_MODE`. Локальный `storage/qdrant_db` (коллекция `tesla_knowledge`, виден в `/api/v1/status`) использует только старый `backend/embeddings/qdrant_client.py` — не трогай его за состояние RAG.
- **Эмбеддинги индексатора и поиска**: `text-embedding-3-small` через ProxyAPI, а НЕ через sentence-transformers. `backend/embeddings/model.py` использует ленивый импорт sentence-transformers (пакет не установлен) — не вызывай этот путь.
- **Neo4j — Community edition**, мульти-БД недоступна. Схема «двух моделей»: сущности/рёбра имеют `source_model` + композитный уникальный ключ `merge_key = "{source_model}::{id}"` (constraint на `merge_key`, не на `id`). Сейчас все данные `source_model='gigachat'`; Gemma-ветка готова, но заморожена.
- **Индексатор**: `--model gigachat|gemma|proxyapi`, `--min-date ''` = все годы. Пропускает посты с пустым `text_clean` (посты-картинки с одними хэштегами) — это ожидаемо, не баг. `--parallel` только для gemma.
- **GigaChat**: OAuth через `ngw.devices.sberbank.ru` с `verify=False`; клиент `backend/utils/gigachat_client.py`; таймаут 120с (дефолтный 600с вешал процесс). Модель: `GigaChat-3-Ultra` (`GIGACHAT_MODEL`). `LLM_PROVIDER` в `answer_generator.py` = `gigachat`.
- **VK-токен**: в `.env` реальный ключ лежит в `VK_SERVICE_TOKEN1` (`VK_SERVICE_TOKEN` пустой); скрапер читает оба: `os.getenv("VK_SERVICE_TOKEN") or os.getenv("VK_SERVICE_TOKEN1")`.
- **Группы**: 18 групп исключены kgeu_official и rso_rt (закомментированы в `storage/posts/group_links.txt`). Метаданные групп — `storage/groups/groups_*.json`, карточки `group://<domain>` в Qdrant.

## Архитектура

- `scraper/` — сбор VK-постов → `storage/posts/posts_*.jsonl`, метаданных групп → `storage/groups/`.
- `backend/indexer/indexer.py` — JSONL → эмбеддинг + LLM-извлечение графа → Neo4j + Qdrant `posts`. `group_indexer.py` — группы в Neo4j + карточки в Qdrant.
- `backend/scripts/build_communities.py` — Louvain-кластеризация Neo4j → `storage/communities.json` (с резюме через GigaChat).
- `backend/rag/` — роутинг вопроса (struct/local/global/basic → `query_router.py`), Cypher-планировщик (`graph_planner.py`), поиск по Qdrant `posts` + карточки групп (`searcher.py`), генерация ответа (`answer_generator.py`). Интенты `units`/`commanders` важны для вопросов про отряды/контакты.
- `backend/api/routes/` — `chat` (user-ключ), `communities`, `index`, `documents` (admin-ключ), `status` (публичный). Авторизация — заголовок `X-API-Key` (ключи в `.env`: `USER_API_KEY`, `ADMIN_API_KEY`).
- `backend/graph/graph_builder.py` — вспомогательный класс (старый документный путь, `create_constraints` ставит constraint на `merge_key`).

## Рабочие потоки данных

- Посты: `storage/posts/*.jsonl` → `indexer` → Neo4j `:Entity`/`RELATES` + Qdrant `posts`.
- Сообщества: Neo4j → `build_communities.py` → `storage/communities.json` (используется для global-режима).
- Ответы: вопрос → `searcher.search()` → режим по `query_router` → источники `group://` и `vk.com` в ответе.

## Мониторинг

- Логи фоновых задач: `storage/logs/*.log` (`index_all_gigachat.log`, `build_communities.log`, `api.log`).
- Прогресс индексации: `grep -c "Processed post" storage/logs/index_all_gigachat.log`.
- Статус: `curl -s http://localhost:8000/api/v1/status`.