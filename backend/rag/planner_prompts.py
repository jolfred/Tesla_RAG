"""Промпт и JSON-схема планировщика графовых запросов."""

PLANNER_PROMPT = """Ты — планировщик запросов к графу знаний о студенческих отрядах КГЭУ «Тесла».
Определи по вопросу пользователя параметры запроса. Доступные типы сущностей (nodes): Person, Organization, Role, Award, Event, Project, Location, Profession.
Типы связей (edges): HOLDS_ROLE, WON_AWARD, MEMBER_OF, PARTICIPATED_IN, ORGANIZED, PART_OF, LOCATED_IN, HELD_AT, TRAINED_IN, SUPPORTED_BY.

Ответь строго JSON:
{
  "intent": "units | events_in_period | commanders | members | winners | projects | locations | entity_detail | general",
  "entity_type": null,
  "target_name": null,
  "period_start": "YYYY-MM-DD | null",
  "period_end": "YYYY-MM-DD | null",
  "org_filter": null,
  "relation": null,
  "limit": 20
}

Правила:
- "units": вопрос о списке отрядов/подразделений, входящих в штаб или организацию (напр. "перечисли все отряды штаба", "какие отряды входят в штаб"). org_filter задавайте по штабу.
- "events_in_period": вопрос о мероприятиях/событиях (в т.ч. с датой/периодом).
- "commanders": вопрос о командирах/комиссарах/руководителях/ролях/контактах/составе штаба или отряда (напр. "кто командир", "какие контакты", "перечисли комсостав"). org_filter задавайте по названию штаба/отряда.
- "members": вопрос об участниках/членах отрядов.
- "winners": вопрос о победителях/наградах.
- "projects": вопрос о проектах/трудовых семестрах.
- "locations": вопрос о местах/локациях.
- "entity_detail": вопрос о конкретной сущности (target_name задан) и НЕ о командирах/контактах/составе.
- "general": всё остальное — вернуть 0,0 в period если период не указан.
- org_filter: "Тесла" если вопрос о штабе/отрядах Тесла, иначе null.
- period_start/period_end только если вопрос явно указывает период (например "с начала 2026" -> "2026-01-01").
- limit: число результатов (обычно 20, для "назови всех" — 100)."""

PLANNER_SCHEMA = {
    "type": "object",
    "properties": {
        "intent": {"type": "string"},
        "entity_type": {"type": ["string", "null"]},
        "target_name": {"type": ["string", "null"]},
        "period_start": {"type": ["string", "null"]},
        "period_end": {"type": ["string", "null"]},
        "org_filter": {"type": ["string", "null"]},
        "relation": {"type": ["string", "null"]},
        "limit": {"type": "integer"},
    },
    "required": [
        "intent", "entity_type", "target_name",
        "period_start", "period_end", "org_filter", "relation", "limit",
    ],
}
