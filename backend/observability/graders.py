"""Оценка ответов RAG-ассистента по трёхбалльной шкале (0/1/2).

Основной способ — LLM-оценка через GigaChat: модель читает вопрос, эталонный
ответ, ключевые факты и рубричные требования, возвращает score и обоснование.
Запасной способ — эвристика по вхождению ключевых фактов (используется, если
GigaChat-оценка не вернула валидный JSON).
"""

import json
import re

from backend.utils.gigachat_client import GigaChatClient
from backend.utils.logger import setup_logger

logger = setup_logger("benchmark_grader")

_JSON_RE = re.compile(r"\{.*\}", re.DOTALL)

GRADER_SYSTEM_PROMPT = """Ты — независимый эксперт, оценивающий ответы RAG-ассистента «Хранитель Летописи» (Штаб студенческих отрядов КГЭУ «Тесла»).

Оцени ответ ассистента по трёхбалльной шкале:
- 2 — «Отлично»: ответ полностью достоверен; приведены точные имена, отряды, годы и численные значения; соблюдена субординация должностей; приставка «экс-» на месте.
- 1 — «Частично»: ключевая информация найдена верно, но допущены мелкие неточности (пропущена приставка «экс-», перепутана буква в фамилии, ошибка в одной цифре или одном факте).
- 0 — «Провал»: модель совершила галлюцинацию, приписала чужую награду/факт, перепутала год или место, либо не смогла найти документ, который есть в базе.

Правила:
1. Оценивай содержание, а не форму. Ответ считается верным, если в нём есть все ключевые факты из списка.
2. «Нет данных» для отрицательных тестов — это правильный достоверный ответ, а не провал.
3. Оценку 1 ставь только за мелкие неточности, не искажающие смысл.
4. Оценку 0 ставь за выдуманные имена/награды/цифры или за пропуск данных, которые должны были быть найдены.

Верни строго JSON без пояснений в формате:
{"score": 0, "reason": "краткое обоснование на русском"}"""


def _build_user_message(case: dict, answer: str) -> str:
    facts = "\n".join(f"- {f}" for f in case.get("key_facts", []))
    parts = [
        f"Вопрос: {case['question']}",
        f"\nЭталонный ответ:\n{case['expected']}",
    ]
    if facts:
        parts.append(f"\nКлючевые факты, которые должны быть в ответе:\n{facts}")
    hints = case.get("rubric_hints")
    if hints:
        parts.append(f"\nОсобые требования к оценке:\n{hints}")
    parts.append(f"\nОтвет ассистента:\n{answer}")
    return "\n".join(parts)


class LLMGrader:
    """Оценка ответа через GigaChat по рубрике 0/1/2."""

    def __init__(self, model: str | None = None, retries: int = 2):
        self._client = GigaChatClient(model=model)
        self._retries = retries

    def grade(self, case: dict, answer: str) -> dict:
        last_error: Exception | None = None
        user_msg = _build_user_message(case, answer)
        for attempt in range(self._retries + 1):
            try:
                raw = self._client.chat(
                    [
                        {"role": "system", "content": GRADER_SYSTEM_PROMPT},
                        {"role": "user", "content": user_msg},
                    ],
                    temperature=0.1,
                    max_tokens=1024,
                )
                match = _JSON_RE.search(raw or "")
                if not match:
                    raise ValueError(f"No JSON in grader response: {raw[:200]!r}")
                data = json.loads(match.group(0))
                score = int(data.get("score", -1))
                if score not in (0, 1, 2):
                    raise ValueError(f"Bad score {score!r}")
                return {"score": score, "reason": data.get("reason", "")}
            except Exception as e:
                last_error = e
                logger.warning(
                    "Grader retry %d/%d for %s: %s",
                    attempt + 1,
                    self._retries + 1,
                    case.get("id"),
                    e,
                )
        raise last_error


def _fact_in_text(fact: str, text: str) -> bool:
    """Проверка факта с учётом падежей: точное вхождение, стем фразы или все слова."""
    if fact in text:
        return True
    stem = fact[:-2] if len(fact) > 5 else ""
    if stem and stem in text:
        return True
    words = re.findall(r"\d+|[а-яё]+", fact.lower())
    words = [w for w in words if len(w) > 2 or w.isdigit()]
    if not words:
        return False
    return all(
        (w in text) or (w[:-1] in text if len(w) > 3 else False) for w in words
    )


def heuristic_score(case: dict, answer: str) -> int | None:
    """Запасная эвристика: доля ключевых фактов, найденных в ответе."""
    facts = [f for f in case.get("key_facts", []) if f]
    if not facts:
        return None
    text = (answer or "").lower()
    hits = sum(1 for f in facts if _fact_in_text(f.lower(), text))
    ratio = hits / len(facts)
    if ratio >= 0.85:
        return 2
    if ratio >= 0.5:
        return 1
    return 0
