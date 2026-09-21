"""entity_detail-путь: структурный блок ролей + LLM-абзац раздельно (Фаза 5).

Вынесено из searcher.py: путь короткий, со своим Cypher (person_roles),
своей фильтрацией поздравлений и своим результатом.
"""

import json

from backend.config import GIGACHAT_MODEL
from backend.observability import langfuse_client as _lf
from backend.observability.checks import run_layer1
from backend.rag.answer_generator import ANSWER_PROMPT_VERSION
from backend.rag.facts import rows_to_facts, supersede_roles
from backend.rag.planner_queries import person_roles_query
from backend.rag.renderers import render_person_roles
from backend.rag.search_utils import (
    _CONGRATS_RE,
    _fact_date,
    _filter_posts_by_period,
    _fmt_call_window,
    narrative_repeats_list,
)
from backend.utils.logger import setup_logger

logger = setup_logger("entity_search")


def search_entity_detail(searcher, question, plan, top_k, include_context,
                         plan_sink, year_period, root,
                         source_model=None, collection="posts") -> dict:
    """Фаза 5: entity_detail — структурный блок ролей + LLM-абзац раздельно."""
    answer_sink: list = []
    graph = searcher._get_planner()._get_graph()
    rows: list = []
    if graph is not None:
        candidate = person_roles_query(plan.target_name or "", source_model)
        if candidate is not None:
            query, params = candidate
            try:
                with _lf.observation(
                    "cypher_exec", as_type="retriever",
                    input={"query": query, "params": params},
                ) as sp:
                    rows = graph.search_cypher(query, params)
                    sp.update(output={"facts_count": len(rows)})
            except Exception as e:
                logger.warning("v2 person roles failed: %s", e)
    try:
        rows.sort(key=_fact_date, reverse=True)
    except Exception:
        pass
    structured = render_person_roles(
        supersede_roles(rows_to_facts(rows)), plan.target_name or "?")
    source_posts = searcher._resolve_source_posts(rows, collection=collection) if rows else []
    try:
        with _lf.observation(
            "vector_search", as_type="retriever",
            input={"question": question, "top_k": 5,
                   "reason": "entity_detail"},
        ) as sp:
            posts = searcher._get_vec().search(question, top_k=5, collection=collection)
            sp.update(output={
                "posts_count": len(posts),
                "urls": [p.get("post_url") for p in posts[:10]],
            })
    except Exception as e:
        logger.warning("Vector search failed: %s", e)
        posts = []
    if year_period[0] or year_period[1]:
        posts = _filter_posts_by_period(posts, *year_period)
    # Поздравления — не биография (п.5 отзыва): выкидываем из контекста
    # нарратива полностью. Осталась пустота — проза по одним фактам.
    narrative_posts = [p for p in source_posts + posts
                       if not _CONGRATS_RE.search(p.get("text") or "")]
    with _lf.observation(
        "llm_answer", as_type="generation", model=GIGACHAT_MODEL,
        input={"question": question,
               "facts_block": ("=== ФАКТЫ ===\n" + structured
                               if structured else None)},
    ) as gen:
        answer, blocks = searcher._get_answer_gen().answer_entity_detail(
            question, structured, narrative_posts,
            trace_sink=answer_sink,
            facts_block=("=== ФАКТЫ ===\n" + structured
                         if structured else None),
        )
        searcher._lf_gen_update(gen, question, answer)
    if structured and narrative_repeats_list(
            rows, answer, structured):
        logger.warning("Entity narrative repeats list, dropping prose")
        answer, blocks = structured, {}
    sources = searcher._collect_sources("local", rows, source_posts, posts)
    if include_context:
        calls = [
            {"title": "Вызов 1 — план (v2)",
             "text": _fmt_call_window(plan_sink,
                    f"=== ПЛАН ===\n{json.dumps(plan.to_dict(), ensure_ascii=False, indent=2)}")},
            {"title": "Вызов 2 — ответ", "text": _fmt_call_window(answer_sink)},
        ]
    else:
        calls = None
    llm_calls = plan.llm_calls + len(answer_sink)
    trace_id = _lf.current_trace_id()
    root.update(output=answer, metadata={
        "intent": plan.intent, "mode": "local", "kind": plan.kind,
        "target_name": plan.target_name,
        "prompt_version": ANSWER_PROMPT_VERSION,
        "facts_count": len(rows),
        "posts_used": len(posts) + len(source_posts),
        "llm_calls": llm_calls,
    })
    run_layer1(trace_id, answer, rows,
               ([structured] if structured else [])
               + [p.get("text") or "" for p in narrative_posts])
    return {
        "answer": answer,
        "sources": sources,
        "media": searcher._collect_media(source_posts, posts),
        "previews": searcher._build_previews(source_posts, posts),
        "mode": "local",
        "facts_count": len(rows),
        "posts_used": len(posts) + len(source_posts),
        "context": blocks if include_context else None,
        "trace": None,
        "trace_id": trace_id,
        "calls": calls,
        "llm_calls": llm_calls,
    }
