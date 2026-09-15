from backend.config import LLM_PROVIDER
from backend.rag.facts import Fact, rows_to_facts
from backend.utils.gigachat_client import GigaChatClient
from backend.utils.logger import setup_logger

logger = setup_logger("answer_generator")

BASE_PROMPT = """Ты — Хранитель Летописи Штаба студенческих отрядов КГЭУ «Тесла».
Твоя цель — 100% историческая достоверность. Не придумывай факты.
Отвечай на русском языке на основе предоставленного контекста.

Правила:
1. Отвечай только на основе предоставленного контекста из базы знаний.
2. Правило тишины: если НИ граф, НИ посты не дали релевантного для ответа — отвечай: «В архивах нет данных». Молчать запрещено, если хоть один источник релевантен. Если источники релевантны, но точного ответа в них нет (например, спрашивают «с какого времени», а есть только упоминания в роли без даты назначения) — изложи, что известно, и честно отметь пробел: «точная дата в архивах отсутствует».
3. При перечислении («все X», «какие мероприятия», «какие отряды») называй конкретные названия по порядку, используй списки.
4. Если вопрос содержит период (например «с начала 2026») — явно упоминай в ответе, к какому периоду относятся данные.
5. Если запрошены данные «за всё время», а в контексте есть данные только за часть периодов — честно укажи это ограничение.
6. Ссылайся на конкретные публикации (URL постов), если они есть в контексте.
7. Не выдумывай названия, имена и даты, которых нет в контексте.
8. Если в контексте есть карточка группы (URL вида group://…) — она является авторитетным справочником: перечисли ВСЕ отряды/подразделения из её раздела «Описание» (как написано в карточке), не усекая список.
9. Если карточка группы перечисляет отряды по направлениям (строительное, педагогическое и т.д.) — сохраняй эту группировку в ответе.
10. Даты (чек-лист достоверности):
    - Различай дату публикации поста и фактическую дату события. У фактов из графа две даты: «с <дата>» = подтверждённое событие назначения (выборы/назначение описаны в посте), «упоминание в посте от <дата>» = человек просто упомянут в роли. Второе НИКОГДА не пересказывай как «занимает должность с <дата>».
    - Год в вопросе сверяй с датами в квадратных скобках у постов; посты нужного года — основание для ответа, остальные — игнор.
    - Зимние выезды часто захватывают два разных года — указывай оба, если контекст их даёт.
11. Должности: статусы меняются ежегодно. Привязывай должность к конкретному году. Строго различай «кандидат», «боец», «командир», «экс-командир» (пометка [экс/бывший] у факта = бывший, не действующий). Не путай посты в отряде с должностями в Штабе вуза или на проекте.
12. Планы и факты: весенние анонсы выездов могут не совпадать с реальностью. Если контекст содержит и анонс, и итоговый пост — опирайся на итоговый и отметь расхождение.
13. Награды: проверяй, кому именно из списка людей в посте принадлежит конкретная награда; награда отряда целиком — отдельно от наград его бойцов.
14. Свежее важнее старого: при расхождении фактов о текущем составе предпочитай факт с более поздней датой события; карточку группы используй как baseline и явно отмечай расхождение («по карточке X, но пост от <дата> сообщает: Y»).
15. Антитавтология: запрещены предложения, пересказывающие тип связи без новой информации («осуществляет командование», «является участником»). Каждый факт излагай, только если он добавляет роль/дату/источник, иначе опускай."""

# Версия промптов ответа (для наблюдаемости: сравнение метрик до/после).
# v4: BASE+NARRATIVE как были + правило 17, плюс SHORT для struct-fallback.
ANSWER_PROMPT_VERSION = "v4"

GLOBAL_EXTRAS = """
Дополнительно: это резюме сообществ знаний (тематических групп сущностей). 
Обобщи главные темы и выводы, перечисли ключевые события/людей, упомянутые в резюме.
"""

# Короткий промпт struct-fallback ответов (п.6 отзыва: Летопись не сокращалась).
# Только grounding-контракт: факты уже чистые (строгий Cypher + supersede),
# 15 правил не нужны. Полный BASE_PROMPT остаётся для basic/global.
SHORT_PROMPT = """Ты — Хранитель Летописи Штаба студенческих отрядов КГЭУ «Тесла».
Отвечай на русском языке только на основе предоставленного контекста.

Правила:
1. Не придумывай факты: ни имён, ни должностей, ни дат вне контекста.
2. Если ни один источник не релевантен — отвечай: «В архивах нет данных».
3. Даты назначений («с <дата>») бери только из фактов графа с event_date;
   «упоминание в посте от <дата>» никогда не пересказывай как дату назначения.
4. Поздравления (в т.ч. с днём рождения) не подтверждают дату назначения.
5. Иерархия — только при PART_OF-факте или прямой формулировке поста
   («входит в состав», «подразделение»); «связанные сообщества» — не связь.
6. Ссылайся на URL постов-источников, если они есть в контексте."""

# Фаза 5: правило 16 — прямой фикс домысла «который является частью Штаба».
# Список «связанные сообщества» и соседство групп в VK — НЕ структурная связь.
NARRATIVE_PROMPT = BASE_PROMPT + """
16. Не делай выводов об организационной иерархии и подчинённости из списка
«связанные сообщества» и соседства групп в VK — это не структурная связь.
Иерархия — только при явном PART_OF-факте в графе или прямой формулировке
поста («входит в состав», «подразделение», «создан на базе»).
17. Поздравления (в т.ч. с днём рождения) не подтверждают дату назначения
на должность. Дата руководства («с <дата>») — только из явного поста
о выборах/назначении или event_date факта графа. Если пост называет
человека командиром, но даты назначения в корпусе нет — пиши «командир
(дата назначения в архивах не зафиксирована)», а не выводи дату
из соседних упоминаний."""


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
        # Фаза 3: форматируем из Fact (одна точка правды), не из сырого dict.
        # role_title — первичен: «Комиссар», а не голый тип связи COMMANDED.
        facts = rows_to_facts(graph_facts)
        if not facts:
            return "Нет данных графа."
        lines = []
        for f in facts[:60]:
            subj = f.person if f.person != "?" else (f.subject or f.label or "?")
            rel = f.role_title or f.relation or ""
            obj = f.org or ""
            event_date = (f.event_date or "")[:10]
            observed_at = (f.observed_at or "")[:10]
            date = f.date
            job = subj
            if rel:
                job += f" ({rel}"
                if obj:
                    job += f": {obj}"
                job += ")"
            elif obj:
                job += f" — {obj}"
            # Честная семантика дат (пункт 6/10): «с <дата>» только при
            # подтверждённом событии, иначе — «упоминание в посте от».
            if event_date:
                job += f" | с {event_date}"
            elif observed_at:
                job += f" (упоминание в посте от {observed_at})"
            elif date:
                job += f" | дата: {date}"
            line = job
            if f.status:
                line += f" [{f.status}]"
            if f.role_status == "former":
                line += " [экс/бывший]"
            if f.description:
                line += f" — {f.description[:120]}"
            if not (rel or obj or date) and f.links:
                dates = sorted({l.get("date") for l in f.links if l.get("date")})
                if dates:
                    line += f" | даты: {', '.join(d[:10] for d in dates[:5])}"
            urls = []
            if f.source_post_url:
                urls.append(f.source_post_url)
            for l in f.links or []:
                u = l.get("source_post_url")
                if u and u not in urls:
                    urls.append(u)
            for s in f.sources or []:
                if s and s not in urls:
                    urls.append(s)
            if urls:
                line += f" | источники: {', '.join(urls[:3])}"
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
            event_date = (l.get("event_date") or "")[:10]
            observed_at = (l.get("observed_at") or "")[:10]
            date = l.get("date")
            url = l.get("source_post_url")
            part = f"{rel}{' → ' + tgt if tgt else ''}"
            if event_date:
                part += f" (с {event_date})"
            elif observed_at:
                part += f" (упом. {observed_at})"
            elif date:
                part += f" ({str(date)[:10]})"
            if l.get("role_status") == "former":
                part += " [экс]"
            if url:
                part += f" [{url}]"
            parts.append(part)
        return "; ".join(parts)

    def answer_entity_detail(
        self,
        question: str,
        structured: str | None,
        posts: list[dict] | None = None,
        trace_sink: list | None = None,
        facts_block: str | None = None,
    ) -> tuple[str, dict[str, str]]:
        """Фаза 5: структурный блок + LLM-абзац раздельными кусками.

        Галлюцинация в прозе не портит факты: детерминированный блок идёт
        первым как есть, narrative пишется только по постам (NARRATIVE_PROMPT
        с правилом 16). Возвращает (answer, blocks) как generate().
        facts_block (опционально) — факты для контекста нарратива, чтобы
        проза не говорила «нет данных» при живых фактах.
        """
        client = self._get_client()
        if client is None:
            return "Ошибка: LLM недоступна. Проверьте настройки провайдера.", {}
        blocks: dict[str, str] = {}
        if structured:
            blocks["structured"] = structured
        post_lines = []
        for p in (posts or [])[:6]:
            text = p.get("text") or ""
            post_lines.append(
                f"- [{p.get('published_at', '')}] {p.get('group_name', '')}: "
                f"{text[:400]} (URL: {p.get('post_url', '')})"
            )
        if post_lines:
            blocks["posts"] = "=== ПОСТЫ ===\n" + "\n".join(post_lines)
        context = "\n\n".join(
            b for b in [facts_block, blocks.get("posts")] if b
        ) or "Контекст отсутствует."
        user_msg = f"Вопрос: {question}\n\n{context}\n\nОтветь на вопрос пользователя."
        try:
            narrative = client.chat(
                [
                    {"role": "system", "content": NARRATIVE_PROMPT},
                    {"role": "user", "content": user_msg},
                ],
                temperature=0.2,
                max_tokens=3072,
                trace_sink=trace_sink,
            )
        except Exception as e:
            logger.error(f"Entity-detail narrative failed: {e}")
            narrative = ""
        answer = "\n\n".join([b for b in [structured, narrative] if b])
        return answer, blocks

    def generate(
        self,
        question: str,
        mode: str = "struct",
        graph_facts: list[dict] | None = None,
        posts: list[dict] | None = None,
        source_posts: list[dict] | None = None,
        communities: list[dict] | None = None,
        trace_sink: list | None = None,
    ) -> tuple[str, dict[str, str]]:
        """Ответ + секции контекста дословно как ушли в LLM (панель «Рентген»).

        Возвращает (answer, sections). sections: {"graph"|"source_posts"|
        "posts"|"communities": str} — только непустые блоки. Системный промпт
        НЕ отдаём никогда.
        """
        client = self._get_client()
        if client is None:
            return "Ошибка: LLM недоступна. Проверьте настройки провайдера."

        # Struct-fallback: факты уже чистые (строгий Cypher + supersede) —
        # короткий контракт вместо 15 правил (п.6 отзыва). Остальным — полный.
        system_prompt = SHORT_PROMPT if mode == "struct" else BASE_PROMPT
        if mode == "global":
            system_prompt += GLOBAL_EXTRAS

        sections = []
        blocks: dict[str, str] = {}
        if mode == "struct" and graph_facts:
            facts_str = self._fmt_facts(graph_facts)
            block = "=== ФАКТЫ ИЗ ГРАФА ЗНАНИЙ ===\n" + facts_str
            sections.append(block)
            blocks["graph"] = block
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
            block = "=== СУЩНОСТИ И ИХ СВЯЗИ ===\n" + "\n".join(lines)
            sections.append(block)
            blocks["graph"] = block

        if posts:
            post_lines = []
            header = (
                "=== ДОП. ПОСТЫ (карточки групп / векторный fallback) ==="
                if source_posts
                else "=== ПОСТЫ ==="
            )
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
            block = header + "\n" + "\n".join(post_lines)
            sections.append(block)
            blocks["posts"] = block

        if source_posts:
            # Посты-источники фактов (п.11): ИМЕННО те посты, на которых
            # стоят факты графа. Полные тексты, а не обрезки top-5.
            src_lines = []
            for p in source_posts[:6]:
                text = p.get("text") or ""
                src_lines.append(
                    f"- [{p.get('published_at', '')}] {p.get('group_name', '')}: "
                    f"{text[:2000]} (URL: {p.get('post_url', '')})"
                )
            block = "=== ПОСТЫ-ИСТОЧНИКИ ФАКТОВ ===\n" + "\n".join(src_lines)
            sections.append(block)
            blocks["source_posts"] = block

        if mode == "global" and communities:
            comm_lines = []
            for c in communities[:15]:
                summary = (c.get("summary") or "").strip()
                if summary:
                    comm_lines.append(f"• Сообщество {c.get('community_id')}: {summary[:600]}")
            if comm_lines:
                block = "=== РЕЗЮМЕ СООБЩЕСТВ ===\n" + "\n".join(comm_lines)
                sections.append(block)
                blocks["communities"] = block

        context = "\n\n".join(sections) if sections else "Контекст отсутствует."
        user_msg = f"Вопрос: {question}\n\n{context}\n\nОтветь на вопрос пользователя."
        try:
            answer = client.chat(
                [
                    {"role": "system", "content": system_prompt},
                    {"role": "user", "content": user_msg},
                ],
                temperature=0.2,
                max_tokens=3072,
                trace_sink=trace_sink,
            )
            return answer, blocks
        except Exception as e:
            logger.error(f"Answer generation failed: {e}")
            return "Извините, произошла ошибка при генерации ответа.", blocks