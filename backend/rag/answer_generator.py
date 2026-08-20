from backend.config import LLM_PROVIDER
from backend.utils.gigachat_client import GigaChatClient
from backend.utils.logger import setup_logger

logger = setup_logger("answer_generator")

BASE_PROMPT = """Ты — Хранитель Летописи Штаба студенческих отрядов КГЭУ «Тесла».
Отвечай на русском языке на основе предоставленного контекста.

Правила:
1. Отвечай только на основе предоставленного контекста из базы знаний.
2. Если в контексте нет информации для ответа — скажи: «В базе знаний нет информации по этому вопросу».
3. При перечислении («все X», «какие мероприятия», «какие отряды») называй конкретные названия по порядку, используй списки.
4. Если вопрос содержит период (например «с начала 2026») — явно упоминай в ответе, к какому периоду относятся данные.
5. Если запрошены данные «за всё время», а в контексте есть данные только за часть периодов — честно укажи это ограничение.
6. Ссылайся на конкретные публикации (URL постов), если они есть в контексте.
7. Не выдумывай названия, имена и даты, которых нет в контексте.
8. Если в контексте есть карточка группы (URL вида group://…) — она является авторитетным справочником: перечисли ВСЕ отряды/подразделения из её раздела «Описание» (как написано в карточке), не усекая список.
9. Если карточка группы перечисляет отряды по направлениям (строительное, педагогическое и т.д.) — сохраняй эту группировку в ответе."""

GLOBAL_EXTRAS = """
Дополнительно: это резюме сообществ знаний (тематических групп сущностей). 
Обобщи главные темы и выводы, перечисли ключевые события/людей, упомянутые в резюме.
"""


class AnswerGenerator:
    def __init__(self):
        self._client = None
        self._gigachat = None

    def _get_client(self):
        if self._client is not None:
            return self._client

        provider = LLM_PROVIDER

        if provider == "gigachat":
            self._gigachat = GigaChatClient()
            self._client = self._gigachat
        else:
            from backend.utils.gigachat_client import GigaChatClient as GC
            logger.warning("LLM_PROVIDER=%s — использую GigaChat по умолчанию", provider)
            self._gigachat = GC()
            self._client = self._gigachat

        return self._client

    @staticmethod
    def _fmt_facts(graph_facts: list[dict]) -> str:
        if not graph_facts:
            return "Нет данных графа."
        lines = []
        for f in graph_facts[:60]:
            subj = f.get("subject") or f.get("person") or f.get("event") or f.get("id") or "?"
            rel = f.get("relation") or f.get("role_title") or ""
            obj = f.get("object") or f.get("target") or f.get("award") or f.get("org") or f.get("location") or f.get("project") or ""
            date = f.get("date")
            description = f.get("description") or ""
            job = subj
            if rel:
                job += f" ({rel}"
                if obj:
                    job += f": {obj}"
                job += ")"
            elif obj:
                job += f" — {obj}"
            if date:
                job += f" | дата: {date}"
            line = job
            if f.get("status"):
                line += f" [{f['status']}]"
            if description:
                line += f" — {description[:120]}"
            if not (rel or obj or date) and f.get("links"):
                dates = sorted({l.get("date") for l in f["links"] if l.get("date")})
                if dates:
                    line += f" | даты: {', '.join(d[:10] for d in dates[:5])}"
            lines.append("- " + line)
        return "\n".join(lines)

    @staticmethod
    def _fmt_edges(links: list) -> str:
        if not links:
            return ""
        parts = []
        for l in links:
            rel = l.get("rel") or l.get("rtype") or ""
            tgt = l.get("target") or l.get("target_id") or ""
            date = l.get("date")
            parts.append(f"{rel}{' → ' + tgt if tgt else ''}{' (' + date + ')' if date else ''}")
        return "; ".join(parts)

    def generate(
        self,
        question: str,
        mode: str = "struct",
        graph_facts: list[dict] | None = None,
        posts: list[dict] | None = None,
        communities: list[dict] | None = None,
    ) -> str:
        client = self._get_client()
        if client is None:
            return "Ошибка: LLM недоступна. Проверьте настройки провайдера."

        system_prompt = BASE_PROMPT
        if mode == "global":
            system_prompt += GLOBAL_EXTRAS

        sections = []
        if mode == "struct" and graph_facts:
            facts_str = self._fmt_facts(graph_facts)
            sections.append("=== ФАКТЫ ИЗ ГРАФА ЗНАНИЙ ===\n" + facts_str)
        elif mode == "local" and graph_facts:
            lines = []
            for f in graph_facts[:40]:
                node_id = f.get("id") or f.get("subject") or "?"
                ntype = f.get("type") or ""
                desc = f.get("description") or ""
                links = self._fmt_edges(f.get("links") or [])
                line = f"- {node_id} [{ntype}]"
                if desc:
                    line += f": {desc[:150]}"
                if links:
                    line += f" | связи: {links[:200]}"
                lines.append(line)
            sections.append("=== СУЩНОСТИ И ИХ СВЯЗИ ===\n" + "\n".join(lines))

        if posts:
            post_lines = []
            for p in posts[:6]:
                text = p.get("text") or ""
                if (p.get("post_url") or "").startswith("group://"):
                    post_lines.append(
                        f"- [{p.get('group_name', '')}] (URL: {p.get('post_url', '')}):\n{text}"
                    )
                else:
                    post_lines.append(
                        f"- [{p.get('published_at', '')}] {p.get('group_name', '')}: "
                        f"{text[:400]} (URL: {p.get('post_url', '')})"
                    )
            sections.append("=== ПОСТЫ ===\n" + "\n".join(post_lines))

        if mode == "global" and communities:
            comm_lines = []
            for c in communities[:15]:
                summary = (c.get("summary") or "").strip()
                if summary:
                    comm_lines.append(f"• Сообщество {c.get('community_id')}: {summary[:600]}")
            if comm_lines:
                sections.append("=== РЕЗЮМЕ СООБЩЕСТВ ===\n" + "\n".join(comm_lines))

        context = "\n\n".join(sections) if sections else "Контекст отсутствует."
        user_msg = f"Вопрос: {question}\n\n{context}\n\nОтветь на вопрос пользователя."

        try:
            return client.chat(
                [
                    {"role": "system", "content": system_prompt},
                    {"role": "user", "content": user_msg},
                ],
                temperature=0.2,
                max_tokens=3072,
            )
        except Exception as e:
            logger.error(f"Answer generation failed: {e}")
            return "Извините, произошла ошибка при генерации ответа."