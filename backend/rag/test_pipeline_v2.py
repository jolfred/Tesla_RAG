"""Тесты Фазы 4/6: путь v2 в searcher (диспетчер, fallback, метрика)."""

from unittest.mock import MagicMock

from backend.rag import searcher as mod
from backend.rag.query_schemas import QueryPlan


HQ = "штаб со кгэу тесла"
ROWS = [
    {"person": "Даниил Астафьев", "role_title": "Руководитель",
     "relation": "COMMANDED", "event_date": "2026-04-01",
     "observed_at": "2026-04-01"},
    {"person": "Альфред Шарифуллин", "role_title": "Комиссар",
     "relation": "COMMANDED", "observed_at": "2026-02-19"},
]


def _v2_searcher(monkeypatch, plan, rows, vec_posts=None):
    monkeypatch.setattr(mod, "QUERY_PIPELINE_VERSION", "v2")
    monkeypatch.setattr(
        mod.query_planner, "classify_and_plan",
        lambda q, graph=None, trace_sink=None: plan,
    )
    s = mod.GraphRAGSearcher()
    planner = MagicMock()
    planner._get_graph.return_value = MagicMock()
    planner.execute_v2.return_value = (
        rows, {"cypher": "STRICT CYPHER", "params": {"org_norm_id": HQ}})
    s._planner = planner
    vec = MagicMock()
    vec.search.return_value = vec_posts or []
    vec._get_qdrant.side_effect = RuntimeError("no qdrant in unit test")
    s._vec = vec
    gen = MagicMock()
    gen.generate.return_value = ("llm-ответ", {})
    s._answer_gen = gen
    return s, gen


def _cmd_plan(**kw):
    base = dict(intent="commanders", mode="struct", kind="enumerable",
                org_filter="Тесла", org_norm_id=HQ, limit=20, llm_calls=1)
    base.update(kw)
    return QueryPlan(**base)


def test_v2_template_no_llm_answer(monkeypatch):
    s, gen = _v2_searcher(monkeypatch, _cmd_plan(), ROWS)
    out = s.search("Кто в комсоставе штаба Тесла?", include_context=True)
    assert out["answer"] == (
        "Командный состав «Тесла»:\n"
        "• Даниил Астафьев — Руководитель (с 2026-04-01)\n"
        "• Альфред Шарифуллин — Комиссар (упоминание от 2026-02-19)"
    )
    gen.generate.assert_not_called()
    assert out["llm_calls"] == 1  # только classify+plan
    assert [c["title"] for c in out["calls"]] == [
        "Вызов 1 — план (v2)", "Вызов 2 — ответ"]
    assert "STRICT CYPHER" in out["calls"][0]["text"]
    assert "=== ШАБЛОН ===" in out["calls"][1]["text"]
    assert out["mode"] == "struct" and out["facts_count"] == 2


def test_v2_empty_graph_and_vec_silence_without_llm(monkeypatch):
    s, gen = _v2_searcher(monkeypatch, _cmd_plan(), [])
    out = s.search("Кто в комсоставе штаба Тесла?")
    assert out["answer"] == "В архивах нет данных"
    gen.generate.assert_not_called()
    assert out["calls"] is None


def test_v2_empty_graph_with_vec_falls_back_to_llm(monkeypatch):
    vec_posts = [{"post_url": "https://vk.com/x", "published_at": "2026-01-01",
                  "group_name": "g", "text": "текст"}]
    s, gen = _v2_searcher(monkeypatch, _cmd_plan(), [], vec_posts=vec_posts)
    out = s.search("Кто в комсоставе штаба Тесла?")
    assert out["answer"] == "llm-ответ"
    gen.generate.assert_called_once()
    assert out["llm_calls"] == 1  # generate-мок в sink не пишет


def test_v2_narrative_path_uses_llm(monkeypatch):
    plan = QueryPlan(intent="general", mode="basic", kind="narrative", llm_calls=1)
    s, gen = _v2_searcher(monkeypatch, plan, [], vec_posts=[])
    out = s.search("Расскажи что-нибудь")
    assert out["answer"] == "llm-ответ"
    assert out["mode"] == "basic"


def test_v1_default_unaffected(monkeypatch):
    """Флаг по умолчанию v1: _search_v2 не вызывается."""
    import backend.config as cfg
    assert cfg.QUERY_PIPELINE_VERSION == "v1"
    s = mod.GraphRAGSearcher()
    called = []
    s._search_v2 = lambda *a, **k: called.append(True) or {}
    s._router = MagicMock()
    s._router.route.return_value = "basic"
    vec = MagicMock()
    vec.search.return_value = []
    s._vec = vec
    gen = MagicMock()
    gen.generate.return_value = ("a", {})
    s._answer_gen = gen
    # QUERY_PIPELINE_VERSION в модуле searcher — v1
    assert mod.QUERY_PIPELINE_VERSION == "v1"
    s.search("привет")
    assert called == []
