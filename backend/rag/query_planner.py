"""Единый вызов классификации+плана v2 (Фаза 2 плана упрощения пайплайна).

Заменяет цепочку QueryRouter.route() + GraphPlanner.plan() (2 LLM-вызова)
одним вызовом: модель возвращает {intent, slots}, режим и вид ответа
берутся из детерминированных таблиц query_schemas (0 вызовов).

Отклонение от исходного плана: вместо нативного tool calling
(`bind_tools` — GigaChatClient его не поддерживает, там только
OpenAI-совместимый `chat.completions.create` с `response_format=json_schema`,
а поддержка `tools=` на стороне GigaChat не проверена) — один плоский
JSON-вызов с последующей pydantic-валидацией по интент-схеме. Цель та же:
1 вызов вместо 2, строгий контракт слотов.

Второе отклонение: `canon.resolve_entity()` из плана в коде отсутствует
(canon.py содержит normalize_id/person_key/resolve_person). Честная
резолюция организации сделана здесь: normalize_id + проверка существования
узла в графе + детерминированный выбор (точное совпадение, предпочтение HQ
для generic-алиасов "тесла"/"штаб"). Никакого молчаливого склеивания:
org_norm_id — norm_id существующего узла или None.
"""

from __future__ import annotations

from backend.admin.prompts import get_prompt as _get_prompt
from backend.common.canon import normalize_id
from backend.rag.query_schemas import (
    INTENT_SCHEMAS,
    INTENT_TO_KIND,
    INTENT_TO_MODE,
    QueryPlan,
    classify_general_subtype,
)
from backend.utils.gigachat_client import GigaChatClient
from backend.utils.logger import setup_logger

logger = setup_logger("query_planner")

PLAN_PROMPT = """Ты — классификатор и планировщик запросов к базе знаний о студенческих отрядах КГЭУ «Тесла».
За ОДИН проход определи интент вопроса и извлеки слоты. Ответь строго JSON, никакого дополнительного текста.

{
  "intent": "units | events_in_period | commanders | members | winners | projects | locations | partners | entity_detail | general",
  "org_filter": "название штаба/отряда/организации | null",
  "target_name": "имя человека/сущности | null",
  "event_name": "название события | null",
  "period_start": "YYYY-MM-DD | null",
  "period_end": "YYYY-MM-DD | null",
  "relation": null,
  "limit": 20
}

Правила интентов:
- "units": списки отрядов/подразделений штаба («перечисли отряды штаба», «какие отряды входят»). org_filter — штаб.
- "commanders": командиры/комиссары/руководители/роли/контакты/состав штаба или отряда («кто командир», «комсостав», «контакты»). org_filter — штаб/отряд.
- "members": участники/бойцы отрядов (НЕ командный состав).
- "winners": победители/награды/призовые места.
- "projects": проекты/трудовые семестры.
- "locations": места/локации.
- "partners": партнёры/спонсоры/поддержка («кто партнёры», «с кем сотрудничает»).
- "events_in_period": мероприятия/события, в т.ч. с датой/периодом.
- "entity_detail": вопрос о КОНКРЕТНОЙ сущности (target_name задан) и НЕ о командирах/составе.
- "general": всё остальное.
- org_filter: "Тесла" если вопрос о штабе/отрядах Тесла, иначе null. Для вопросов про конкретный отряд — его название.
- period_start/period_end только при явном периоде в вопросе («с начала 2026» -> "2026-01-01").
- limit: обычно 20, для «назови всех» — 100."""

PLAN_SCHEMA = {
    "type": "object",
    "properties": {
        "intent": {"type": "string"},
        "org_filter": {"type": ["string", "null"]},
        "target_name": {"type": ["string", "null"]},
        "event_name": {"type": ["string", "null"]},
        "period_start": {"type": ["string", "null"]},
        "period_end": {"type": ["string", "null"]},
        "relation": {"type": ["string", "null"]},
        "limit": {"type": "integer"},
    },
    "required": [
        "intent", "org_filter", "target_name", "event_name",
        "period_start", "period_end", "relation", "limit",
    ],
}

# Канонический ключ штаба (target canon.SYNONYMS): узел с этим norm_id —
# штаб, даже если у него нет org_type='hq' (в живых данных org_type пуст,
# а generic-алиас 'тесла' точно совпадает с norm_id отряда СПО «Тесла»).
HQ_NORM_ID = "штаб со кгэу тесла"

# Generic-алиасы штаба: вопрос "про Теслу" = вопрос про штаб.
# Маппинг НЕ кладём в canon.SYNONYMS: там он повлиял бы на MERGE-ключи
# индексатора (отряд СПО «Тесла» склеился бы со штабом). Правило живёт
# только здесь, на чтение.
HQ_GENERIC_WORDS = frozenset(
    {"тесла", "штаб", "штаб тесла", "тесла штаб", "со тесла", "штаб со"}
)


def resolve_org_norm_id(
    org_filter: str | None, graph, source_model: str | None = None
) -> str | None:
    """Честная резолюция организации: norm_id существующего узла или None.

    graph — объект с .search_cypher(query, params) (GraphBuilder или mock
    в тестах). Возвращает norm_id выбранного узла, никакого CONTAINS-
    склеивания на этапе выполнения запроса.
    """
    if not org_filter or graph is None:
        return None
    norm = normalize_id(org_filter)
    if not norm:
        return None
    model = source_model or "llmgraph_gigachat"
    try:
        rows = graph.search_cypher(
            "MATCH (o) "
            "WHERE o.source_model = $m "
            "AND (o:Squad OR o:Organization OR o:Entity) "
            "AND (o.norm_id = $norm "
            "OR toLower(toString(o.name)) CONTAINS toLower($raw)) "
            "RETURN o.norm_id AS norm_id, o.name AS name, "
            "o.org_type AS org_type LIMIT 25",
            {"m": model, "norm": norm, "raw": org_filter},
        )
    except Exception as e:
        logger.warning("org resolve failed: %s", e)
        return None
    cands = [dict(r) for r in rows if r.get("norm_id")]
    if not cands:
        return None
    prefer_hq = norm in HQ_GENERIC_WORDS

    def _rank(c: dict) -> tuple:
        exact = c.get("norm_id") == norm
        name_norm = normalize_id(c.get("name") or "")
        full = norm in name_norm
        # Токены имени целиком внутри фильтра («отряд Монолит» -> «Монолит»).
        subset = bool(name_norm) and set(name_norm.split()) <= set(norm.split())
        hq = (c.get("org_type") or "") == "hq" or c.get("norm_id") == HQ_NORM_ID
        if prefer_hq:
            return (not hq, not exact, not full, not subset,
                    len(c.get("name") or ""))
        return (not exact, not full, not subset, not hq,
                len(c.get("name") or ""))

    cands.sort(key=_rank)
    return cands[0]["norm_id"]


def classify_and_plan(
    question: str,
    graph=None,
    llm: GigaChatClient | None = None,
    trace_sink: list | None = None,
    source_model: str | None = None,
) -> QueryPlan:
    """Один LLM-вызов: интент + слоты, дальше — детерминированный код."""
    client = llm or GigaChatClient()
    inner: list = []
    try:
        data = client.extract_json(
            _get_prompt("plan_prompt"), question, schema=PLAN_SCHEMA,
            max_retries=1, trace_sink=inner,
        )
    except Exception as e:
        logger.warning("classify_and_plan LLM failed: %s", e)
        if trace_sink is not None:
            trace_sink.extend(inner)
        return QueryPlan(llm_calls=len(inner))
    if trace_sink is not None:
        trace_sink.extend(inner)

    intent = data.get("intent")
    schema = INTENT_SCHEMAS.get(intent)
    if schema is None:
        logger.warning("Unknown intent '%s', fallback to general", intent)
        return QueryPlan(llm_calls=len(inner))
    try:
        slots = schema.model_validate(
            {k: v for k, v in data.items() if k in schema.model_fields}
        )
    except Exception as e:
        logger.warning("Slot validation failed for %s: %s", intent, e)
        return QueryPlan(llm_calls=len(inner))

    limit = max(1, min(int(slots.limit) if getattr(slots, "limit", None) else 20, 100))
    mode = INTENT_TO_MODE[intent] or classify_general_subtype(question)
    kind = INTENT_TO_KIND[intent]

    org_filter = getattr(slots, "org_filter", None)
    org_norm_id = (
        resolve_org_norm_id(org_filter, graph, source_model) if org_filter else None
    )
    if org_filter and org_norm_id is None:
        logger.warning("org resolve failed for filter: %s", org_filter)

    return QueryPlan(
        intent=intent,
        mode=mode,
        kind=kind,
        org_filter=org_filter,
        org_norm_id=org_norm_id,
        target_name=getattr(slots, "target_name", None),
        event_name=getattr(slots, "event_name", None),
        period_start=getattr(slots, "period_start", None),
        period_end=getattr(slots, "period_end", None),
        relation=data.get("relation"),
        entity_type=None,
        limit=limit,
        llm_calls=len(inner),
    )
