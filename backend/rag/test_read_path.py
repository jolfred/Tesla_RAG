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


def _searcher(router_mode, plan, facts, qtexts=None, vec_posts=None):
    from backend.rag import searcher as mod

    s = mod.GraphRAGSearcher()
    s._router = MagicMock()
    s._router.route.return_value = router_mode
    planner = MagicMock()
    planner.plan.return_value = plan
    planner.execute.return_value = facts
    planner.resolve_org_exact.return_value = None
    s._planner = planner
    vec = MagicMock()
    vec.search.return_value = vec_posts or []
    vec._get_qdrant.return_value = FakeQdrant(qtexts or {})
    s._vec = vec
    gen = MagicMock()
    gen.generate.return_value = ("ответ", {})
    s._answer_gen = gen
    return s, planner, vec, gen


def test_struct_uses_source_posts_no_vector():
    url = "https://vk.com/rso_tesla?w=wall-1_1"
    facts = [{"person": "Иван", "relation": "COMMANDED",
              "source_post_url": url, "observed_at": "2026-03-01"}]
    s, planner, vec, gen = _searcher(
        "struct",
        {"intent": "commanders", "org_filter": None, "period_start": None,
         "period_end": None},
        facts,
        qtexts={url: ("Текст поста про Ивана", "2026-03-01", "Тесла")},
    )
    out = s.search("кто командует")
    vec.search.assert_not_called()  # ТЕСТ п.11: вектора в struct нет
    kwargs = gen.generate.call_args[1]
    assert len(kwargs["source_posts"]) == 1
    assert kwargs["source_posts"][0]["text"] == "Текст поста про Ивана"
    assert kwargs["posts"] == []
    assert out["posts_used"] == 1


def test_struct_empty_graph_falls_back_to_vector():
    s, planner, vec, gen = _searcher(
        "struct",
        {"intent": "commanders", "org_filter": None, "period_start": None,
         "period_end": None},
        [],
        vec_posts=[{"post_url": "u", "text": "t", "group_name": "g",
                    "published_at": "2026-01-01"}],
    )
    s.search("кто командует")
    vec.search.assert_called_once()  # п.9: граф пуст -> вектор
    kwargs = gen.generate.call_args[1]
    assert kwargs["source_posts"] == []
    assert len(kwargs["posts"]) == 1


def test_basic_year_filter():
    s, planner, vec, gen = _searcher(
        "basic", {}, [],
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
            return "ответ"

    gen = AnswerGenerator()
    stub = StubClient()
    gen._client = stub
    answer, blocks = gen.generate(
        "кто командует",
        mode="struct",
        graph_facts=[{"person": "Иван", "relation": "COMMANDED",
                      "event_date": "2026-04-01"}],
        posts=[],
        source_posts=[{"post_url": "u", "published_at": "2026-04-01",
                       "group_name": "g", "text": "текст поста"}],
    )
    assert answer == "ответ"
    assert "ФАКТЫ ИЗ ГРАФА" in blocks["graph"]
    assert "Иван" in blocks["graph"]
    assert "ПОСТЫ-ИСТОЧНИКИ" in blocks["source_posts"]
    assert "posts" not in blocks  # пустые блоки не отдаём
    assert "communities" not in blocks
    # Системный промпт наружу не утекает — только user-контекст.
    assert len(stub.seen) == 2


def test_search_context_flag():
    # include_context=False (по умолчанию) — контекст не раздувает ответ.
    s, planner, vec, gen = _searcher(
        "basic", {}, [],
        vec_posts=[{"post_url": "u", "text": "t", "group_name": "g",
                    "published_at": "2026-01-01"}],
    )
    gen.generate.return_value = ("ответ", {"posts": "=== ПОСТЫ ===\n..."})
    out = s.search("привет")
    assert out["context"] is None
    out2 = s.search("привет", include_context=True)
    assert out2["context"] == {"posts": "=== ПОСТЫ ===\n..."}


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
