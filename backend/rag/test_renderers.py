"""Тесты Фазы 4: рендереры точным сравнением строк."""

import pytest

from backend.rag import renderers as r
from backend.rag.facts import Fact


def test_render_commanders_rank_hierarchy():
    """Иерархия: командир -> комиссар -> мастер -> пресса -> остальные."""
    facts = [
        Fact(person="Юлия Остапенко", role_title="Мастер Штаба СО КГЭУ «Тесла»"),
        Fact(person="Карина Баранова",
             role_title="Заместитель пресс-секретаря Штаба СО КГЭУ «Тесла»"),
        Fact(person="Никита Соловьев",
             role_title="Руководитель строительного направления Штаба СО КГЭУ «Тесла»"),
        Fact(person="Альфред Шарифуллин", role_title="Комиссар Штаба СО КГЭУ «Тесла»"),
        Fact(person="Арсений Аксенов",
             role_title="Пресс-секретарь Штаба СО КГЭУ «Тесла»"),
        Fact(person="Артём Хазиев",
             role_title="Руководитель проектного центра Штаба СО КГЭУ «Тесла»"),
        Fact(person="Даниил Астафьев",
             role_title="Руководитель (командир) Штаба СО КГЭУ «Тесла»"),
        Fact(person="Максим Шархимуллин", role_title="Мастер Штаба СО КГЭУ «Тесла»"),
    ]
    out = r.render_commanders(facts, "Тесла")
    names = [line.split(" — ")[0][2:] for line in out.split("\n")[1:]]
    assert names == [
        "Даниил Астафьев",
        "Альфред Шарифуллин",
        "Максим Шархимуллин",
        "Юлия Остапенко",
        "Арсений Аксенов",
        "Карина Баранова",
        "Артём Хазиев",
        "Никита Соловьев",
    ]


def test_render_commanders_exact():
    facts = [
        Fact(person="Даниил Астафьев", role_title="Руководитель",
             event_date="2026-04-01"),
        Fact(person="Альфред Шарифуллин", role_title="Комиссар",
             observed_at="2026-02-19T10:00:00Z"),
        Fact(person="Экс", role_title=None, role_status="former"),
    ]
    assert r.render_commanders(facts, "Штаб") == (
        "Командный состав «Штаб»:\n"
        "• Альфред Шарифуллин — Комиссар (упоминание от 2026-02-19)\n"
        "• Даниил Астафьев — Руководитель (с 2026-04-01)\n"
        "• Экс — должность не указана [экс]"
    )


def test_render_empty_is_none():
    for fn in r.RENDERERS.values():
        assert fn([], "Штаб") is None
    assert r.render("unknown_intent", [{"person": "X"}], "Штаб") is None


def test_render_units_winners_members():
    assert r.render("units", [{"unit": "Монолит"}, {"unit": "Дельта"}], "Штаб") == (
        "Отряды «Штаб»:\n• Монолит\n• Дельта"
    )
    assert r.render(
        "winners",
        [{"person": "X", "award": "Гран-при", "relation": "WON_AWARD"},
         {"person": "Y", "award": "Конкурс", "relation": "PARTICIPATED_IN"}],
        "Штаб",
    ) == (
        "Награды «Штаб»:\n• X — Гран-при\n• Y — Конкурс (участие, не победа)"
    )
    assert r.render(
        "members", [{"person": "Боец", "role_title": "боец"}], "Монолит"
    ) == "Участники «Монолит»:\n• Боец — боец"


def test_render_partners_events_projects_locations():
    assert r.render(
        "partners",
        [{"subject": "Штаб", "partner": "Ак Барс Банк"}],
        "Штаб",
    ) == "Партнёры «Штаб»:\n• Ак Барс Банк (поддерживает Штаб)"
    assert r.render(
        "events_in_period", [{"event": "Погружение", "event_date": "2026-01-15"}],
        "Штаб",
    ) == "Мероприятия «Штаб»:\n• Погружение (2026-01-15)"
    assert r.render("projects", [{"project": "Снежный десант"}], "Штаб") == (
        "Проекты «Штаб»:\n• Снежный десант"
    )
    assert r.render("locations", [{"location": "Казань"}], "Штаб") == (
        "Локации «Штаб»:\n• Казань"
    )


def test_render_person_roles_exact():
    facts = [
        Fact(person="Даниил Астафьев", role_title="Руководитель",
             org="Штаб СО КГЭУ «Тесла»", event_date="2026-04-01"),
        Fact(person="Даниил Астафьев", role_title="Командир",
             org="Монолит", role_status="former"),
    ]
    assert r.render_person_roles(facts, "Даниил Астафьев") == (
        "«Даниил Астафьев»:\n"
        "• Руководитель — Штаб СО КГЭУ «Тесла» (с 2026-04-01)\n"
        "• Командир — Монолит [экс]"
    )
    assert r.render_person_roles([], "X") is None


def test_progresslab_note_when_not_subordinate(monkeypatch):
    monkeypatch.setattr(r, "PROGRESSLAB_IS_SUBORDINATE", False)
    out = r.render_commanders(
        [Fact(person="Виталий Петров",
              role_title="Заместитель руководителя Проектного центра",
              org="Проектный центр Штаба СО «Тесла» - «ПрогрессLAB»")],
        "Штаб",
    )
    assert "связанная структура, подчинение не подтверждено" in out
    assert "частью Штаба" not in out
