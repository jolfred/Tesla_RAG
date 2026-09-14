import json
import re
import uuid
from pathlib import Path

from backend.embeddings.vec_search import VectorSearcher
from backend.rag.answer_generator import AnswerGenerator
from backend.rag.graph_planner import GraphPlanner
from backend.rag.query_router import QueryRouter
from backend.utils.logger import setup_logger

logger = setup_logger("searcher")

# ТЕСТ п.11: struct без вектора — контекст только из постов-источников фактов.
# Откат: True. Тогда struct снова подмешивает векторный top-5.
STRUCT_USE_VECTOR = False

_YEAR_RE = re.compile(r"(?:19|20)\d{2}")


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
        self._router = None
        self._planner = None
        self._vec = None
        self._answer_gen = None
        self._communities = None

    def _get_router(self):
        if self._router is None:
            self._router = QueryRouter()
        return self._router

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

    def search(self, question: str, top_k: int = 8, include_context: bool = False) -> dict:
        logger.info("GraphRAG search: '%s'", question)

        # Sink'и полных обменов с LLM (панель «Рентген»): по одному списку
        # на вызов, живут в локалях — параллельные запросы не перемешиваются.
        router_sink: list = []
        planner_sink: list = []
        answer_sink: list = []

        mode = self._get_router().route(question, trace_sink=router_sink)
        logger.info("Question mode: %s", mode)

        graph_facts = []
        posts = []
        source_posts = []
        communities = []
        sources = []
        media = []

        # Год из вопроса — один раз, на все пути (п.8, только на время теста).
        year = question_year(question)
        year_period = (f"{year}-01-01", f"{year}-12-31") if year else (None, None)

        # Трейс конвейера для панели «Рентген» (только по запросу).
        trace: dict = {"router": {"mode": mode}, "planner": None}
        plan_debug: dict = {}

        if mode in ("struct", "local"):
            plan = None
            try:
                plan = self._get_planner().plan(question, trace_sink=planner_sink)
                # Точная резолюция организации (C4) до выполнения запроса.
                plan["org_exact"] = self._get_planner().resolve_org_exact(
                    plan.get("org_filter")
                )
                graph_facts, plan_debug = self._get_planner().execute(plan)
                trace["planner"] = {
                    "plan": plan,
                    "cypher": plan_debug.get("cypher"),
                    "params": plan_debug.get("params", {}),
                }
            except Exception as e:
                logger.warning("Planner execution failed: %s", e)
            # Temporal-приоритет (п.10): свежие факты первыми.
            try:
                graph_facts.sort(key=_fact_date, reverse=True)
            except Exception:
                pass
            if graph_facts:
                # Контекст — ИМЕННО посты-источники фактов (п.11, тест).
                # Работает и для local: у фактов entity_detail есть links с URL.
                source_posts = self._resolve_source_posts(graph_facts)
                if mode == "struct" and STRUCT_USE_VECTOR:
                    try:
                        posts = self._get_vec().search(question, top_k=5)
                    except Exception as e:
                        logger.warning("Vector search failed: %s", e)
                # Сидовые факты (group://) — подмешиваем тексты карточек (п.10).
                # После вектора, с дедупом: карточка — baseline, а не дубль.
                try:
                    cards = self._cards_for_fact_sources(graph_facts)
                    seen = {p.get("post_url") for p in posts}
                    posts = [c for c in cards if c["post_url"] not in seen] + posts
                except Exception as e:
                    logger.warning("Group card resolve failed: %s", e)
            else:
                # П.9: граф молчит — не сдаёмся, вектор отдельным блоком.
                # "Нет данных" разрешено, только если оба источника пусты.
                try:
                    posts = self._get_vec().search(question, top_k=5)
                except Exception as e:
                    logger.warning("Vector fallback failed: %s", e)
            if mode == "struct":
                # Период: из плана, иначе год из вопроса (п.8).
                pstart = (plan or {}).get("period_start") or year_period[0]
                pend = (plan or {}).get("period_end") or year_period[1]
                if pstart or pend:
                    source_posts = _filter_posts_by_period(source_posts, pstart, pend)
                    posts = _filter_posts_by_period(posts, pstart, pend)
                # units: полный состав из карточки по имени (факты из постов
                # могут не ссылаться на group:// — это дополнение к общему правилу).
                if plan and plan.get("intent") == "units":
                    try:
                        cards = self._group_card_posts(plan.get("org_filter"))
                        seen = {p.get("post_url") for p in posts}
                        posts = [c for c in cards if c["post_url"] not in seen] + posts
                    except Exception as e:
                        logger.warning("Group card injection failed: %s", e)

        elif mode == "global":
            communities = self._load_communities()
            posts = []

        else:  # basic
            try:
                posts = self._get_vec().search(question, top_k=top_k)
            except Exception as e:
                logger.warning("Vector search failed: %s", e)
            if year_period[0] or year_period[1]:
                posts = _filter_posts_by_period(posts, *year_period)

        answer, blocks = self._get_answer_gen().generate(
            question,
            mode=mode,
            graph_facts=graph_facts,
            posts=posts,
            source_posts=source_posts,
            communities=communities,
            trace_sink=answer_sink,
        )

        # источники: сначала URL из фактов графа (релевантны периоду),
        # затем из векторных постов
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

        if include_context:
            planner_extra = ""
            cypher = (plan_debug or {}).get("cypher")
            if cypher:
                planner_extra = (
                    f"=== CYPHER ===\n{cypher}\n\n"
                    f"=== ПАРАМЕТРЫ ===\n"
                    f"{json.dumps((plan_debug or {}).get('params', {}), ensure_ascii=False, indent=2)}\n\n"
                    f"=== СТРОКИ ГРАФА ===\n"
                    f"{json.dumps((graph_facts or [])[:20], ensure_ascii=False, indent=2)}"
                )
            calls = [
                {"title": "Вызов 1 — роутер", "text": _fmt_call_window(router_sink)},
                {"title": "Вызов 2 — планировщик", "text": _fmt_call_window(planner_sink, planner_extra)},
                {"title": "Вызов 3 — ответ", "text": _fmt_call_window(answer_sink)},
            ]
        else:
            calls = None
            trace = None

        return {
            "answer": answer,
            "sources": sources,
            "media": media,
            "mode": mode,
            "facts_count": len(graph_facts),
            "posts_used": len(posts) + len(source_posts),
            # Панель «Рентген»: три окна вызовов дословно. Только по запросу.
            "context": blocks if include_context else None,
            "trace": trace,
            "calls": calls,
        }

    def close(self):
        if self._planner is not None:
            self._planner.close()
            self._planner = None