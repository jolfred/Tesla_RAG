"""Тесты Фазы 3: rows_to_facts и _fmt_facts из Fact."""

from backend.rag.answer_generator import AnswerGenerator
from backend.rag.facts import Fact, rows_to_facts


def test_rows_to_facts_mapping():
    facts = rows_to_facts([
        {"person": "Даниил Астафьев", "role_title": "Руководитель",
         "relation": "COMMANDED", "event_date": "2026-04-01",
         "observed_at": "2026-04-01", "role_status": "active",
         "source_post_url": "https://vk.com/x",
         "description": "d", "unknown_key": 1},
        {"event": "Погружение", "links": [{"date": "2026-01-01"}]},
    ])
    f = facts[0]
    assert isinstance(f, Fact)
    assert (f.person, f.role_title, f.event_date) == (
        "Даниил Астафьев", "Руководитель", "2026-04-01")
    assert f.source_post_url == "https://vk.com/x"
    assert facts[1].label == "Погружение"
    assert facts[1].person == "?"
    # Fact на входе проходит как есть
    assert rows_to_facts([f]) == [f]
    assert rows_to_facts([]) == []


def test_fmt_prefers_role_title():
    s = AnswerGenerator._fmt_facts([
        {"person": "Альфред Шарифуллин", "role_title": "Комиссар",
         "relation": "COMMANDED", "observed_at": "2026-02-19"},
    ])
    assert "Комиссар" in s
    assert "(COMMANDED)" not in s
    assert "упоминание в посте от 2026-02-19" in s


def test_fmt_keeps_legacy_date_and_links():
    s = AnswerGenerator._fmt_facts([
        {"person": "X", "relation": "MEMBER_OF", "date": "2025-05-05"},
        {"event": "Погружение", "links": [{"date": "2026-01-01"}]},
    ])
    assert "| дата: 2025-05-05" in s
    assert "Погружение" in s and "2026-01-01" in s
