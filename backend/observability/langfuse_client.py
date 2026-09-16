"""Обёртка Langfuse SDK v4 (self-host :3000).

Правила:
- Best-effort: недоступность Langfuse никогда не роняет ответ. Все вызовы
  обёрнуты, при выключенном/упавшем Langfuse наблюдения — no-op.
- Токены — источник истины всегда (usage_details). Cost в built-in поле
  пишется ТОЛЬКО для моделей с однозначной валютой (ProxyAPI, USD).
  GigaChat (рубли) — отдельным custom-Score `cost_rub`, чтобы графики
  Langfuse не врали суммированием разных валют. Тарифов пока нет ни для
  кого — cost везде None, токены считаются.
"""
from __future__ import annotations

import os
from contextlib import contextmanager
from typing import Any

from backend.utils.logger import setup_logger

logger = setup_logger("langfuse_client")

try:  # CLI-скрипты работают вне API, где .env уже загружен
    from dotenv import load_dotenv

    load_dotenv()
except Exception:
    pass

COST_RUB_SCORE = "cost_rub"


def _rate(name: str) -> float | None:
    try:
        v = os.getenv(name)
        return float(v) if v else None
    except (TypeError, ValueError):
        return None


def generation_cost(usage: dict | None,
                    model: str | None) -> tuple[dict | None,
                                                tuple[str, float] | None]:
    """(cost_details, rub_score) для generation-наблюдения.

    Тарифы — только из env (не выдумываем):
      GIGACHAT_RUB_PER_1K_IN / _OUT — GigaChat, рубли → custom-Score;
      PROXYAPI_USD_PER_1K_IN / _OUT — ProxyAPI, доллары → built-in cost.
    Не заданы — (None, None), cost не пишем, токены остаются истиной.
    """
    if not usage:
        return None, None
    m = (model or "").lower()
    tin = usage.get("input", 0) or 0
    tout = usage.get("output", 0) or 0
    if "gigachat" in m:
        rin, rout = _rate("GIGACHAT_RUB_PER_1K_IN"), _rate("GIGACHAT_RUB_PER_1K_OUT")
        if rin is None and rout is None:
            return None, None
        rub = tin / 1000 * (rin or 0) + tout / 1000 * (rout or 0)
        return None, (COST_RUB_SCORE, rub)
    rin, rout = _rate("PROXYAPI_USD_PER_1K_IN"), _rate("PROXYAPI_USD_PER_1K_OUT")
    if rin is None and rout is None:
        return None, None
    return ({"input": tin / 1000 * (rin or 0),
             "output": tout / 1000 * (rout or 0)}, None)

_client = None
_client_failed = False


def is_enabled() -> bool:
    return os.getenv("LANGFUSE_ENABLED", "0") == "1"


def get_langfuse():
    """Синглтон Langfuse-клиента; None — выключен/не настроен/упал."""
    global _client, _client_failed
    if _client is not None:
        return _client
    if _client_failed or not is_enabled():
        return None
    try:
        from langfuse import get_client

        c = get_client()
        if not c.auth_check():
            raise RuntimeError("auth_check failed")
        _client = c
        return _client
    except Exception as e:
        logger.warning("Langfuse недоступен, трейсинг выключен: %s", e)
        _client_failed = True
        return None


def estimate_tokens(text: str | None) -> int:
    return max(0, len(text or "") // 4)


def usage_details(
    last_usage: dict | None,
    prompt_text: str | None = None,
    completion_text: str | None = None,
) -> dict[str, int]:
    """usage_details для generation: серверный usage или грубая оценка."""
    if last_usage:
        try:
            return {
                "input": int(last_usage.get("input", 0) or 0),
                "output": int(last_usage.get("output", 0) or 0),
            }
        except Exception:
            pass
    return {
        "input": estimate_tokens(prompt_text),
        "output": estimate_tokens(completion_text),
    }


class _NoopObs:
    def update(self, *a: Any, **k: Any) -> None:
        pass


@contextmanager
def observation(name: str, as_type: str = "span", **kwargs):
    """Контекст наблюдения; no-op при недоступном Langfuse.

    Использование:
        with observation("cypher_exec", as_type="retriever", input=q) as sp:
            ...
            sp.update(output=facts)
    """
    lf = get_langfuse()
    if lf is None:
        yield _NoopObs()
        return
    try:
        with lf.start_as_current_observation(
            name=name, as_type=as_type, **kwargs
        ) as obs:
            yield obs
    except Exception as e:
        logger.warning("Langfuse observation %s упало: %s", name, e)
        yield _NoopObs()


def current_trace_id() -> str | None:
    lf = get_langfuse()
    if lf is None:
        return None
    try:
        return lf.get_current_trace_id()
    except Exception:
        return None


def score(
    trace_id: str | None,
    name: str,
    value: float | bool,
    data_type: str = "BOOLEAN",
    comment: str | None = None,
) -> None:
    """Score на трейс (Слой 1, судья, cost_rub). Best-effort."""
    if not trace_id:
        return
    lf = get_langfuse()
    if lf is None:
        return
    try:
        lf.create_score(
            trace_id=trace_id,
            name=name,
            value=value,
            data_type=data_type,
            comment=comment,
        )
    except Exception as e:
        logger.warning("Langfuse score %s упало: %s", name, e)


def flush() -> None:
    lf = get_langfuse()
    if lf is None:
        return
    try:
        lf.flush()
    except Exception as e:
        logger.warning("Langfuse flush упал: %s", e)
