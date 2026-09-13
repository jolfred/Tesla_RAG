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
    gen.generate.return_value = "ответ"
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
    assert params["org"] == "Тесла"


def test_org_exact_in_commanders_query():
    q, params = query_for_plan(
        {"intent": "commanders", "org_filter": "Тесла",
         "org_exact": "штаб со кгэу тесла", "limit": 20}
    )
    assert "o.norm_id = $org_exact" in q
    assert params["org_exact"] == "штаб со кгэу тесла"
