"""Онтология v2 для LLMGraphTransformer.

Унифицирует три рассинхронизированных источника:
- backend/indexer/prompts.py (8 типов, 10 связей)
- schema/graph_schema.json (12 типов)
- backend/rag/planner_queries.py (интенты units/commanders/members/...)

Главные изменения относительно legacy:
- Squad выделен из Organization (вопросы про отряды — главный кейс).
- COMMANDED отделён от MEMBER_OF (интент commanders).
- Узел Post/Publication в allowed_nodes НЕ вводим (не плодить мусор) —
  provenance идёт свойствами рёбер + :Post-узлом на записи (neo4j_writer_v2).
"""

ALLOWED_NODES: list[str] = [
    "Person",
    "Squad",
    "Organization",
    "Event",
    "Project",
    "Award",
    "Location",
    "Role",
    "Profession",
]

# org_type для Squad/Organization (совместимо с legacy-схемой и planner).
ORG_TYPES: list[str] = ["hq", "lso", "university", "external", "partner"]

# Допустимые тройки (head, relation, tail). Всё вне списка strict_mode отбрасывает.
ALLOWED_RELATIONSHIPS: list[tuple[str, str, str]] = [
    ("Person", "HOLDS_ROLE", "Role"),
    ("Person", "MEMBER_OF", "Squad"),
    ("Person", "MEMBER_OF", "Organization"),
    ("Person", "COMMANDED", "Squad"),
    ("Person", "COMMANDED", "Organization"),
    ("Person", "WON_AWARD", "Award"),
    ("Person", "PARTICIPATED_IN", "Event"),
    ("Squad", "PARTICIPATED_IN", "Event"),
    ("Squad", "PART_OF", "Organization"),
    ("Squad", "ORGANIZED", "Event"),
    ("Organization", "ORGANIZED", "Event"),
    ("Organization", "PART_OF", "Organization"),
    ("Event", "HELD_AT", "Location"),
    ("Person", "TRAINED_IN", "Profession"),
    ("Organization", "SUPPORTED_BY", "Organization"),
    ("Squad", "SUPPORTED_BY", "Organization"),
]

# Плоский список типов связей (для strict_mode-фильтров и writer-v2).
ALLOWED_REL_TYPES: list[str] = sorted({rel for _, rel, _ in ALLOWED_RELATIONSHIPS})

# Структурированные свойства, которые просим у LLM.
# Узлам описание НЕ заказываем (NODE_PROPERTIES = []): узел = {id, type},
# вся фактура живёт на рёбрах. Так решено: в описаниях узлов был мусор.
NODE_PROPERTIES: list[str] = []
RELATIONSHIP_PROPERTIES: list[str] = [
    "description",
    "role_title",
    "status",
]

# date/source_post_url writer-v2 дописывает из метаданных поста детерминированно,
# у LLM их не просим (legacy показал 72% null).

# --- Стоп-лист generic-сущностей ("бесполезные узлы") ---
# Точное совпадение с norm_id (см. normalize.py) -> дроп узла с логом.
STOP_NODES: frozenset[str] = frozenset(
    {
        "лето",
        "зима",
        "весна",
        "осень",
        "команда",
        "ребята",
        "гость",
        "гости",
        "гость мероприятия",
        "участник",
        "участники",
        "студенты",
        "студент",
        "активисты",
        "активист",
        "мероприятие",
        "конкурс",
        "праздник",
        "море",
        "горы",
        "теслаteam",
    }
)

# source_model для новой ветки (dual-model схема на merge_key уже готова).
SOURCE_MODEL_V2 = "llmgraph_gigachat"
