"""Тесты Фазы 2: единый classify+plan, честная резолюция, строгий Cypher."""

import pytest

from backend.rag import query_planner as qp
from backend.rag.planner_queries import (
    commanders_query_strict,
    query_for_plan_v2,
    units_query_strict,
)
from backend.rag.query_schemas import QueryPlan


HQ_NORM = "штаб со кгэу тесла"


class FakeLLM:
    """Canned-ответ classify+plan + запись обмена в sink."""

    def __init__(self, payload=None, fail=False):
        self.payload = payload
        self.fail = fail

    def extract_json(self, prompt, question, schema=None, max_retries=1,
                     trace_sink=None):
        if self.fail:
            raise RuntimeError("LLM down")
        if trace_sink is not None:
            trace_sink.append({
                "messages": [
                    {"role": "system", "content": prompt[:20]},
                    {"role": "user", "content": question},
                ],
                "response": '{"intent": "%s"}' % self.payload.get("intent"),
            })
        return dict(self.payload)


class FakeGraph:
    """Кандидаты резолюции + строки commanders."""

    def __init__(self, candidates, rows=None):
        self.candidates = candidates
        self.rows = rows or []
        self.seen = []

    def search_cypher(self, query, params=None):
        self.seen.append((query, params or {}))
        if "o.norm_id AS norm_id" in query:
            return list(self.candidates)
        return list(self.rows)


# Живая топология (проверено 2026-09-14): org_type пуст у всех узлов,
# штаб опознаётся по HQ_NORM_ID, узлы несут по несколько меток.
CANDS = [
    {"norm_id": "тесла", "name": "Тесла", "org_type": None},
    {"norm_id": HQ_NORM, "name": "Студенческие отряды КГЭУ «Тесла» | РСО",
     "org_type": None},
    {"norm_id": "проектный центр штаба со тесла - прогрессlab",
     "name": "Проектный центр Штаба СО «Тесла» - «ПрогрессLAB»",
     "org_type": None},
]

COMMANDERS_PAYLOAD = {
    "intent": "commanders", "org_filter": "Тесла", "target_name": None,
    "event_name": None, "period_start": None, "period_end": None,
    "relation": None, "limit": 20,
}


def test_resolve_prefers_hq_for_generic_alias():
    g = FakeGraph(CANDS)
    assert qp.resolve_org_norm_id("Тесла", g) == HQ_NORM


def test_resolve_hq_without_org_type_beats_exact_squad():
    """Кейс живого графа: exact-norm 'тесла' = отряд, HQ без org_type."""
    g = FakeGraph(CANDS)
    assert qp.resolve_org_norm_id("штаб Тесла", g) == HQ_NORM


def test_resolve_exact_squad():
    g = FakeGraph(CANDS)
    assert qp.resolve_org_norm_id("Студенческий отряд «Тесла»", g) == "тесла"


def test_resolve_none_when_unknown(monkeypatch, tmp_path):
    monkeypatch.setattr(qp.quality_log, "_LOG_PATH", tmp_path / "q.jsonl")
    g = FakeGraph([])
    assert qp.resolve_org_norm_id("Несуществующий", g) is None
    assert qp.resolve_org_norm_id("Тесла", None) is None


def test_classify_and_plan_single_call(monkeypatch, tmp_path):
    monkeypatch.setattr(qp.quality_log, "_LOG_PATH", tmp_path / "q.jsonl")
    g = FakeGraph(CANDS)
    sink: list = []
    plan = qp.classify_and_plan(
        "кто входит в комсостав штаба Тесла?",
        graph=g, llm=FakeLLM(COMMANDERS_PAYLOAD), trace_sink=sink,
    )
    assert isinstance(plan, QueryPlan)
    assert (plan.intent, plan.mode, plan.kind) == ("commanders", "struct", "enumerable")
    assert plan.org_norm_id == HQ_NORM
    assert plan.llm_calls == 1 and len(sink) == 1


def test_unknown_intent_falls_back(monkeypatch, tmp_path):
    monkeypatch.setattr(qp.quality_log, "_LOG_PATH", tmp_path / "q.jsonl")
    bad = dict(COMMANDERS_PAYLOAD, intent="teleport")
    plan = qp.classify_and_plan("???", graph=FakeGraph(CANDS), llm=FakeLLM(bad))
    assert (plan.intent, plan.mode) == ("general", "basic")
    assert (tmp_path / "q.jsonl").exists()


def test_llm_failure_falls_back(monkeypatch, tmp_path):
    monkeypatch.setattr(qp.quality_log, "_LOG_PATH", tmp_path / "q.jsonl")
    plan = qp.classify_and_plan("???", graph=None, llm=FakeLLM(fail=True))
    assert plan.intent == "general"


def test_strict_queries_no_contains():
    plan = {"intent": "commanders", "org_norm_id": HQ_NORM, "limit": 20}
    q, params = commanders_query_strict(plan)
    assert "CONTAINS" not in q and "$org_norm_id" in q
    assert params["org_norm_id"] == HQ_NORM
    assert commanders_query_strict({"intent": "commanders"}) is None

    uplan = {"intent": "units", "org_norm_id": HQ_NORM, "limit": 20}
    uq, up = units_query_strict(uplan)
    assert "CONTAINS" not in uq and up["org_norm_id"] == HQ_NORM

    from backend.rag.planner_queries import partners_query_strict
    pplan = {"intent": "partners", "org_norm_id": HQ_NORM, "limit": 20}
    pq, pp = partners_query_strict(pplan)
    # Направленный запрос от самой org, внутренние пары вырезаны.
    assert "CONTAINS" not in pq
    assert "s.norm_id = $org_norm_id" in pq
    assert "PART_OF" in pq and "o.norm_id <> $org_norm_id" in pq
    assert pp["org_norm_id"] == HQ_NORM
    assert partners_query_strict({"intent": "partners"}) is None


def test_query_for_plan_v2_dispatch():
    q, _ = query_for_plan_v2(
        {"intent": "commanders", "org_norm_id": HQ_NORM, "limit": 20})
    assert "$org_norm_id" in q
    # members: legacy-хендлер, но с проброшенным org_exact
    mq, mp = query_for_plan_v2(
        {"intent": "members", "org_filter": "Тесла",
         "org_norm_id": HQ_NORM, "limit": 20})
    assert mp["org_exact"] == HQ_NORM


def test_regression_commanders_tesla_without_progresslab(monkeypatch, tmp_path):
    """Регресс Фазы 2: commanders('Тесла') — только штаб, без ПрогрессLAB."""
    monkeypatch.setattr(qp.quality_log, "_LOG_PATH", tmp_path / "q.jsonl")
    hq_rows = [
        {"person": "Даниил Астафьев", "role_title": "Руководитель",
         "relation": "COMMANDED"},
        {"person": "Альфред Шарифуллин", "role_title": "Комиссар",
         "relation": "COMMANDED"},
    ]
    leak_rows = hq_rows + [
        {"person": "Виталий Петров",
         "role_title": "Заместитель руководителя Проектного центра",
         "relation": "COMMANDED"},
    ]

    class LeakyGraph(FakeGraph):
        def search_cypher(self, query, params=None):
            self.seen.append((query, params or {}))
            if "o.norm_id AS norm_id" in query:
                return list(self.candidates)
            # Эмуляция старого поведения: CONTAINS тянет и ПрогрессLAB.
            if "CONTAINS" in query:
                return list(leak_rows)
            assert (params or {}).get("org_norm_id") == HQ_NORM
            return list(hq_rows)

    g = LeakyGraph(CANDS)
    plan = qp.classify_and_plan(
        "Кто входит в командный состав штаба Тесла?",
        graph=g, llm=FakeLLM(COMMANDERS_PAYLOAD),
    )
    query, params = query_for_plan_v2(plan.to_dict())
    assert "CONTAINS" not in query
    rows = g.search_cypher(query, params)
    names = [r["person"] for r in rows]
    assert "Виталий Петров" not in names
    assert set(names) == {"Даниил Астафьев", "Альфред Шарифуллин"}


def _payload(intent, **kw):
    base = {"intent": intent, "org_filter": None, "target_name": None,
            "event_name": None, "period_start": None, "period_end": None,
            "relation": None, "limit": 20}
    base.update(kw)
    return base


# Golden-набор Фазы 6: вопрос -> intent+slots -> точный текст шаблона.
GOLDEN = [
    (_payload("units", org_filter="Тесла"),
     [{"unit": "Монолит"}],
     ("units", "struct", "enumerable"), "Отряды «Тесла»:"),
    (_payload("commanders", org_filter="Тесла"),
     [{"person": "Даниил Астафьев", "role_title": "Руководитель",
       "relation": "COMMANDED"}],
     ("commanders", "struct", "enumerable"), "Командный состав «Тесла»:"),
    (_payload("members", org_filter="Монолит"),
     [{"person": "Боец"}],
     ("members", "struct", "enumerable"), "Участники «Монолит»:"),
    (_payload("winners", org_filter="Тесла"),
     [{"person": "X", "award": "Гран-при", "relation": "WON_AWARD"}],
     ("winners", "struct", "enumerable"), "Награды «Тесла»:"),
    (_payload("partners", org_filter="Тесла"),
     [{"subject": "Штаб", "partner": "Ак Барс Банк"}],
     ("partners", "struct", "enumerable"), "Партнёры «Тесла» (поддерживают Штаб):"),
    (_payload("projects", org_filter="Тесла"),
     [{"project": "Снежный десант"}],
     ("projects", "struct", "enumerable"), "Проекты «Тесла»:"),
    (_payload("locations"),
     [{"location": "Казань"}],
     ("locations", "struct", "enumerable"), "Локации «архив»:"),
    (_payload("events_in_period", period_start="2026-01-01",
              period_end="2026-03-31"),
     [{"event": "Погружение"}],
     ("events_in_period", "struct", "enumerable"), "Мероприятия:"),
]


@pytest.mark.parametrize("payload,rows,expected,head", GOLDEN)
def test_golden_intent_and_template(monkeypatch, tmp_path, payload, rows,
                                    expected, head):
    from backend.rag.renderers import render

    monkeypatch.setattr(qp.quality_log, "_LOG_PATH", tmp_path / "q.jsonl")
    plan = qp.classify_and_plan(
        "вопрос", graph=FakeGraph(CANDS), llm=FakeLLM(payload))
    assert (plan.intent, plan.mode, plan.kind) == expected
    text = render(plan.intent, rows, plan.org_filter or "архив")
    assert text.startswith(head)


def test_golden_narrative_intents(monkeypatch, tmp_path):
    monkeypatch.setattr(qp.quality_log, "_LOG_PATH", tmp_path / "q.jsonl")
    g = FakeGraph(CANDS)
    ed = qp.classify_and_plan(
        "кто такой", graph=g,
        llm=FakeLLM(_payload("entity_detail", target_name="Астафьев")))
    assert (ed.intent, ed.mode, ed.kind) == (
        "entity_detail", "local", "narrative")
    assert ed.target_name == "Астафьев"
    gen = qp.classify_and_plan("расскажи", graph=g, llm=FakeLLM(_payload("general")))
    assert (gen.intent, gen.mode, gen.kind) == ("general", "basic", "narrative")
