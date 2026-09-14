"""Тесты Milestone C (read-путь): год-фильтр, посты-источники, честные даты."""

import uuid
from unittest.mock import MagicMock

from backend.rag.answer_generator import AnswerGenerator
from backend.rag.planner_queries import query_for_plan
from backend.rag.searcher import (
    _fact_date,
    question_year,
)


class FakePoint:
    def __init__(self, pid, payload):
        self.id = pid
        self.payload = payload


class FakeQdrant:
    def __init__(self, texts):
        self.texts = texts  # url -> (text, published_at, group)

    def retrieve(self, collection_name, ids, with_payload=True, with_vectors=False):
        out = []
        for pid in ids:
            for url, (text, pub, grp) in self.texts.items():
                if str(uuid.uuid5(uuid.NAMESPACE_URL, url)) == str(pid):
                    out.append(
                        FakePoint(
                            pid,
                            {
                                "text_clean": text,
                                "published_at": pub,
                                "group_name": grp,
                            },
                        )
                    )
        return out


def test_question_year():
    assert question_year("что было в 2026 году") == "2026"
    assert question_year("с 2024 по 2026") is None
    assert question_year("кто командир") is None


def test_fact_date_priority():
    assert (
        _fact_date({"event_date": "2026-04-01", "observed_at": "2026-05-01"})
        == "2026-04-01"
    )
    assert _fact_date({"observed_at": "2026-05-01", "date": "2026-01-01"}) == "2026-05-01"
    assert _fact_date({"links": [{"date": "2025-01-01"}, {"date": "2026-06-01"}]}) == "2026-06-01"
    assert _fact_date({}) == ""


def test_fmt_facts_honest_dates():
    s = AnswerGenerator._fmt_facts(
        [
            {"person": "Марсель", "relation": "COMMANDED", "event_date": "2026-04-01",
             "observed_at": "2026-04-01"},
            {"person": "Даниил", "relation": "COMMANDED", "event_date": None,
             "observed_at": "2026-02-19"},
            {"person": "Экс", "relation": "COMMANDED", "role_status": "former",
             "observed_at": "2025-01-01"},
        ]
    )
    assert "| с 2026-04-01" in s
    assert "упоминание в посте от 2026-02-19" in s
    assert "занимает должность с" not in s
    assert "[экс/бывший]" in s


def _searcher(monkeypatch, mode, intent, rows, qtexts=None, vec_posts=None,
              plan_extra=None):
    """Мок единого пути: canned classify+plan + canned execute_v2."""
    from backend.rag import searcher as mod
    from backend.rag.query_schemas import INTENT_TO_KIND, QueryPlan

    plan = QueryPlan(
        intent=intent or "general",
        mode=mode,
        kind=INTENT_TO_KIND.get(intent or "general", "narrative"),
        org_filter=(plan_extra or {}).get("org_filter"),
        org_norm_id=(plan_extra or {}).get("org_norm_id"),
        llm_calls=1,
    )

    def _fake_classify(q, graph=None, trace_sink=None):
        # Мок пишет canned-обмен в sink — как настоящий classify через trace_sink.
        if trace_sink is not None:
            trace_sink.append(
                {
                    "messages": [
                        {"role": "system", "content": "PLAN_PROMPT"},
                        {"role": "user", "content": q},
                    ],
                    "response": '{"intent": "%s"}' % plan.intent,
                }
            )
        return plan

    monkeypatch.setattr(mod.query_planner, "classify_and_plan", _fake_classify)
    s = mod.GraphRAGSearcher()
    planner = MagicMock()
    planner._get_graph.return_value = MagicMock()
    planner.execute_v2.return_value = (
        rows, {"cypher": "MOCK CYPHER", "params": {}})
    s._planner = planner
    vec = MagicMock()
    vec.search.return_value = vec_posts or []
    vec._get_qdrant.return_value = FakeQdrant(qtexts or {})
    s._vec = vec
    gen = MagicMock()

    def _gen_side_effect(question, trace_sink=None, **kwargs):
        if trace_sink is not None:
            trace_sink.append(
                {
                    "messages": [
                        {"role": "system", "content": "ANSWER_SYS"},
                        {"role": "user", "content": question},
                    ],
                    "response": "ответ",
                }
            )
        return ("ответ", getattr(gen, "_blocks_override", {}))

    gen.generate.side_effect = _gen_side_effect
    s._answer_gen = gen
    return s, planner, vec, gen


def test_struct_uses_source_posts_no_vector(monkeypatch):
    url = "https://vk.com/rso_tesla?w=wall-1_1"
    facts = [{"person": "Иван", "relation": "COMMANDED",
              "source_post_url": url, "observed_at": "2026-03-01"}]
    s, planner, vec, gen = _searcher(
        monkeypatch, "struct", "commanders", facts,
        qtexts={url: ("Текст поста про Ивана", "2026-03-01", "Тесла")},
    )
    out = s.search("кто командует")
    vec.search.assert_not_called()  # вектора в struct с фактами нет
    gen.generate.assert_not_called()  # ответ — шаблон, 0 LLM
    assert out["answer"] == (
        "Командный состав «архив»:\n"
        "• Иван — должность не указана (упоминание от 2026-03-01)"
    )
    assert out["posts_used"] == 1
    assert out["llm_calls"] == 1


def test_struct_empty_graph_falls_back_to_vector(monkeypatch):
    s, planner, vec, gen = _searcher(
        monkeypatch, "struct", "commanders", [],
        vec_posts=[{"post_url": "u", "text": "t", "group_name": "g",
                    "published_at": "2026-01-01"}],
    )
    s.search("кто командует")
    vec.search.assert_called_once()  # граф пуст -> вектор
    kwargs = gen.generate.call_args[1]
    assert kwargs["source_posts"] == []
    assert len(kwargs["posts"]) == 1


def test_basic_year_filter(monkeypatch):
    s, planner, vec, gen = _searcher(
        monkeypatch, "basic", "general", [],
        vec_posts=[
            {"post_url": "old", "text": "t", "group_name": "g",
             "published_at": "2023-04-24"},
            {"post_url": "new", "text": "t", "group_name": "g",
             "published_at": "2026-04-20"},
        ],
    )
    s.search("как прошла школа в 2026 году")
    kwargs = gen.generate.call_args[1]
    urls = [p["post_url"] for p in kwargs["posts"]]
    assert urls == ["new"]  # п.8: пост 2023 отсечён


def test_partners_intent_query():
    q, params = query_for_plan(
        {"intent": "partners", "org_filter": "Тесла", "org_exact": None, "limit": 20}
    )
    assert "SUPPORTED_BY" in q
    assert "type(r) AS relation" in q
    assert params["org"] == "Тесла"


def test_winners_query_has_participation_union():
    q, params = query_for_plan(
        {"intent": "winners", "org_filter": "РКТ", "org_exact": None, "limit": 20}
    )
    assert "UNION" in q
    assert "PARTICIPATED_IN" in q
    # Различение побед и участий — колонкой relation.
    assert q.count("AS relation") == 2


def test_org_exact_in_commanders_query():
    q, params = query_for_plan(
        {"intent": "commanders", "org_filter": "Тесла",
         "org_exact": "штаб со кгэу тесла", "limit": 20}
    )
    # Union-форма: точные первыми, CONTAINS-фолбэк не отрезан (кейс D).
    assert "o.norm_id = $org_exact" in q
    assert "CONTAINS toLower($org)" in q
    assert params["org_exact"] == "штаб со кгэу тесла"


def test_question_year_none_for_range():
    assert question_year("с 2024 по 2026") is None


def test_generate_returns_answer_and_blocks():
    # Панель «Рентген»: generate отдаёт секции дословно как в LLM.

    class StubClient:
        def __init__(self):
            self.seen = None

        def chat(self, messages, **kwargs):
            self.seen = messages
            sink = kwargs.get("trace_sink")
            if sink is not None:
                sink.append({"messages": [dict(m) for m in messages], "response": "ответ"})
            return "ответ"

    gen = AnswerGenerator()
    stub = StubClient()
    gen._client = stub
    sink: list = []
    answer, blocks = gen.generate(
        "кто командует",
        mode="struct",
        graph_facts=[{"person": "Иван", "relation": "COMMANDED",
                      "event_date": "2026-04-01"}],
        posts=[],
        source_posts=[{"post_url": "u", "published_at": "2026-04-01",
                       "group_name": "g", "text": "текст поста"}],
        trace_sink=sink,
    )
    assert answer == "ответ"
    assert len(sink) == 1
    assert sink[0]["messages"][0]["role"] == "system"
    assert "кто командует" in sink[0]["messages"][1]["content"]
    assert sink[0]["response"] == "ответ"
    assert "ФАКТЫ ИЗ ГРАФА" in blocks["graph"]
    assert "Иван" in blocks["graph"]
    assert "ПОСТЫ-ИСТОЧНИКИ" in blocks["source_posts"]
    assert "posts" not in blocks  # пустые блоки не отдаём
    assert "communities" not in blocks
    # Системный промпт наружу не утекает — только user-контекст.
    assert len(stub.seen) == 2


def test_search_context_flag(monkeypatch):
    # include_context=False (по умолчанию) — окон нет, ответ не раздут.
    s, planner, vec, gen = _searcher(
        monkeypatch, "basic", "general", [],
        vec_posts=[{"post_url": "u", "text": "t", "group_name": "g",
                    "published_at": "2026-01-01"}],
    )
    gen._blocks_override = {"posts": "=== ПОСТЫ ===\n..."}
    out = s.search("привет")
    assert out["calls"] is None
    out2 = s.search("привет", include_context=True)
    assert [c["title"] for c in out2["calls"]] == [
        "Вызов 1 — план (v2)",
        "Вызов 2 — ответ",
    ]
    # basic: граф не трогали — в окне плана только сам план.
    assert "MOCK CYPHER" not in out2["calls"][0]["text"]
    assert '{"intent": "general"}' in out2["calls"][0]["text"]


def test_search_trace_struct(monkeypatch):
    # Окна struct: план + cypher + сырые строки графа в окне плана.
    facts = [{"person": "Иван", "relation": "COMMANDED",
              "source_post_url": "https://vk.com/x",
              "observed_at": "2026-03-01"}]
    s, planner, vec, gen = _searcher(
        monkeypatch, "struct", "commanders", facts,
    )
    gen._blocks_override = {"graph": "=== ФАКТЫ ===\n..."}
    out = s.search("кто командует", include_context=True)
    by_title = {c["title"]: c["text"] for c in out["calls"]}
    assert "MOCK CYPHER" in by_title["Вызов 1 — план (v2)"]
    assert "Иван" in by_title["Вызов 1 — план (v2)"]  # строки графа
    assert "=== SYSTEM ===" in by_title["Вызов 1 — план (v2)"]
    # Ответ — шаблон: LLM не вызывалась, окно честно говорит об этом.
    assert "=== ШАБЛОН ===" in by_title["Вызов 2 — ответ"]
    gen.generate.assert_not_called()


def test_cards_for_fact_sources():
    import json
    import tempfile
    from pathlib import Path
    from backend.rag import searcher as mod

    with tempfile.TemporaryDirectory() as tmp:
        prev, mod.GROUPS_DIR = mod.GROUPS_DIR, Path(tmp)
        try:
            (Path(tmp) / "groups_rso_tesla.json").write_text(
                json.dumps({"domain": "rso_tesla", "name": "Тесла HQ",
                            "description": "Контакты: Иван — командир"}),
                encoding="utf-8",
            )
            s = mod.GraphRAGSearcher()
            cards = s._cards_for_fact_sources(
                [{"source_post_url": "group://rso_tesla"},
                 {"links": [{"source_post_url": "https://vk.com/x"}]}]
            )
        finally:
            mod.GROUPS_DIR = prev
        assert len(cards) == 1
        assert "Иван — командир" in cards[0]["text"]
        assert cards[0]["post_url"] == "group://rso_tesla"
