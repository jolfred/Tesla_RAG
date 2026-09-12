import json
from pathlib import Path

from backend.embeddings.vec_search import VectorSearcher
from backend.rag.answer_generator import AnswerGenerator
from backend.rag.graph_planner import GraphPlanner
from backend.rag.query_router import QueryRouter
from backend.utils.logger import setup_logger

logger = setup_logger("searcher")


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
                parts = [f"Группа: {name}"]
                if meta.get("status"):
                    parts.append(f"Статус: {meta['status']}")
                if meta.get("members_count"):
                    parts.append(f"Участников: {meta['members_count']}")
                if meta.get("description"):
                    parts.append(f"Описание: {meta['description']}")
                posts.append({
                    "post_url": f"group://{meta.get('domain', '')}",
                    "published_at": "",
                    "group_name": name,
                    "text": "\n".join(parts),
                })
        return posts

    def search(self, question: str, top_k: int = 8) -> dict:
        logger.info("GraphRAG search: '%s'", question)

        mode = self._get_router().route(question)
        logger.info("Question mode: %s", mode)

        graph_facts = []
        posts = []
        communities = []
        sources = []
        media = []

        if mode in ("struct", "local"):
            plan = None
            try:
                plan = self._get_planner().plan(question)
                graph_facts = self._get_planner().execute(plan)
            except Exception as e:
                logger.warning("Planner execution failed: %s", e)
            if mode == "struct":
                # векторный контекст как дополнение к фактам
                try:
                    posts = self._get_vec().search(question, top_k=5)
                except Exception as e:
                    logger.warning("Vector search failed: %s", e)
                # если в плане есть период — отсекаем посты вне периода
                # (иначе в контекст лезут старые посты и тянут ответ назад)
                if plan and (plan.get("period_start") or plan.get("period_end")):
                    posts = _filter_posts_by_period(
                        posts, plan.get("period_start"), plan.get("period_end")
                    )
                # для списка отрядов подмешиваем карточку группы с полным составом
                if plan and plan.get("intent") == "units":
                    try:
                        cards = self._group_card_posts(plan.get("org_filter"))
                        if cards:
                            posts = cards + posts
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

        answer = self._get_answer_gen().generate(
            question,
            mode=mode,
            graph_facts=graph_facts,
            posts=posts,
            communities=communities,
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
        for p in posts[:8]:
            url = p.get("post_url")
            title = p.get("group_name") or url
            if url:
                src = {"title": title, "url": url}
                if src not in sources:
                    sources.append(src)

        return {
            "answer": answer,
            "sources": sources,
            "media": media,
            "mode": mode,
            "facts_count": len(graph_facts),
            "posts_used": len(posts),
        }

    def close(self):
        if self._planner is not None:
            self._planner.close()
            self._planner = None