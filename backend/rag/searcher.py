import json
import uuid
from pathlib import Path

from backend.config import GIGACHAT_MODEL
from backend.embeddings.vec_search import VectorSearcher
from backend.observability import langfuse_client as _lf
from backend.observability.checks import run_layer1 as _run_layer1
from backend.rag import query_planner
from backend.rag.answer_generator import ANSWER_PROMPT_VERSION, AnswerGenerator
from backend.rag.entity_search import search_entity_detail
from backend.rag.facts import rows_to_facts, supersede_roles
from backend.rag.graph_planner import GraphPlanner
from backend.rag.renderers import (
    render,
    render_commanders,
)
from backend.rag.search_utils import (
    _fact_date,
    _filter_posts_by_period,
    _fmt_call_window,
    narrative_repeats_list,
    question_year,
)
from backend.rag.units_enrich import (
    enrich_units,
    parse_unit_directions,
    render_units_enriched,
)
from backend.utils.logger import setup_logger

logger = setup_logger("searcher")
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

    def _load_communities(self, project_slug: str | None = None) -> list[dict]:
        if project_slug:
            path = COMMUNITIES_PATH.with_name(f"communities_proj_{project_slug}.json")
            if not path.exists():
                return []
            try:
                with open(path, encoding="utf-8") as f:
                    return json.load(f)
            except Exception as e:
                logger.warning("Failed to load communities: %s", e)
                return []
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
        self, graph_facts: list[dict], cap: int = 8, collection: str = "posts"
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
                collection_name=collection,
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
                    "photos": [p for p in (pay.get("photos") or [])
                               if isinstance(p, str) and p.startswith("http")],
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
    def _collect_media(source_posts, posts, per_post: int = 4,
                       total: int = 8) -> list[str]:
        """Фото для карточки ответа: все фото поста (до per_post), затем
        фото из других постов (до total всего). Порядок — по релевантности
        постов (source_posts, затем векторные). Дубли режутся."""
        media: list[str] = []
        for p in (source_posts or []) + (posts or []):
            for url in (p.get("photos") or [])[:per_post]:
                if url not in media:
                    media.append(url)
                if len(media) >= total:
                    return media
        return media

    @staticmethod
    def _build_previews(source_posts, posts, limit: int = 4) -> list[dict]:
        """Превью VK-постов для лендинга: первые посты с текстом (в идеале
        с фото). group://-карточки пропускаем. Порядок — по релевантности."""
        previews: list[dict] = []
        for p in (source_posts or []) + (posts or []):
            if len(previews) >= limit:
                break
            url = p.get("post_url") or ""
            if not url or url.startswith("group://"):
                continue
            text = (p.get("text") or "").strip()
            photos = [u for u in (p.get("photos") or [])
                      if isinstance(u, str) and u.startswith("http")]
            if not text and not photos:
                continue
            previews.append({
                "group_name": p.get("group_name") or "",
                "published_at": p.get("published_at") or "",
                "text": text[:280],
                "photo": photos[0] if photos else "",
                "url": url,
            })
        return previews

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

    def _lf_usage(self, prompt_text=None, completion_text=None) -> dict:
        try:
            lu = getattr(
                getattr(self._get_answer_gen(), "_gigachat", None),
                "last_usage", None)
        except Exception:
            lu = None
        return _lf.usage_details(lu, prompt_text, completion_text)

    def _lf_gen_update(self, gen, question, answer) -> None:
        """usage + cost (тарифы из env, нет тарифов — только токены)."""
        usage = self._lf_usage(question, answer)
        kw: dict = {"output": answer, "usage_details": usage}
        cost, rub = _lf.generation_cost(usage, GIGACHAT_MODEL)
        if cost is not None:
            kw["cost_details"] = cost
        gen.update(**kw)
        if rub is not None:
            _lf.score(_lf.current_trace_id(), rub[0], rub[1],
                      data_type="NUMERIC")

    def search(
        self,
        question: str,
        top_k: int = 8,
        include_context: bool = False,
        project_slug: str | None = None,
    ) -> dict:
        """Единый путь: classify+plan, диспетчер enumerable/narrative.

        enumerable + факты -> шаблон (0 LLM-вызовов на ответе);
        шаблон пуст -> vector-fallback -> LLM; оба пусты -> тишина без LLM.

        Трейсинг — Langfuse (best-effort, ответы не ломает).
        """
        with _lf.observation("answer", input=question) as root:
            try:
                return self._search_inner(question, top_k, include_context, root, project_slug)
            finally:
                _lf.flush()

    def _search_inner(self, question, top_k, include_context, root, project_slug=None) -> dict:
        logger.info("GraphRAG search: '%s'", question)
        plan_sink: list = []
        answer_sink: list = []

        if not project_slug:  # wiki-first; в проектах — старый путь
            try:
                from backend.wiki.loop import try_wiki_answer

                with _lf.observation("wiki_loop", input=question) as wsp:
                    wr = try_wiki_answer(question)
                    wsp.update(output=(wr or {}).get("answer", "")[:500])
                if wr and wr.get("answer"):
                    root.update(output=wr["answer"], metadata={"mode": "wiki", "pages": wr.get("pages", [])})
                    return {
                        "answer": wr["answer"],
                        "sources": wr.get("sources", []),
                        "media": [],
                        "previews": [],
                        "mode": "wiki",
                        "facts_count": len(wr.get("pages", [])),
                        "posts_used": len(wr.get("sources", [])),
                        "context": {"wiki_pages": wr.get("pages", [])} if include_context else None,
                        "trace": None,
                        "trace_id": _lf.current_trace_id(),
                        "calls": None,
                        "llm_calls": 0,
                    }
            except Exception as e:
                logger.warning("wiki_loop failed, fallback to RAG: %s", e)

        if project_slug:
            from backend.admin.indexing import project_collection, project_source_model

            source_model: str | None = project_source_model(project_slug)
            collection = project_collection(project_slug)
        else:
            source_model = None
            collection = "posts"

        with _lf.observation("classify_and_plan", input=question) as sp:
            # source_model — только для проекта: дефолтный путь зовёт
            # classify_and_plan ровно как раньше (совместимость с моками).
            plan_kwargs: dict = {"trace_sink": plan_sink}
            if source_model:
                plan_kwargs["source_model"] = source_model
            plan = query_planner.classify_and_plan(
                question,
                graph=self._get_planner()._get_graph(),
                **plan_kwargs,
            )
            sp.update(output=plan.to_dict())
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
            return search_entity_detail(
                self, question, plan, top_k, include_context, plan_sink,
                year_period, root, source_model, collection)

        plan_dict = plan.to_dict()
        if source_model:
            plan_dict["source_model"] = source_model
        if mode in ("struct", "local"):
            try:
                with _lf.observation(
                    "cypher_exec", as_type="retriever",
                    input=plan_dict,
                ) as sp:
                    graph_facts, plan_debug = self._get_planner().execute_v2(
                        plan_dict
                    )
                    sp.update(output={
                        "facts_count": len(graph_facts),
                        "cypher": (plan_debug or {}).get("cypher"),
                    })
            except Exception as e:
                logger.warning("v2 planner execution failed: %s", e)
            try:
                graph_facts.sort(key=_fact_date, reverse=True)
            except Exception:
                pass
            if graph_facts:
                source_posts = self._resolve_source_posts(graph_facts, collection=collection)
                try:
                    cards = self._cards_for_fact_sources(graph_facts)
                    seen = {p.get("post_url") for p in posts}
                    posts = [c for c in cards if c["post_url"] not in seen] + posts
                except Exception as e:
                    logger.warning("Group card resolve failed: %s", e)
            else:
                try:
                    with _lf.observation(
                        "vector_search", as_type="retriever",
                        input={"question": question, "top_k": 5,
                               "reason": "struct_fallback"},
                    ) as sp:
                        posts = self._get_vec().search(question, top_k=5, collection=collection)
                        sp.update(output={
                            "posts_count": len(posts),
                            "urls": [p.get("post_url") for p in posts[:10]],
                        })
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
            communities = self._load_communities(project_slug)
        else:  # basic
            try:
                with _lf.observation(
                    "vector_search", as_type="retriever",
                    input={"question": question, "top_k": top_k},
                ) as sp:
                    posts = self._get_vec().search(question, top_k=top_k, collection=collection)
                    sp.update(output={
                        "posts_count": len(posts),
                        "urls": [p.get("post_url") for p in posts[:10]],
                    })
            except Exception as e:
                logger.warning("Vector search failed: %s", e)
            if year_period[0] or year_period[1]:
                posts = _filter_posts_by_period(posts, *year_period)

        rendered = None
        narrative_answer = None
        narrative_blocks: dict = {}
        structured = None
        if plan.kind == "enumerable" and mode == "struct" and graph_facts:
            org_name = plan.org_filter or plan.org_norm_id or "архив"
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
                narrative_answer, narrative_blocks = None, {}
                with _lf.observation(
                    "llm_answer", as_type="generation", model=GIGACHAT_MODEL,
                    input={"question": question, "facts_block": structured},
                ) as gen:
                    narrative_answer, narrative_blocks = (
                        self._get_answer_gen().answer_entity_detail(
                            question, structured, source_posts + posts,
                            trace_sink=answer_sink,
                            facts_block="=== ФАКТЫ ===\n" + structured,
                        )
                    )
                    self._lf_gen_update(gen, question, narrative_answer)
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
            with _lf.observation(
                "llm_answer", as_type="generation", model=GIGACHAT_MODEL,
                input={"question": question, "mode": mode,
                       "facts_count": len(graph_facts),
                       "posts_count": len(posts) + len(source_posts)},
            ) as gen:
                answer, blocks = self._get_answer_gen().generate(
                    question,
                    mode=mode,
                    graph_facts=graph_facts,
                    posts=posts,
                    source_posts=source_posts,
                    communities=communities,
                    trace_sink=answer_sink,
                )
                self._lf_gen_update(gen, question, answer)

        sources = self._collect_sources(mode, graph_facts, source_posts, posts)

        llm_calls = plan.llm_calls + len(answer_sink)
        trace_id = _lf.current_trace_id()
        root.update(output=answer, metadata={
            "intent": plan.intent, "mode": mode, "kind": plan.kind,
            "org_norm_id": plan.org_norm_id,
            "prompt_version": ANSWER_PROMPT_VERSION,
            "facts_count": len(graph_facts),
            "posts_used": len(posts) + len(source_posts),
            "llm_calls": llm_calls,
        })
        _ctx = ([structured] if structured else []) + [
            (p.get("text") or "") for p in (source_posts + posts)]
        _run_layer1(trace_id, answer, graph_facts, _ctx)

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
            "media": self._collect_media(source_posts, posts),
            "previews": self._build_previews(source_posts, posts),
            "mode": mode,
            "facts_count": len(graph_facts),
            "posts_used": len(posts) + len(source_posts),
            "context": blocks if include_context else None,
            "trace": None,
            "trace_id": trace_id,
            "calls": calls,
            # Сколько LLM-вызовов ушло на вопрос.
            "llm_calls": llm_calls,
        }

    def close(self):
        if self._planner is not None:
            self._planner.close()
            self._planner = None