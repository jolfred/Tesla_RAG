"""Роутер запросов: классификация STRUCT / LOCAL / GLOBAL / BASIC."""

from backend.utils.gigachat_client import GigaChatClient
from backend.utils.logger import setup_logger

logger = setup_logger("query_router")

ROUTER_PROMPT = """Ты — роутер запросов к базе знаний о студенческих отрядах КГЭУ «Тесла».
Определи, каким методом лучше ответить на вопрос. Варианты:
- "struct": вопрос о конкретных фактах/сущностях, которые можно достать структурированным запросом
  (мероприятия за период, командиры/роли, участники, победители/награды, проекты, локации, конкретная сущность).
- "local": вопрос о конкретной сущности/лице/организации, требующий контекста вокруг неё.
- "global": широкий вопрос о корпусе в целом (темы, тенденции, «что вообще происходило», обобщения).
- "basic": открытый вопрос, лучше всего отвечаемый поиском по постам.

Ответь строго JSON: {"mode": "struct | local | global | basic"}
Никакого дополнительного текста."""

ROUTER_SCHEMA = {
    "type": "object",
    "properties": {
        "mode": {"type": "string", "enum": ["struct", "local", "global", "basic"]},
    },
    "required": ["mode"],
}


class QueryRouter:
    def __init__(self):
        self._llm = None

    def _get_llm(self) -> GigaChatClient:
        if self._llm is None:
            self._llm = GigaChatClient()
        return self._llm

    def route(self, question: str) -> str:
        llm = self._get_llm()
        try:
            data = llm.extract_json(ROUTER_PROMPT, question, schema=ROUTER_SCHEMA)
            mode = data.get("mode")
            if mode in ("struct", "local", "global", "basic"):
                return mode
        except Exception as e:
            logger.warning("Router LLM failed: %s", e)
        return "basic"