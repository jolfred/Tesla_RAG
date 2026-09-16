import os

# Тесты не ходят в живой Langfuse: ответы должны строиться без трейсинга.
os.environ["LANGFUSE_ENABLED"] = "0"
