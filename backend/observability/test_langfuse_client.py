"""Трейсинг выключен (conftest LANGFUSE_ENABLED=0): всё no-op, ответы живы."""
from backend.observability import langfuse_client as lf


def test_disabled_client_is_none():
    assert lf.get_langfuse() is None
    assert lf.current_trace_id() is None


def test_observation_noop():
    with lf.observation("x", input="y") as sp:
        sp.update(output="z")  # не должно падать


def test_score_and_flush_noop():
    lf.score("nope", "date_groundedness", True)
    lf.flush()


def test_usage_details_fallback_estimate():
    u = lf.usage_details(None, prompt_text="1234", completion_text="12")
    assert u == {"input": 1, "output": 0}


def test_usage_details_server_first():
    u = lf.usage_details({"input": 10, "output": 5}, "x", "y")
    assert u == {"input": 10, "output": 5}


def test_generation_cost_no_tariffs(monkeypatch):
    for v in ("GIGACHAT_RUB_PER_1K_IN", "GIGACHAT_RUB_PER_1K_OUT",
              "PROXYAPI_USD_PER_1K_IN", "PROXYAPI_USD_PER_1K_OUT"):
        monkeypatch.delenv(v, raising=False)
    assert lf.generation_cost({"input": 10, "output": 5},
                              "GigaChat-3-Ultra") == (None, None)
    assert lf.generation_cost(None, "GigaChat-3-Ultra") == (None, None)


def test_generation_cost_rub(monkeypatch):
    monkeypatch.setenv("GIGACHAT_RUB_PER_1K_IN", "1.0")
    monkeypatch.setenv("GIGACHAT_RUB_PER_1K_OUT", "2.0")
    cost, rub = lf.generation_cost({"input": 1000, "output": 500},
                                   "GigaChat-3-Ultra")
    assert cost is None
    assert rub == ("cost_rub", 2.0)


def test_generation_cost_usd(monkeypatch):
    monkeypatch.setenv("PROXYAPI_USD_PER_1K_IN", "1.0")
    monkeypatch.setenv("PROXYAPI_USD_PER_1K_OUT", "2.0")
    cost, rub = lf.generation_cost({"input": 1000, "output": 500},
                                   "text-embedding-3-small")
    assert rub is None
    assert cost == {"input": 1.0, "output": 1.0}
