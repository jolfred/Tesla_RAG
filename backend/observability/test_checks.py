from backend.observability import checks


def test_dates_grounded_ok():
    facts = [{"event_date": "2026-03-30", "observed_at": "2026-03-31"}]
    assert checks.check_groundedness_of_dates("Событие 2026-03-30 прошло",
                                              facts) is True


def test_dates_grounded_year_fail():
    facts = [{"observed_at": "2025-09-18"}]
    assert checks.check_groundedness_of_dates("Итоги 2026 года", facts) \
        is False


def test_dates_no_dates_in_answer_ok():
    assert checks.check_groundedness_of_dates("Просто текст",
                                              [{"observed_at": None}]) is True


def test_dates_year_from_context_ok():
    # Год из контекста модели (карточка группы), не из строк графа, —
    # не галлюцинация.
    facts = [{"observed_at": "2026-03-31"}]
    assert checks.check_groundedness_of_dates(
        "Объединение работает с 2015 года", facts,
        ["история: объединение работает с 2015 года"]) is True


def test_dates_invented_iso_fail_despite_context():
    facts = [{"observed_at": "2026-03-31"}]
    assert checks.check_groundedness_of_dates(
        "Событие 2026-03-30 прошло", facts, ["пост без дат"]) is False


def test_hierarchy_no_claim_ok():
    assert checks.check_hierarchy_claim("Обычный ответ", []) is True


def test_hierarchy_claim_without_evidence_fail():
    assert checks.check_hierarchy_claim("Отряд входит в состав штаба",
                                        [{"relation": "HOLDS_ROLE"}]) is False


def test_hierarchy_claim_with_part_of_ok():
    assert checks.check_hierarchy_claim("Отряд входит в состав штаба",
                                        [{"relation": "PART_OF"}]) is True


def test_empty_but_confident_silence_ok():
    assert checks.check_empty_but_confident([], "В архивах нет данных") \
        is True


def test_empty_but_confident_confident_fail():
    assert checks.check_empty_but_confident([], "Командир — Иванов") is False


def test_empty_but_confident_with_facts_ok():
    assert checks.check_empty_but_confident([{"a": 1}], "Командир — Иванов") \
        is True
