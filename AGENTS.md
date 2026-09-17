# AGENTS.md

GraphRAG-сервис для Штаба СО КГЭУ «Тесла». VK-посты → граф (Neo4j) + векторный индекс (Qdrant) → Louvain-сообщества → ответы через GigaChat. Работает только с серверами Docker (`docker compose up -d qdrant neo4j`); Python-venv в `.venv`.

## GitHub (обязательно)

- Источник истины — GitHub. Код всегда брать оттуда (`git pull`), не из локальных копий вслепую.
- Пуш — только в `upstream` = `git@github.com:jolfred/Tesla_RAG` (SSH). `origin` — тот же репозиторий по HTTPS, для пуша не использовать.
- Рабочий цикл: изменение → коммит → `git push` сразу → деплой на сервер. Пользователь проверяет всё через GitHub.
- Активная ветка лендинга — `gid-web`. Перед пушем: `git status`, `git diff --stat`; секреты (`.env`) не коммитить.

## Команды

```bash
# API (порт 8000)
.venv/bin/python -m uvicorn backend.main:app --host 0.0.0.0 --port 8000

# Индексация постов в Neo4j + Qdrant (ресюм: пропускает уже проиндексированные)
.venv/bin/python -m backend.indexer.indexer storage/posts/posts_*.jsonl --model gigachat --min-date ''

# Индексация v2 через LLMGraphTransformer (онтология v2, source_model='llmgraph_gigachat',
# настоящие метки :Person/:Squad/..., рёбра настоящими типами, provenance из кода).
# --force в v2-режиме делает resume по :Post-узлам графа (не пережигает GigaChat).
.venv/bin/python -m backend.indexer.indexer storage/posts/posts_rso_tesla.jsonl --model gigachat --min-date 2026-01-01 --extractor transformer --force

# Метрики ветки графа (legacy=gigachat, v2=llmgraph_gigachat)
.venv/bin/python -m backend.scripts.pilot_metrics --model llmgraph_gigachat

# Сид метаданных групп в граф v2 (HQ/отряды/контакты + Qdrant-карточки, идемпотентно)
.venv/bin/python -m backend.indexer.group_indexer_v2

# Фоновый запуск (без setsid процесс умирает вместе с терминалом!)
setsid nohup .venv/bin/python -m backend.indexer.indexer $(ls storage/posts/posts_*.jsonl | grep -v kgeu_official | tr '\n' ' ') --model gigachat --min-date '' > storage/logs/index_all_gigachat.log 2>&1 < /dev/null & disown

# Сообщества (медленно: 1 запрос GigaChat на сообщество, ~890 шт)
.venv/bin/python -m backend.scripts.build_communities

# Тесты (моковые, сервисы не нужны)
.venv/bin/python -m pytest backend/indexer/test_indexer.py

# Регресс RAG-ответов (нужны Neo4j + Qdrant + GigaChat + Langfuse;
# golden-источник backend/rag/golden_set.yaml, прогоны — Experiment API)
.venv/bin/python -m backend.scripts.run_regression
# подмножество кейсов: --ids commanders_hq,units_tesla
# exit 1 при провале (для CI).
# Пул вопросов (24 шт, мягкая оценка: Слой 1 + судья в UI):
.venv/bin/python -m backend.scripts.run_regression --dataset question-pool --yaml backend/rag/question_pool.yaml --soft
# импорт наборов: import_golden_to_langfuse.py [--source ... --dataset ...]

# Скрапер (метаданные групп и посты VK)
.venv/bin/python -m scraper.main --url-file storage/posts/group_links.txt --meta

# Фронтенд (сборка ТОЛЬКО через Docker, Node на хосте не ставится)
docker run --rm -v $PWD/frontend:/app -v graphrag_npm_cache:/root/.npm -w /app node:20-alpine sh -c "npm ci && npm run build"
# ВАЖНО: после правки package.json сначала `npm install` (перегенерить lock), иначе `npm ci` падает.
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
  - `POST /api/v1/auth/vk {params, sign}` → VK-вход с проверкой подписи launch-параметров (HMAC-SHA256 на `VK_APP_SECRET`, официальный алгоритм VK) + контроль `vk_app_id` == `VK_APP_ID`; роль по allowlist `VK_ADMIN_IDS`; при пустом секрете → 501. Активен (секрет задан), фолбэк фронта на гостя при 401/501.
- **Запуск в VK Mini App**: раздел «Настройки → Общие → Размещение» в dev.vk.com: поле **URL** — production-адрес приложения (публичный HTTPS), **Режим разработки** — адрес версии для администраторов (можно `http://localhost:8000` для теста в десктопном VK). VK грузит приложение в iframe с launch-параметрами (`?vk_user_id=...&sign=...`), фронт сам делает `VKWebAppInit` → `POST /auth/vk`. Production без публичного HTTPS-адреса (туннель ngrok/cloudflared на :8000 или сервер) на мобильных клиентах не заработает.
- **Фронтенд**: `frontend/` (Vite + React + TS + VKUI + vk-bridge). Сборка только через Docker (`npm ci && npm run build`), готовая статика в `frontend/dist/`. FastAPI раздаёт `/assets/*` и отдаёт `index.html` для не-API GET-путей (SPA-fallback); `/api/*`, `/docs`, `/openapi.json`, `/redoc` не перехватываются. Собранную статику в docker-compose можно смонтировать: `./frontend/dist:/app/frontend/dist`.
- **Лендинг (ветка `gid-web`, дефолтный экран)**: `frontend/src/landing/` — `LandingPage.tsx` (Hero + секции + CTA), `AiLetopis.tsx` (RAG-виджет через `api.chat`), `MagneticField.tsx` (WebGL-шейдер «магнитное поле», тихий fallback без WebGL), `data.ts` (контент + импорты логотипов из `src/assets/logos/`, ресайз 512px). Стек: Tailwind 3 (`preflight: false`, чтобы не ломать VKUI) + framer-motion. Старые `ChatPage/StatusPage` лежат в `src/pages/` как файлы, в роутинге не участвуют.
- **Модуль аутентификации фронта**: `frontend/src/auth/` (authContext + `localStorage`), `frontend/src/api/client.ts` (Bearer-инжекция + авто-перевыдача гостя при 401), `frontend/src/types.ts` (единый источник истины контрактов API). Экраны: Чат (`src/pages/ChatPage.tsx`), Статус (`src/pages/StatusPage.tsx`, вход/выход админа).
- **Новые переменные .env**: `SESSION_TTL` (30), `VK_APP_ID` (задан), `VK_APP_SECRET` (задан → VK-вход активен; пусто → неактивен, 501), `VK_ADMIN_IDS` (CSV).
- **Тесты M1**: `backend/api/test_sessions.py`, `backend/api/test_auth.py` (вкл. тест-векторы VK sign, Bearer vs X-API-Key на `/chat`). Админ-роуты (`documents/index/communities`) по-прежнему только X-API-Key; Bearer-зависимость `verify_admin_session` готова к M2.

## Критические нюансы

- **Два разных Qdrant.** В `.env` `QDRANT_MODE=local`, но **индексатор и `vec_search.py` ходят в серверный Qdrant на порту 6333 напрямую** (коллекция `posts`), игнорируя `QDRANT_MODE`. Локальный `storage/qdrant_db` (коллекция `tesla_knowledge`, виден в `/api/v1/status`) использует только старый `backend/embeddings/qdrant_client.py` — не трогай его за состояние RAG.
- **Эмбеддинги индексатора и поиска**: `text-embedding-3-small` через ProxyAPI, а НЕ через sentence-transformers. `backend/embeddings/model.py` использует ленивый импорт sentence-transformers (пакет не установлен) — не вызывай этот путь.
- **Neo4j — Community edition**, мульти-БД недоступна. Схема «двух моделей»: сущности/рёбра имеют `source_model` + композитный уникальный ключ `merge_key = "{source_model}::{id}"` (constraint на `merge_key`, не на `id`). Сейчас живые данные `source_model='llmgraph_gigachat'` (v2-граф, ~296 узлов); legacy `gigachat` и Gemma-ветка заморожены.
- **Индексатор**: `--model gigachat|gemma|proxyapi`, `--min-date ''` = все годы. Пропускает посты с пустым `text_clean` (посты-картинки с одними хэштегами) — это ожидаемо, не баг. `--parallel` только для gemma.
- **GigaChat**: OAuth через `ngw.devices.sberbank.ru` с `verify=False`; клиент `backend/utils/gigachat_client.py`; таймаут 120с (дефолтный 600с вешал процесс). Модель: `GigaChat-3-Ultra` (`GIGACHAT_MODEL`). `LLM_PROVIDER` в `answer_generator.py` = `gigachat`.
- **VK-токен**: в `.env` реальный ключ лежит в `VK_SERVICE_TOKEN1` (`VK_SERVICE_TOKEN` пустой); скрапер читает оба: `os.getenv("VK_SERVICE_TOKEN") or os.getenv("VK_SERVICE_TOKEN1")`.
- **Группы**: 18 групп исключены kgeu_official и rso_rt (закомментированы в `storage/posts/group_links.txt`). Метаданные групп — `storage/groups/groups_*.json`, карточки `group://<domain>` в Qdrant.

## Архитектура

- `scraper/` — сбор VK-постов → `storage/posts/posts_*.jsonl`, метаданных групп → `storage/groups/`.
- `backend/indexer/indexer.py` — JSONL → эмбеддинг + LLM-извлечение графа → Neo4j + Qdrant `posts`. `group_indexer.py` — группы в Neo4j + карточки в Qdrant.
- `backend/scripts/build_communities.py` — Louvain-кластеризация Neo4j → `storage/communities.json` (с резюме через GigaChat).
- `backend/rag/` — единый путь: `query_planner.classify_and_plan` (1 LLM-вызов: интент+слоты) → строгий Cypher (`graph_planner.execute_v2` + `planner_queries.query_for_plan_v2`) → диспетчер `searcher` (enumerable — детерминированный шаблон `renderers`, 0 LLM; иначе LLM-ответ). Интенты `units`/`commanders` важны для вопросов про отряды/контакты.
- `backend/api/routes/` — `chat` (user-ключ), `communities`, `index`, `documents` (admin-ключ), `status` (публичный). Авторизация — заголовок `X-API-Key` (ключи в `.env`: `USER_API_KEY`, `ADMIN_API_KEY`).
- `backend/graph/graph_builder.py` — вспомогательный класс (старый документный путь, `create_constraints` ставит constraint на `merge_key`).

## Рабочие потоки данных

- Посты: `storage/posts/*.jsonl` → `indexer` → Neo4j `:Entity`/`RELATES` + Qdrant `posts`.
- Сообщества: Neo4j → `build_communities.py` → `storage/communities.json` (используется для global-режима).
- Ответы: вопрос → `searcher.search()` → план (`query_planner`) → источники `group://` и `vk.com` в ответе.

## Деплой лендинга (ВМ Кирилла, фронт-only)

- ВМ: `jolfred@192.168.10.160` (Ubuntu 24.04, 1 CPU, ~576МБ RAM — хватает только на статику). SSH-ключ каждый раз даёт пользователь (файл, `chmod 600`); приватные ключи в чат не вставлять повторно, в репозиторий не класть.
- Схема: на ВМ только nginx + собранный `frontend/dist`; RAG-стек (API:8000, Neo4j, Qdrant) и Langfuse остаются здесь. Секреты на ВМ не везти.
- Перед ВМ стоит HAProxy Кирилла: шлёт `sotesla-jolfred.deagly.tech` → `:80` с `send-proxy-v2`, сертификат терминирует балансировщик. Поэтому в nginx обязательно `listen 80 proxy_protocol` + `real_ip_header proxy_protocol`, иначе ляжет и трафик, и хелсчек. `/api/` → `proxy_pass` сюда (таймаут ≥120с под GigaChat), `/` → статика, gzip вкл.
- Риск: если хелсчек балансировщика идёт без PROXY-заголовка — просить у Кирилла `check-send-proxy` (его сторона, одна строка).
- Проверка: вопрос ИИ-Летописи end-to-end через домен + логи nginx и `storage/logs/api.log`.

## Мониторинг

- Логи фоновых задач: `storage/logs/*.log` (`index_all_gigachat.log`, `build_communities.log`, `api.log`).
- Прогресс индексации: `grep -c "Processed post" storage/logs/index_all_gigachat.log`.
- Статус: `curl -s http://localhost:8000/api/v1/status`.

## Наблюдаемость (Langfuse, self-host :3000)

- Стек: `docker compose -f docker-compose.langfuse.yml up -d` (web+worker+postgres+clickhouse+minio+redis, тома `lf_*`). UI: `http://localhost:3000`. Ключи создаются headless-инициализацией, лежат в `.env` (`LANGFUSE_*`, gitignored).
- Критично: `LANGFUSE_MIGRATION_V4_WRITE_MODE=dual` (дефолт `events_only` не пишет legacy-таблицы — public API пуст); S3-region `us-east-1` (иначе 500 на ingest). SDK `langfuse==4.15.3`, API v4: `create_score` (не `score`), `as_type="retriever"` напрямую.
- Код: `backend/observability/langfuse_client.py` (best-effort синглтон; токены — истина, GigaChat cost только Score `cost_rub`), `checks.py` (Слой 1 → Score), `judge.py` (LLMGrader → `faithfulness_llm`, только с эталоном), инструментация в `searcher.py` (answer/classify/cypher/vector/llm), `trace_id` в `ChatResponse`.
- Регресс: `backend/rag/golden_set.yaml` (источник истины) → `scripts/import_golden_to_langfuse.py` → Dataset `regression-golden-set` → `scripts/run_regression.py` (Experiment API, exit 1 при провале).
- Алерты: `scripts/check_langfuse_alerts.py` (exit 2; фильтр traceId API игнорирует — джойн в питоне; доставка в канал снаружи).
- Тесты: `conftest.py` гасит Langfuse (`LANGFUSE_ENABLED=0`), иначе `.env` полезет в живой сервер.
- Рестарт API: `scripts/restart_api.sh` (PID-файл; `pkill -f` убивает собственный шелл).
- Cost: только из env (`GIGACHAT_RUB_PER_1K_IN/_OUT`, `PROXYAPI_USD_PER_1K_IN/_OUT`); не заданы — только токены.