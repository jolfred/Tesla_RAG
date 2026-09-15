import json
import re
import uuid
from pathlib import Path

from backend.embeddings.vec_search import VectorSearcher
from backend.rag import query_planner
from backend.rag.answer_generator import AnswerGenerator
from backend.rag.facts import rows_to_facts, supersede_roles
from backend.rag.graph_planner import GraphPlanner
from backend.rag.planner_queries import person_roles_query
from backend.rag.renderers import (
    render,
    render_commanders,
    render_person_roles,
)
from backend.rag.units_enrich import (
    enrich_units,
    parse_unit_directions,
    render_units_enriched,
)
from backend.utils.logger import setup_logger

logger = setup_logger("searcher")

_YEAR_RE = re.compile(r"(?:19|20)\d{2}")
_BULLET_RE = re.compile(r"^\s*(?:•|[-*]|\d+[.)])\s+")
_CONGRATS_RE = re.compile(r"дн[её]м рождения|поздравля|happy birthday", re.IGNORECASE)
_DATE_HINT_RE = re.compile(r"(?:19|20)\d{2}|\d{1,2}[.\-]\d{1,2}[.\-]\d{2,4}")


def _fmt_call_window(exchanges: list[dict], extra: str = "") -> str:
    """Одно окно вызова: полные тексты запроса и ответа (fidelity).

    Ретраи складываются стопкой с заголовками попыток. Ничего не режется.
    """
    parts = []
    for i, ex in enumerate(exchanges):
        if len(exchanges) > 1:
            parts.append(f"--- попытка {i + 1} ---")
        for m in ex.get("messages") or []:
            parts.append(f"=== {str(m.get('role', '')).upper()} ===\n{m.get('content', '')}")
        parts.append(f"=== ОТВЕТ ===\n{ex.get('response', '')}")
    if extra:
        parts.append(extra)
    return "\n\n".join(parts) if parts else "— вызовов не было —"


def narrative_repeats_list(graph_facts: list[dict], answer: str,
                           structured: str | None) -> bool:
    """Проза дублирует блок (п.1 отзыва): прозу выкинуть.

    Два триггера: (а) список — ≥2 буллетов с именами, покрывающих
    ≥ половины имён; (б) пересказ без добавленной стоимости — ≥ половины
    имён и ни одной даты (проза ничего не добавила к блоку).
    Абзац с парой упоминаний и датами — не дубль, пропускаем.
    """
    prose = (answer[len(structured):]
             if structured and answer.startswith(structured) else answer)
    if not prose.strip():
        return False
    names = set()
    for f in rows_to_facts(graph_facts or []):
        for v in (f.person, f.subject, f.label):
            if v and v != "?" and len(v) > 2:
                names.add(v.lower())
    if not names:
        return False
    lowered = prose.lower()
    mentioned = {n for n in names if n in lowered}
    if len(mentioned) * 2 < len(names):
        return False
    named_bullets = sum(
        1 for ln in prose.splitlines()
        if _BULLET_RE.match(ln) and any(n in ln.lower() for n in names)
    )
    if named_bullets >= 2:
        return True
    # Пересказ без дат: проза повторила БОЛЬШИНСТВО имён, но информации
    # не добавила (ровно половина — пограничный случай, пропускаем).
    return len(mentioned) * 2 > len(names) and _DATE_HINT_RE.search(prose) is None


def question_year(question: str) -> str | None:
    """Единственный год из вопроса (п.8) — для фильтра на всех путях."""
    years = sorted(set(_YEAR_RE.findall(question or "")))
    return years[0] if len(years) == 1 else None


def _fact_date(f: dict) -> str:
    """Дата факта для сортировки (п.10): сначала event_date, при отсутствии —
    observed_at/date. Свежее важнее, но дата события бьёт дату упоминания."""
    events, mentions = [], []

    def _add(d, bucket):
        if d:
            bucket.append((d or "")[:10])

    _add(f.get("event_date"), events)
    _add(f.get("observed_at"), mentions)
    _add(f.get("date"), mentions)
    for link in f.get("links") or []:
        if isinstance(link, dict):
            _add(link.get("event_date"), events)
            _add(link.get("observed_at"), mentions)
            _add(link.get("date"), mentions)
    pool = events or mentions
    return max(pool) if pool else ""


def _filter_posts_by_period(
    posts: list[dict], start: str | None, end: str | None
) -> list[dict]:
    """Оставить посты внутри [start, end] (ISO). Карточки group:// — всегда."""
    if not start and not end:
        return posts
    kept = []
    for p in posts:
        url = p.get("post_url") or ""
        if url.startswith("group://"):
            kept.append(p)
            continue
        pub = (p.get("published_at") or "")[:10]
        if not pub:
            kept.append(p)
            continue
        if start and pub < start[:10]:
            continue
        if end and pub > end[:10]:
            continue
        kept.append(p)
    return kept


COMMUNITIES_PATH = (
    Path(__file__).resolve().parent.parent.parent / "storage" / "communities.json"
)
GROUPS_DIR = Path(__file__).resolve().parent.parent.parent / "storage" / "groups"


class GraphRAGSearcher:
    def __init__(self):
        self._planner = None
        self._vec = None
        self._answer_gen = None
        self._communities = None

    def _get_planner(self):
        if self._planner is None:
            self._planner = GraphPlanner()
        return self._planner

    def _get_vec(self):
        if self._vec is None:
            self._vec = VectorSearcher()
        return self._vec

    def _get_answer_gen(self):
        if self._answer_gen is None:
            self._answer_gen = AnswerGenerator()
        return self._answer_gen

    def _load_communities(self) -> list[dict]:
        if self._communities is None:
            if COMMUNITIES_PATH.exists():
                try:
                    with open(COMMUNITIES_PATH, encoding="utf-8") as f:
                        self._communities = json.load(f)
                except Exception as e:
                    logger.warning("Failed to load communities: %s", e)
                    self._communities = []
            else:
                self._communities = []
        return self._communities

    @staticmethod
    def _format_card(meta: dict) -> dict:
        # Единый формат карточки — backend/indexer/group_meta.group_card_text
        # (с контактами и связями, а не только описание).
        from backend.indexer.group_meta import group_card_text

        return {
            "post_url": f"group://{meta.get('domain', '')}",
            "published_at": "",
            "group_name": meta.get("name", ""),
            "text": group_card_text(meta),
        }

    def _group_card_posts(self, org_filter: str | None) -> list[dict]:
        if not org_filter:
            return []
        key = org_filter.lower()
        posts = []
        if GROUPS_DIR.exists():
            for path in sorted(GROUPS_DIR.glob("groups_*.json")):
                try:
                    with path.open(encoding="utf-8") as f:
                        meta = json.load(f)
                except (json.JSONDecodeError, OSError):
                    continue
                name = meta.get("name", "")
                if key not in name.lower():
                    continue
                posts.append(self._format_card(meta))
        return posts

    def _cards_for_fact_sources(self, graph_facts: list[dict]) -> list[dict]:
        """Карточки групп-источников фактов (seed-baseline, п.10).

        Сидовые факты ссылаются на group://domain — без текста карточки
        отвечающий видит голый триплет. Подмешиваем тексты карточек,
        чтобы было на что опереться («по карточке X, но пост сообщает Y»).
        """
        domains: list[str] = []
        for f in graph_facts or []:
            urls = [f.get("source_post_url")]
            for link in f.get("links") or []:
                if isinstance(link, dict):
                    urls.append(link.get("source_post_url"))
            urls += list(f.get("sources") or [])
            for u in urls:
                if u and u.startswith("group://"):
                    d = u[len("group://"):]
                    if d and d not in domains:
                        domains.append(d)
        cards = []
        for d in domains:
            path = GROUPS_DIR / f"groups_{d}.json"
            try:
                with path.open(encoding="utf-8") as fh:
                    cards.append(self._format_card(json.load(fh)))
            except (OSError, json.JSONDecodeError):
                continue
        return cards

    def _resolve_source_posts(
        self, graph_facts: list[dict], cap: int = 8
    ) -> list[dict]:
        """Полные тексты постов-источников фактов (п.11, главная проблема).

        URL берём из фактов (source_post_url + links), тексты — точечным
        Qdrant retrieve по uuid5(post_url). Без эмбеддингов, без поиска:
        в контекст идут ИМЕННО те посты, на которых стоят факты.
        """
        urls: list[str] = []
        for f in graph_facts or []:
            cands = [f.get("source_post_url")]
            for link in f.get("links") or []:
                if isinstance(link, dict):
                    cands.append(link.get("source_post_url"))
            for s in f.get("sources") or []:
                cands.append(s)
            for u in cands:
                if u and u not in urls and not u.startswith("group://"):
                    urls.append(u)
        urls = urls[:cap]
        if not urls:
            return []
        try:
            qclient = self._get_vec()._get_qdrant()
            ids = [str(uuid.uuid5(uuid.NAMESPACE_URL, u)) for u in urls]
            points = qclient.retrieve(
                collection_name="posts",
                ids=ids,
                with_payload=True,
                with_vectors=False,
            )
            by_id = {str(p.id): (p.payload or {}) for p in points}
        except Exception as e:
            logger.warning("Source-post resolve failed: %s", e)
            return []
        posts = []
        for u, pid in zip(urls, ids):
            pay = by_id.get(pid) or {}
            text = pay.get("text_clean") or ""
            if not text:
                logger.warning("Source post %s has no text in Qdrant", u)
                continue
            posts.append(
                {
                    "post_url": u,
                    "published_at": pay.get("published_at", ""),
                    "group_name": pay.get("group_name", ""),
                    "text": text,
                }
            )
        logger.info("Resolved %d/%d source posts", len(posts), len(urls))
        return posts

    def _unit_metas(self) -> dict[int, dict]:
        """Метафайлы групп по numeric group_id (для обогащения units)."""
        if self.__dict__.get("_unit_metas_cache") is None:
            metas: dict[int, dict] = {}
            if GROUPS_DIR.exists():
                for path in sorted(GROUPS_DIR.glob("groups_*.json")):
                    try:
                        with path.open(encoding="utf-8") as f:
                            meta = json.load(f)
                        metas[int(meta.get("group_id") or 0)] = meta
                    except (json.JSONDecodeError, OSError, ValueError, TypeError):
                        continue
            self.__dict__["_unit_metas_cache"] = metas
        return self.__dict__["_unit_metas_cache"]

    def _unit_card_meta(self, org_filter: str | None) -> dict | None:
        """Сырая мета карточки штаба по имени (направления отрядов).

        'Тесла' подстрокой матчится и на ПрогрессLAB (файл раньше
        по алфавиту, описание пустое) — выбираем карточку с направлениями.
        """
        if not org_filter:
            return None
        key = org_filter.lower()
        best = None
        if GROUPS_DIR.exists():
            for path in sorted(GROUPS_DIR.glob("groups_*.json")):
                try:
                    with path.open(encoding="utf-8") as f:
                        meta = json.load(f)
                except (json.JSONDecodeError, OSError):
                    continue
                if key not in (meta.get("name") or "").lower():
                    continue
                if best is None:
                    best = meta
                if parse_unit_directions(meta.get("description") or ""):
                    return meta
        return best

    def _render_units(self, graph_facts: list[dict], org_name: str,
                      org_filter: str | None) -> str | None:
        """Units с обогащением из карточки штаба, фолбэк — plain-рендер."""
        meta = self._unit_card_meta(org_filter)
        if meta is not None:
            directions = parse_unit_directions(meta.get("description") or "")
            if directions:
                names = [
                    f.label or f.person
                    for f in rows_to_facts(graph_facts)
                ]
                items = enrich_units(names, directions, self._unit_metas())
                return render_units_enriched(items, org_name)
        return render("units", graph_facts, org_name)

    @staticmethod
    def _collect_sources(mode, graph_facts, source_posts, posts) -> list[dict]:
        # источники: сначала URL из фактов графа (релевантны периоду),
        # затем из векторных постов
        sources = []
        if mode == "struct":
            for f in graph_facts:
                urls: list[str] = []
                if f.get("source_post_url"):
                    urls.append(f["source_post_url"])
                for link in f.get("links") or []:
                    u = link.get("source_post_url")
                    if u and u not in urls:
                        urls.append(u)
                for s in f.get("sources") or []:
                    if s and s not in urls:
                        urls.append(s)
                for url in urls[:3]:
                    src = {"title": f.get("event") or f.get("person") or url, "url": url}
                    if src not in sources:
                        sources.append(src)
        for p in (source_posts + posts)[:10]:
            url = p.get("post_url")
            title = p.get("group_name") or url
            if url:
                src = {"title": title, "url": url}
                if src not in sources:
                    sources.append(src)
        return sources

    def search(self, question: str, top_k: int = 8, include_context: bool = False) -> dict:
        """Единый путь: classify+plan, диспетчер enumerable/narrative.

        enumerable + факты -> шаблон (0 LLM-вызовов на ответе);
        шаблон пуст -> vector-fallback -> LLM; оба пусты -> тишина без LLM.
        """
        logger.info("GraphRAG search: '%s'", question)
        plan_sink: list = []
        answer_sink: list = []

        plan = query_planner.classify_and_plan(
            question,
            graph=self._get_planner()._get_graph(),
            trace_sink=plan_sink,
        )
        mode = plan.mode
        logger.info("plan: intent=%s mode=%s kind=%s org=%s",
                    plan.intent, mode, plan.kind, plan.org_norm_id)

        graph_facts: list = []
        posts: list = []
        source_posts: list = []
        communities: list = []
        plan_debug: dict = {}

        year = question_year(question)
        year_period = (f"{year}-01-01", f"{year}-12-31") if year else (None, None)

        if plan.intent == "entity_detail" and plan.target_name:
            return self._search_v2_entity(
                question, plan, top_k, include_context, plan_sink, year_period)

        if mode in ("struct", "local"):
            try:
                graph_facts, plan_debug = self._get_planner().execute_v2(
                    plan.to_dict()
                )
            except Exception as e:
                logger.warning("v2 planner execution failed: %s", e)
            try:
                graph_facts.sort(key=_fact_date, reverse=True)
            except Exception:
                pass
            if graph_facts:
                source_posts = self._resolve_source_posts(graph_facts)
                try:
                    cards = self._cards_for_fact_sources(graph_facts)
                    seen = {p.get("post_url") for p in posts}
                    posts = [c for c in cards if c["post_url"] not in seen] + posts
                except Exception as e:
                    logger.warning("Group card resolve failed: %s", e)
            else:
                try:
                    posts = self._get_vec().search(question, top_k=5)
                except Exception as e:
                    logger.warning("Vector fallback failed: %s", e)
            if mode == "struct":
                pstart = plan.period_start or year_period[0]
                pend = plan.period_end or year_period[1]
                if pstart or pend:
                    source_posts = _filter_posts_by_period(source_posts, pstart, pend)
                    posts = _filter_posts_by_period(posts, pstart, pend)
                # units: полный состав из карточки по имени (паритет с v1 —
                # без неё LLM-ответ перечисляет 2 отряда вместо всех).
                if plan.intent == "units":
                    try:
                        cards = self._group_card_posts(plan.org_filter)
                        seen = {p.get("post_url") for p in posts}
                        posts = [c for c in cards if c["post_url"] not in seen] + posts
                    except Exception as e:
                        logger.warning("Group card injection failed: %s", e)
        elif mode == "global":
            communities = self._load_communities()
        else:  # basic
            try:
                posts = self._get_vec().search(question, top_k=top_k)
            except Exception as e:
                logger.warning("Vector search failed: %s", e)
            if year_period[0] or year_period[1]:
                posts = _filter_posts_by_period(posts, *year_period)

        rendered = None
        narrative_answer = None
        narrative_blocks: dict = {}
        if plan.kind == "enumerable" and mode == "struct" and graph_facts:
            org_name = plan.org_filter or plan.org_norm_id or "архив"
            structured = None
            if plan.intent == "commanders":
                # Одно кресло — один действующий (без имён, только даты).
                # Старый состав гаснет сам, когда приходит новый.
                graph_facts = [
                    {**f, "role_status": nf.role_status}
                    for f, nf in zip(
                        graph_facts,
                        supersede_roles(rows_to_facts(graph_facts)),
                    )
                ]
                structured = render_commanders(
                    rows_to_facts(graph_facts), org_name)
            elif plan.intent == "units":
                # Units — чистый список без прозы (решение пользователя).
                rendered = self._render_units(
                    graph_facts, org_name, plan.org_filter)
            else:
                structured = render(plan.intent, graph_facts, org_name)
            if structured:
                # Стиль Летописи всем шаблонам (п.3–4 отзыва): детерминированный
                # блок фактов + живой нарратив. Факты не выдумываются.
                # LLM легла — answer_entity_detail вернёт голый шаблон.
                narrative_answer, narrative_blocks = (
                    self._get_answer_gen().answer_entity_detail(
                        question, structured, source_posts + posts,
                        trace_sink=answer_sink,
                        facts_block="=== ФАКТЫ ===\n" + structured,
                    )
                )
                if not (narrative_answer or "").strip():
                    narrative_answer = None
                elif "в архивах нет данных" in (
                        narrative_answer or "").lower():
                    # Модель промолчала при живых фактах — оставляем
                    # детерминированный блок, противоречие выкидываем.
                    logger.warning("Narrative silence despite facts, dropping")
                    narrative_answer, narrative_blocks = structured, {}
                elif narrative_repeats_list(
                        graph_facts, narrative_answer, structured):
                    # Проза продублировала блок списком — оставляем блок.
                    logger.warning("Narrative repeats list, dropping prose")
                    narrative_answer, narrative_blocks = structured, {}

        answer_sink_note = ""
        if narrative_answer is not None:
            answer = narrative_answer
            blocks = narrative_blocks if include_context else {}
        elif rendered is not None:
            answer = rendered
            blocks = {"rendered": rendered} if include_context else {}
        elif plan.kind == "enumerable" and not graph_facts and not posts:
            # Оба источника пусты — тишина сразу, без LLM-вызова.
            answer = "В архивах нет данных"
            blocks = {}
            answer_sink_note = "— без LLM (оба источника пусты) —"
        else:
            answer, blocks = self._get_answer_gen().generate(
                question,
                mode=mode,
                graph_facts=graph_facts,
                posts=posts,
                source_posts=source_posts,
                communities=communities,
                trace_sink=answer_sink,
            )

        sources = self._collect_sources(mode, graph_facts, source_posts, posts)

        if include_context:
            cypher = (plan_debug or {}).get("cypher")
            planner_extra = (
                f"=== ПЛАН ===\n"
                f"{json.dumps(plan.to_dict(), ensure_ascii=False, indent=2)}\n\n"
                f"=== CYPHER ===\n{cypher}\n\n"
                f"=== ПАРАМЕТРЫ ===\n"
                f"{json.dumps((plan_debug or {}).get('params', {}), ensure_ascii=False, indent=2)}\n\n"
                f"=== СТРОКИ ГРАФА ===\n"
                f"{json.dumps((graph_facts or [])[:20], ensure_ascii=False, indent=2)}"
                if cypher else
                f"=== ПЛАН ===\n"
                f"{json.dumps(plan.to_dict(), ensure_ascii=False, indent=2)}"
            )
            answer_text = (
                _fmt_call_window(answer_sink)
                if answer_sink
                else (answer_sink_note or f"=== ШАБЛОН ===\n{answer}")
            )
            calls = [
                {"title": "Вызов 1 — план (v2)",
                 "text": _fmt_call_window(plan_sink, planner_extra)},
                {"title": "Вызов 2 — ответ", "text": answer_text},
            ]
        else:
            calls = None

        return {
            "answer": answer,
            "sources": sources,
            "media": [],
            "mode": mode,
            "facts_count": len(graph_facts),
            "posts_used": len(posts) + len(source_posts),
            "context": blocks if include_context else None,
            "trace": None,
            "calls": calls,
            # Метрика Фазы 6: сколько LLM-вызовов ушло на вопрос.
            "llm_calls": plan.llm_calls + len(answer_sink),
        }

    def _search_v2_entity(
        self, question, plan, top_k, include_context, plan_sink, year_period
    ) -> dict:
        """Фаза 5: entity_detail — структурный блок ролей + LLM-абзац раздельно."""
        answer_sink: list = []
        graph = self._get_planner()._get_graph()
        rows: list = []
        if graph is not None:
            candidate = person_roles_query(plan.target_name or "")
            if candidate is not None:
                query, params = candidate
                try:
                    rows = graph.search_cypher(query, params)
                except Exception as e:
                    logger.warning("v2 person roles failed: %s", e)
        try:
            rows.sort(key=_fact_date, reverse=True)
        except Exception:
            pass
        structured = render_person_roles(
            supersede_roles(rows_to_facts(rows)), plan.target_name or "?")
        source_posts = self._resolve_source_posts(rows) if rows else []
        try:
            posts = self._get_vec().search(question, top_k=5)
        except Exception as e:
            logger.warning("Vector search failed: %s", e)
            posts = []
        if year_period[0] or year_period[1]:
            posts = _filter_posts_by_period(posts, *year_period)
        # Поздравления — не биография (п.5 отзыва): выкидываем из контекста
        # нарратива полностью. Осталась пустота — проза по одним фактам.
        narrative_posts = [p for p in source_posts + posts
                           if not _CONGRATS_RE.search(p.get("text") or "")]
        answer, blocks = self._get_answer_gen().answer_entity_detail(
            question, structured, narrative_posts, trace_sink=answer_sink,
            facts_block=("=== ФАКТЫ ===\n" + structured if structured else None),
        )
        if structured and narrative_repeats_list(
                rows, answer, structured):
            logger.warning("Entity narrative repeats list, dropping prose")
            answer, blocks = structured, {}
        sources = self._collect_sources("local", rows, source_posts, posts)
        if include_context:
            calls = [
                {"title": "Вызов 1 — план (v2)",
                 "text": _fmt_call_window(plan_sink,
                        f"=== ПЛАН ===\n{json.dumps(plan.to_dict(), ensure_ascii=False, indent=2)}")},
                {"title": "Вызов 2 — ответ", "text": _fmt_call_window(answer_sink)},
            ]
        else:
            calls = None
        return {
            "answer": answer,
            "sources": sources,
            "media": [],
            "mode": "local",
            "facts_count": len(rows),
            "posts_used": len(posts) + len(source_posts),
            "context": blocks if include_context else None,
            "trace": None,
            "calls": calls,
            "llm_calls": plan.llm_calls + len(answer_sink),
        }

    def close(self):
        if self._planner is not None:
            self._planner.close()
            self._planner = None