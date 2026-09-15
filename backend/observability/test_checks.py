"""Тесты Слоя 1: проверки дат, иерархии и 'пусто, но уверенно'."""

from backend.observability import checks as c


def test_dates_grounded():
    facts = [{"event_date": "2025-09-30", "observed_at": "2025-10-01",
              "links": [{"date": "2026-01-01"}]}]
    assert c.check_groundedness_of_dates("назначен с 2025-09-30", facts) is True
    assert c.check_groundedness_of_dates("упоминание от 2026-01-01", facts) is True
    assert c.check_groundedness_of_dates("с 19 февраля", facts) is True  # не ISO — мимо
    assert c.check_groundedness_of_dates("командует с 2025-02-25", facts) is False
    assert c.check_groundedness_of_dates("без дат", []) is True


def test_hierarchy_claim():
    ok_facts = [{"relation": "PART_OF"}]
    assert c.check_hierarchy_claim("просто ответ", []) is True
    assert c.check_hierarchy_claim("X входит в состав штаба", ok_facts) is True
    assert c.check_hierarchy_claim("X является частью штаба", []) is False
    assert c.check_hierarchy_claim("X подчиняется штабу", []) is False
    links = [{"links": [{"rel": "PART_OF"}]}]
    assert c.check_hierarchy_claim("X входит в состав", links) is True


def test_empty_but_confident():
    assert c.check_empty_but_confident([{"a": 1}], 0, "уверенный ответ") is True
    assert c.check_empty_but_confident([], 3, "уверенный ответ") is True
    assert c.check_empty_but_confident([], 0, "В архивах нет данных") is True
    assert c.check_empty_but_confident([], 0, "Командир — Иван") is False


def test_run_layer1_keys():
    flags = c.run_layer1("X входит в состав, с 2025-02-25", [], 0)
    assert flags == {"groundedness_ok": False,
                     "hierarchy_claim_flag": True,
                     "empty_but_confident_flag": True}
