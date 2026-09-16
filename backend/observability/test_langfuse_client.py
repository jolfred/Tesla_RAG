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
