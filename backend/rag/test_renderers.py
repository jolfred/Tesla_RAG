"""Тесты Фазы 4: рендереры точным сравнением строк."""

import pytest

from backend.rag import renderers as r
from backend.rag.facts import Fact


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
        "• Даниил Астафьев — Руководитель (с 2026-04-01)\n"
        "• Альфред Шарифуллин — Комиссар (упоминание от 2026-02-19)\n"
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
