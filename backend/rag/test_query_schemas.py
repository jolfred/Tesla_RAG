"""Тесты Фазы 1: интент-схемы, таблицы режим/вид, подтип general."""

from backend.rag import query_schemas as qs


def test_schema_field_sets():
    """Набор полей каждой схемы зафиксирован (регресс против призрачных полей)."""
    assert set(qs.UnitsQuery.model_fields) == {"org_filter", "limit"}
    assert set(qs.CommandersQuery.model_fields) == {"org_filter", "limit"}
    assert set(qs.MembersQuery.model_fields) == {"org_filter", "limit"}
    assert set(qs.WinnersQuery.model_fields) == {
        "org_filter", "event_name", "period_start", "period_end", "limit",
    }
    assert set(qs.PartnersQuery.model_fields) == {"org_filter", "limit"}
    assert set(qs.ProjectsQuery.model_fields) == {"org_filter", "limit"}
    assert set(qs.LocationsQuery.model_fields) == {"org_filter", "limit"}
    assert set(qs.EventsQuery.model_fields) == {
        "org_filter", "period_start", "period_end", "limit",
    }
    assert set(qs.EntityDetailQuery.model_fields) == {"target_name"}
    assert set(qs.GeneralQuery.model_fields) == set()


def test_tables_cover_all_intents():
    assert set(qs.INTENT_SCHEMAS) == set(qs.INTENT_TO_MODE) == set(qs.INTENT_TO_KIND)
    assert len(qs.INTENT_SCHEMAS) == 10


def test_enumerable_set():
    kinds = {i for i, k in qs.INTENT_TO_KIND.items() if k == "enumerable"}
    assert kinds == {
        "units", "commanders", "members", "winners",
        "projects", "locations", "partners", "events_in_period",
    }
    assert qs.INTENT_TO_KIND["entity_detail"] == "narrative"
    assert qs.INTENT_TO_KIND["general"] == "narrative"


def test_modes():
    for intent in ("units", "commanders", "members", "winners",
                   "projects", "locations", "partners", "events_in_period"):
        assert qs.INTENT_TO_MODE[intent] == "struct"
    assert qs.INTENT_TO_MODE["entity_detail"] == "local"
    assert qs.INTENT_TO_MODE["general"] is None


def test_classify_general_subtype():
    assert qs.classify_general_subtype("что было в целом за всё время") == "global"
    assert qs.classify_general_subtype("какие тенденции?") == "global"
    assert qs.classify_general_subtype("как менялось?") == "global"
    assert qs.classify_general_subtype("кто командир?") == "basic"
    assert qs.classify_general_subtype("") == "basic"


def test_query_plan_defaults():
    p = qs.QueryPlan()
    assert (p.intent, p.mode, p.kind) == ("general", "basic", "narrative")
    assert p.org_norm_id is None
    d = p.to_dict()
    assert d["intent"] == "general" and "llm_calls" not in d
