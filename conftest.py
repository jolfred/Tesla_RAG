"""Тестовое окружение: трейсинг в файл storage/traces.db выключен,
чтобы моковые тесты не писали мусор в продовый стор."""

import os

os.environ.setdefault("TESLA_TRACING_ENABLED", "0")
