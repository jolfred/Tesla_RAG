"""Тесты Milestone A: ontology.validate_triple + canon (mock'и, сервисы не нужны)."""

from backend.common.canon import (
    normalize_id,
    parse_ex_person,
    person_key,
    resolve_person,
    yo_normalize,
)
from backend.common.ontology import ALLOWED_TRIPLES, validate_triple


class FakeSession:
    def __init__(self, rows):
        self._rows = rows
        self.calls = []

    def run(self, query, **params):
        self.calls.append((query, params))

        class R:
            def __init__(self, rows):
                self._rows = rows

            def data(self):
                return self._rows

        return R(self._rows)


# --- пункт 7: проверка тройки целиком ---


def test_validate_triple_ok():
    assert validate_triple("Person", "COMMANDED", "Squad") is True
    assert validate_triple("Squad", "SUPPORTED_BY", "Organization") is True


def test_validate_triple_commanded_role_rejected():
    # Класс Б3b: тип ребра "разрешён", но такая тройка — нет.
    assert validate_triple("Person", "COMMANDED", "Role") is False


def test_validate_triple_squad_award_allowed():
    # Б2: награды получают отряды целиком.
    assert validate_triple("Squad", "WON_AWARD", "Award") is True
    assert validate_triple("Organization", "WON_AWARD", "Award") is True


def test_validate_triple_unknown_rejected():
    assert validate_triple("Person", "FOO", "Squad") is False
    assert validate_triple("Alien", "MEMBER_OF", "Squad") is False
    assert validate_triple("Person", "MEMBER_OF", "Alien") is False


def test_triples_subset_of_allowed():
    assert ("Person", "COMMANDED", "Squad") in ALLOWED_TRIPLES
    assert ("Person", "COMMANDED", "Role") not in ALLOWED_TRIPLES


# --- canon: нормализация ---


def test_yo_normalize():
    assert yo_normalize("Артём") == "артем"
    assert yo_normalize("  Хазиев ") == "хазиев"


def test_normalize_id_legacy_behaviour():
    assert normalize_id("СОП «Энергия»") == normalize_id("Соп Энергия")
    assert normalize_id("775 000 рублей") == "775000 рублей"
    assert normalize_id("Республика Татарстан") == "татарстан"
    assert normalize_id("Студенческие отряды Тесла") == "штаб со кгэу тесла"


def test_person_key_order_and_yo():
    # Б5: порядок слов и ё не должны давать разные узлы.
    assert person_key("Хазиев Артем") == person_key("Артём Хазиев")
    assert person_key("Хазиев Артем") != person_key("Хазиев Искандер")


def test_person_key_drops_ex_and_role():
    assert person_key("экс-командир Иван Петров") == person_key("Иван Петров")
    assert person_key("командир Иван Петров") == person_key("Иван Петров")


def test_parse_ex_person():
    name, role, former = parse_ex_person("экс-командир Иван Петров")
    assert name == "Иван Петров"
    assert role == "командир"
    assert former is True
    name, role, former = parse_ex_person("Иван Петров")
    assert name == "Иван Петров"
    assert role is None
    assert former is False


# --- canon: бинарное разрешение ---


def test_resolve_no_candidates_creates():
    res = resolve_person("Иван Петров", {"squad-x"}, FakeSession([]))
    assert res.action == "create"
    assert res.possible_duplicates == []
    assert res.is_former is False


def test_resolve_single_exact_string_merges():
    s = FakeSession([{"id": "m::x", "name": "Иван Петров", "orgs": []}])
    res = resolve_person("Иван Петров", set(), s)
    assert res.action == "merge"
    assert res.target_id == "m::x"


def test_resolve_single_yo_variant_merges():
    s = FakeSession([{"id": "m::x", "name": "Артем Хазиев", "orgs": []}])
    res = resolve_person("Артём Хазиев", set(), s)
    assert res.action == "merge"


def test_resolve_single_org_overlap_merges():
    s = FakeSession([{"id": "m::x", "name": "И. Петров", "orgs": ["squad-x"]}])
    res = resolve_person("Иван Петров", {"squad-x"}, s)
    assert res.action == "merge"


def test_resolve_single_no_proof_flags():
    # Один кандидат, но ни строка ни орг-контекст не совпали -> уточнить.
    s = FakeSession([{"id": "m::x", "name": "Петр Иванов", "orgs": ["squad-y"]}])
    res = resolve_person("Иван Петров", {"squad-x"}, s)
    assert res.action == "create"
    assert res.possible_duplicates == ["m::x"]


def test_resolve_multiple_flags_all():
    s = FakeSession(
        [
            {"id": "m::1", "name": "Иван Петров", "orgs": ["squad-a"]},
            {"id": "m::2", "name": "Иван Петров", "orgs": ["squad-b"]},
        ]
    )
    res = resolve_person("Иван Петров", {"squad-a"}, s)
    assert res.action == "create"
    assert res.possible_duplicates == ["m::1", "m::2"]


def test_resolve_ex_marks_former():
    res = resolve_person("экс-командир Иван Петров", set(), FakeSession([]))
    assert res.action == "create"
    assert res.is_former is True
    assert res.role_hint == "командир"
    assert res.name == "Иван Петров"
