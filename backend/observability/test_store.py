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


def test_search_writes_trace(tmp_path, monkeypatch):
    """Инструментированный search пишет трейс+спаны (Фаза 1)."""
    from unittest.mock import MagicMock

    from backend.rag import searcher as mod
    from backend.rag.query_schemas import QueryPlan

    monkeypatch.setenv("TESLA_TRACING_ENABLED", "1")
    monkeypatch.setenv("TESLA_TRACES_DB", str(tmp_path / "t.db"))
    monkeypatch.setattr(mod, "TRACING_ENABLED", True)
    monkeypatch.setattr(
        mod.query_planner, "classify_and_plan",
        lambda q, graph=None, trace_sink=None: QueryPlan(
            intent="general", mode="basic", kind="narrative", llm_calls=0),
    )
    s = mod.GraphRAGSearcher()
    s._planner = MagicMock()
    vec = MagicMock()
    vec.search.return_value = []
    s._vec = vec
    gen = MagicMock()
    gen.generate.return_value = ("ответ", {})
    gen.last_usage = {}
    s._answer_gen = gen
    out = s.search("привет", source="manual_test")
    assert out["answer"] == "ответ"

    from backend.observability.store import TraceStore
    store = TraceStore(tmp_path / "t.db")
    tid = store.last_trace_id()
    got = store.fetch_trace(tid)
    assert got["question"] == "привет"
    assert got["source"] == "manual_test"
    assert got["mode"] == "basic"
    assert got["prompt_version"] == "v5"
    assert {sp["name"] for sp in got["spans"]} >= {
        "classify_and_plan", "vector_search", "llm_answer"}
    store.close()


def test_judge_writes_judgement(tmp_path):
    from backend.observability.judge import judge_trace, sample_traces

    class FakeGrader:
        def grade(self, case, answer):
            assert "Эталонного ответа нет" in case["expected"]
            return {"score": 2, "reason": "достоверно"}

    s = _store(tmp_path)
    t = Trace(s, "кто такой?", source="prod")
    tid = t.finish(kind="narrative", final_answer="ответ", mode="local")
    res = judge_trace(s, tid, FakeGrader())
    assert res["faithfulness"] == 2
    # Повтор — пропуск, дублей нет.
    assert judge_trace(s, tid, FakeGrader())["skipped"] is True
    assert sample_traces(s, 5) == []
    cur = s._conn.execute(
        "SELECT faithfulness_score, relevance_score FROM judgements")
    assert cur.fetchall() == [(2, None)]
    s.close()
