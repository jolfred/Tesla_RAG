"""Тесты Фазы 0: стор трейсов, Trace-спаны, quality_log на сторе."""

from backend.observability.store import TraceStore
from backend.observability.tracing import Trace, estimate_tokens


def _store(tmp_path):
    return TraceStore(tmp_path / "traces.db")


def test_trace_roundtrip(tmp_path):
    s = _store(tmp_path)
    t = Trace(s, "кто командир?", source="manual_test")
    with t.span("classify_and_plan", {"q": "кто командир?"}) as sp:
        sp.set_output({"intent": "commanders"}, model="GigaChat",
                      tokens_in=100, tokens_out=20)
    t.add_tokens(120)
    tid = t.finish(intent="commanders", mode="struct",
                   prompt_version="v5", total_llm_calls=1)
    got = s.fetch_trace(tid)
    assert got["question"] == "кто командир?"
    assert got["source"] == "manual_test"
    assert got["total_tokens"] == 120
    assert got["prompt_version"] == "v5"
    assert len(got["spans"]) == 1
    assert got["spans"][0]["name"] == "classify_and_plan"
    assert got["spans"][0]["tokens_in"] == 100
    s.close()


def test_span_error_recorded(tmp_path):
    s = _store(tmp_path)
    t = Trace(s, "q")
    try:
        with t.span("cypher_exec", {"q": "MATCH"}):
            raise RuntimeError("boom")
    except RuntimeError:
        pass
    got = s.fetch_trace(t.trace_id)
    assert "boom" in got["spans"][0]["output_json"]
    s.close()


def test_quality_log_table(tmp_path):
    s = _store(tmp_path)
    s.log_quality("???", "resolve_org", "Тесла")
    cur = s._conn.execute("SELECT question, stage FROM quality_log")
    assert cur.fetchall() == [("???", "resolve_org")]
    s.close()


def test_last_trace_id(tmp_path):
    s = _store(tmp_path)
    assert s.last_trace_id() is None
    t1 = Trace(s, "первый")
    t1.finish()
    t2 = Trace(s, "второй")
    t2.finish()
    assert s.last_trace_id() == t2.trace_id
    assert s.fetch_trace("нет-такого") is None
    s.close()


def test_estimate_tokens():
    assert estimate_tokens("") == 0
    assert estimate_tokens("привет мир") == 2
    assert estimate_tokens("x" * 400) == 100


def test_quality_module_uses_store(tmp_path, monkeypatch):
    from backend.rag import quality_log as ql

    monkeypatch.setattr(ql, "_store", _store(tmp_path))
    ql.log_zero_result("q?", "classify", "d")
    cur = ql._store._conn.execute("SELECT COUNT(*) FROM quality_log")
    assert cur.fetchone()[0] == 1
    ql._store.close()
    monkeypatch.setattr(ql, "_store", None)
