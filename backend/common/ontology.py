"""Единый список правил "что можно писать в базу" (Milestone A, пункт 1).

Всё, что отвечает на вопрос о допустимых типах узлов, связей и троек,
живёт только здесь. `backend/indexer/graph_schema_v2.py` — тонкий шим
для обратной совместимости, своей онтологии он больше не содержит.

Изменение этого файла = изменение поведения пайплайна при следующей
экстракции. Версия пайплайна штампуется в граф свойством `prompt_version`
(see PROMPT_VERSION) — так отличаем "факт из старой версии" от "факта из новой".
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

# Допустимые тройки (head, relation, tail). Всё вне списка writer отбрасывает.
# Squad/Organization-WON_AWARD->Award добавлены под Б2 (победы РКТ: награды
# получают отряды целиком, не только люди).
ALLOWED_RELATIONSHIPS: list[tuple[str, str, str]] = [
    ("Person", "HOLDS_ROLE", "Role"),
    ("Person", "MEMBER_OF", "Squad"),
    ("Person", "MEMBER_OF", "Organization"),
    ("Person", "COMMANDED", "Squad"),
    ("Person", "COMMANDED", "Organization"),
    ("Person", "WON_AWARD", "Award"),
    ("Squad", "WON_AWARD", "Award"),
    ("Organization", "WON_AWARD", "Award"),
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

ALLOWED_TRIPLES: frozenset[tuple[str, str, str]] = frozenset(ALLOWED_RELATIONSHIPS)

# Плоский список типов связей (для фильтров и writer).
ALLOWED_REL_TYPES: list[str] = sorted({rel for _, rel, _ in ALLOWED_TRIPLES})

# Структурированные свойства, которые просим у LLM.
# Узлам описание НЕ заказываем (NODE_PROPERTIES = []): узел = {id, type},
# вся фактура живёт на рёбрах — в описаниях узлов был мусор.
NODE_PROPERTIES: list[str] = []
RELATIONSHIP_PROPERTIES: list[str] = [
    "description",
    "role_title",
    "status",
]

# date/observed_at/event_date/source_post_url writer дописывает из метаданных
# поста детерминированно, у LLM их не просим (legacy показал 72% null).

# --- Стоп-лист generic-сущностей ("бесполезные узлы") ---
# Точное совпадение с norm_id (см. backend/common/canon.py) -> дроп узла с логом.
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

# source_model для ветки v2 (dual-model схема на merge_key).
SOURCE_MODEL_V2 = "llmgraph_gigachat"

# Версия пайплайна: штампуется свойством prompt_version на каждый узел/ребро,
# записанный новым пайплайном (Milestone B+). Инкремент при правке промпта,
# схемы или writer. У данных без свойства — версия "до v3" (пилот + сид групп).
PROMPT_VERSION = "v3"


def validate_triple(head_type: str, relation: str, tail_type: str) -> bool:
    """Проверка связи целиком, а не одного её конца (пункт 7).

    Именно эта функция — hard gate перед любым MERGE ребра.
    Закрывает класс Б3b: Person-COMMANDED->Role (тип ребра "разрешён",
    но такая тройка — нет) больше не проскакивает.
    """
    return (
        head_type in ALLOWED_NODES
        and tail_type in ALLOWED_NODES
        and (head_type, relation, tail_type) in ALLOWED_TRIPLES
    )
