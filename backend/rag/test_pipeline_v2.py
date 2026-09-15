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
    gen.answer_entity_detail.return_value = ("структура\n\nпроза", {})
    s._answer_gen = gen
    return s, gen


def _cmd_plan(**kw):
    base = dict(intent="commanders", mode="struct", kind="enumerable",
                org_filter="Тесла", org_norm_id=HQ, limit=20, llm_calls=1)
    base.update(kw)
    return QueryPlan(**base)


def test_v2_commanders_narrative_style(monkeypatch):
    """Комсостав — стиль Летописи: блок фактов + нарратив, не сухое перечисление."""
    s, gen = _v2_searcher(monkeypatch, _cmd_plan(), ROWS)
    gen.answer_entity_detail.return_value = ("структура\n\nпроза", {})
    out = s.search("Кто в комсоставе штаба Тесла?", include_context=True)
    assert out["answer"] == "структура\n\nпроза"
    gen.generate.assert_not_called()
    structured = gen.answer_entity_detail.call_args[0][1]
    # Факты детерминированы и ранжированы: комиссар (ранг 1) выше
    # «Руководителя» без «командир» (ранг 4).
    assert structured.startswith("Командный состав «Тесла»:\n• Альфред Шарифуллин")
    assert "Даниил Астафьев" in structured
    assert out["llm_calls"] == 1  # мок в sink не пишет
    assert [c["title"] for c in out["calls"]] == [
        "Вызов 1 — план (v2)", "Вызов 2 — ответ"]
    assert "STRICT CYPHER" in out["calls"][0]["text"]
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


def test_router_module_removed():
    """Cutover: роутера больше нет — единый путь, откат только git'ом."""
    import pytest

    assert not hasattr(mod.GraphRAGSearcher, "_get_router")
    with pytest.raises(ImportError):
        import backend.rag.query_router  # noqa: F401


def test_rule16_in_narrative_prompt():
    from backend.rag.answer_generator import NARRATIVE_PROMPT
    assert "связанные сообщества" in NARRATIVE_PROMPT
    assert "PART_OF" in NARRATIVE_PROMPT


def test_answer_entity_detail_joins_blocks():
    from backend.rag.answer_generator import AnswerGenerator

    class StubClient:
        def __init__(self):
            self.seen = None

        def chat(self, messages, **kwargs):
            self.seen = messages
            sink = kwargs.get("trace_sink")
            if sink is not None:
                sink.append({"messages": [dict(m) for m in messages],
                             "response": "проза"})
            return "проза"

    gen = AnswerGenerator()
    stub = StubClient()
    gen._client = stub
    answer, blocks = gen.answer_entity_detail(
        "Кто такой Даниил Астафьев?",
        "«Даниил Астафьев»:\n• Руководитель — Штаб",
        [{"post_url": "u", "published_at": "2026-01-01",
          "group_name": "g", "text": "текст"}],
    )
    assert answer.startswith("«Даниил Астафьев»:\n• Руководитель — Штаб")
    assert answer.endswith("проза")
    assert "16." in stub.seen[0]["content"]  # правило 16 ушло в модель
    assert set(blocks) == {"structured", "posts"}


def test_person_roles_query_shape():
    from backend.rag.planner_queries import person_roles_query
    q, params = person_roles_query("Астафьев")
    assert "o.name AS org" in q and params["name"] == "Астафьев"
    assert person_roles_query("") is None


def test_v2_entity_detail_path(monkeypatch):
    plan = QueryPlan(intent="entity_detail", mode="local", kind="narrative",
                     target_name="Астафьев", llm_calls=1)
    monkeypatch.setattr(
        mod.query_planner, "classify_and_plan",
        lambda q, graph=None, trace_sink=None: plan,
    )
    s = mod.GraphRAGSearcher()
    planner = MagicMock()
    graph = MagicMock()
    graph.search_cypher.return_value = [
        {"person": "Даниил Астафьев", "org": "Штаб СО КГЭУ «Тесла»",
         "role_title": "Руководитель", "relation": "COMMANDED",
         "event_date": "2026-04-01"},
    ]
    planner._get_graph.return_value = graph
    s._planner = planner
    vec = MagicMock()
    vec.search.return_value = []
    vec._get_qdrant.side_effect = RuntimeError("no qdrant")
    s._vec = vec
    gen = MagicMock()
    gen.answer_entity_detail.return_value = ("структура\n\nпроза", {})
    s._answer_gen = gen
    out = s.search("Кто такой Даниил Астафьев?", include_context=True)
    assert out["mode"] == "local" and out["facts_count"] == 1
    assert out["answer"] == "структура\n\nпроза"
    structured = gen.answer_entity_detail.call_args[0][1]
    assert structured.startswith("«Даниил Астафьев»:")
    assert "Руководитель — Штаб СО КГЭУ «Тесла»" in structured
    assert out["llm_calls"] == 1
    assert [c["title"] for c in out["calls"]] == [
        "Вызов 1 — план (v2)", "Вызов 2 — ответ"]
