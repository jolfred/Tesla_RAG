import os
import tempfile

# Тесты не ходят в живой Langfuse: ответы должны строиться без трейсинга.
os.environ["LANGFUSE_ENABLED"] = "0"
# Тесты не ходят в живой GigaChat: wiki-first сразу делает fallback в моки.
os.environ["TESLA_WIKI_ENABLED"] = "0"
# Unit/API tests must never consume queued source-collection jobs.
os.environ["TESLA_OPERATIONS_WORKER"] = "0"
# Тесты не трогают боевую admin.db: промпты читаются с дефолтов кода.
os.environ.setdefault(
    "TESLA_ADMIN_DB",
    os.path.join(tempfile.mkdtemp(prefix="tesla_test_"), "admin.db"),
)
os.environ.setdefault(
    "TESLA_SESSIONS_DB",
    os.path.join(tempfile.mkdtemp(prefix="tesla_sessions_test_"), "sessions.db"),
)
