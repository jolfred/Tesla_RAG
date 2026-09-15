"""Тесты Фазы 3: rows_to_facts и _fmt_facts из Fact."""

from backend.rag.answer_generator import AnswerGenerator
from backend.rag.facts import Fact, rows_to_facts, supersede_roles


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


def test_supersede_new_commander_wins():
    # Смена состава: вымышленные имена, только механика дат.
    old = Fact(person="Иван Петров", role_title="Командир",
               observed_at="2024-10-01")
    new = Fact(person="Петр Иванов", role_title="Руководитель (командир)",
               event_date="2025-09-30")
    out = supersede_roles([old, new])
    assert out[0].role_status == "former"
    assert out[1].role_status != "former"
    # Порядок не меняем, только флаги.
    assert [f.person for f in out] == ["Иван Петров", "Петр Иванов"]


def test_supersede_two_masters_coexist():
    a = Fact(person="А", role_title="Мастер", observed_at="2025-01-01")
    b = Fact(person="Б", role_title="Мастер", observed_at="2025-01-01")
    out = supersede_roles([a, b])
    assert [f.role_status for f in out] == [None, None]


def test_supersede_no_dates_no_one_loses():
    a = Fact(person="А", role_title="Командир")
    b = Fact(person="Б", role_title="Комиссар")
    out = supersede_roles([a, b])
    assert [f.role_status for f in out] == [None, None]
    # Разные кресла не конфликтуют даже с датами.
    c = Fact(person="В", role_title="Командир", observed_at="2024-01-01")
    d = Fact(person="Г", role_title="Комиссар", observed_at="2025-01-01")
    out2 = supersede_roles([c, d])
    assert [f.role_status for f in out2] == [None, None]


def test_supersede_same_title_old_loses():
    old = Fact(person="А", role_title="Мастер", observed_at="2024-01-01")
    new = Fact(person="Б", role_title="Мастер", event_date="2025-09-30")
    out = supersede_roles([old, new])
    assert out[0].role_status == "former"
    assert out[1].role_status != "former"
