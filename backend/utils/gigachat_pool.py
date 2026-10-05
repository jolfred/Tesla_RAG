"""Пул из 2 GigaChat-клиентов (по ключу). Round-robin + fallback на 429/5xx."""
import itertools
import threading

from backend.config import GIGACHAT_AUTH_KEY, GIGACHAT_AUTH_KEY_2
from backend.utils.gigachat_client import GigaChatClient


class GigaChatPool:
    def __init__(self):
        keys = [k for k in (GIGACHAT_AUTH_KEY, GIGACHAT_AUTH_KEY_2) if k]
        if not keys:
            raise RuntimeError("Нет GIGACHAT_AUTH_KEY")
        self._clients = [GigaChatClient(auth_key=k) for k in keys]
        self._cycle = itertools.cycle(self._clients)
        self._lock = threading.Lock()

    @property
    def size(self) -> int:
        return len(self._clients)

    def _next(self) -> GigaChatClient:
        with self._lock:
            return next(self._cycle)

    def chat(self, messages: list[dict], **kwargs) -> str:
        last_err = None
        # пробуем каждого клиента по очереди (fallback при rate-limit/сбое)
        for _ in range(self.size):
            cli = self._next()
            try:
                return cli.chat(messages, **kwargs)
            except Exception as e:
                msg = str(e).lower()
                if "429" in msg or "rate" in msg or "503" in msg or "502" in msg:
                    last_err = e
                    continue
                raise
        raise last_err  # type: ignore[misc]
