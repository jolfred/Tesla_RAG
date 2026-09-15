"""Трейс одного вопроса (Фаза 1): обёртка с контекстным менеджером спанов.

Использование в searcher:
    trace = Trace(store, question, source="prod")
    with trace.span("classify_and_plan", {"question": q}) as sp:
        plan = classify_and_plan(...)
        sp.set_output(plan.to_dict(), llm_calls=plan.llm_calls)
    ...
    trace.finish(answer=..., ...)
"""

from __future__ import annotations

import time

from backend.observability.store import TraceStore


def estimate_tokens(text: str) -> int:
    """Грубая оценка токенов по длине (фолбэк, когда API не отдал usage).

    Кириллица токенизируется плотно (~3-4 символа на токен); берём
    консервативную нижнюю границу, чтобы не завышать cost.
    """
    if not text:
        return 0
    return max(1, len(text) // 4)


class _Span:
    def __init__(self, trace: "Trace", name: str, input_json=None):
        self._trace = trace
        self._name = name
        self._input = input_json
        self._output = None
        self._model = None
        self._tokens_in = None
        self._tokens_out = None
        self._t0 = time.perf_counter()

    def set_output(self, output_json=None, model: str | None = None,
                   tokens_in: int | None = None,
                   tokens_out: int | None = None) -> "_Span":
        self._output = output_json
        if model is not None:
            self._model = model
        if tokens_in is not None:
            self._tokens_in = tokens_in
        if tokens_out is not None:
            self._tokens_out = tokens_out
        return self

    def __enter__(self) -> "_Span":
        return self

    def __exit__(self, *exc) -> bool:
        latency_ms = int((time.perf_counter() - self._t0) * 1000)
        if exc[0] is not None:
            self._output = {"error": f"{exc[0].__name__}: {exc[1]}"}
        try:
            self._trace._store.add_span(
                self._trace.trace_id, self._name, self._input, self._output,
                latency_ms, self._model, self._tokens_in, self._tokens_out,
            )
        except Exception:
            pass
        return False


class Trace:
    def __init__(self, store: TraceStore | None, question: str,
                 source: str = "prod"):
        self._store = store
        self.trace_id = store.new_trace(question, source) if store else "off"
        self._t0 = time.perf_counter()
        self._tokens = 0

    @property
    def enabled(self) -> bool:
        return self._store is not None and self._store._ok

    def span(self, name: str, input_json=None) -> _Span:
        return _Span(self, name, input_json)

    def add_tokens(self, n: int) -> None:
        self._tokens += n or 0

    def set(self, **fields) -> None:
        if self.enabled:
            self._store.finish_trace(self.trace_id, **fields)

    def finish(self, **fields) -> str:
        latency_ms = int((time.perf_counter() - self._t0) * 1000)
        fields.setdefault("latency_ms", latency_ms)
        fields.setdefault("total_tokens", self._tokens or None)
        if self.enabled:
            self._store.finish_trace(self.trace_id, **fields)
        return self.trace_id
