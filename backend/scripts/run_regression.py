"""Прогон Dataset через Experiment API (регресс или пул вопросов).

По умолчанию: `regression-golden-set` + golden_set.yaml (строго, exit 1).
Пул: --dataset question-pool --yaml backend/rag/question_pool.yaml
(мягко: пустые ожидания проходят, оценка — Слой 1 + судья в UI).

Каждый запуск виден в UI как отдельный run. Живые вызовы:
Neo4j + Qdrant + GigaChat. max_concurrency=1 (общий searcher).
"""
from __future__ import annotations

import argparse

import yaml

from backend.observability import langfuse_client as _lf
from backend.rag.searcher import GraphRAGSearcher
from backend.utils.logger import setup_logger

logger = setup_logger("lf_regression")

DATASET = "regression-golden-set"
_searcher: GraphRAGSearcher | None = None
# Источник истины ожиданий — yaml (правки действуют сразу, без
# переимпорта датасета; expected_output в Langfuse — копия).
_EXPECT: dict = {}


def _get_searcher() -> GraphRAGSearcher:
    global _searcher
    if _searcher is None:
        _searcher = GraphRAGSearcher()
    return _searcher


def task(*, item, **kwargs) -> dict:
    q = item.input["question"] if isinstance(item.input, dict) \
        else item.input.get("question", "")
    res = _get_searcher().search(q)
    return {"answer": res.get("answer", ""),
            "trace_id": res.get("trace_id"),
            "intent": None}  # intent доберём из трейса при нужде


def evaluator_contains(*, input, output, expected_output, metadata,
                       **kwargs) -> dict:
    exp = expected_output or {}
    case_id = (metadata or {}).get("case_id")
    if case_id in _EXPECT:  # yaml — источник истины
        exp = _EXPECT[case_id]
    answer = (output.get("answer", "") or "") if isinstance(output, dict) \
        else str(output or "")
    if exp.get("expect_silence"):
        ok = "архивах нет данных" in answer.lower()
        return {"name": "regression_contains", "value": 1.0 if ok else 0.0,
                "comment": f"expect_silence, silent={ok}"}
    missing = [s for s in exp.get("contains", []) if s not in answer]
    present_bad = [s for s in exp.get("excludes", []) if s in answer]
    ok = not missing and not present_bad
    return {"name": "regression_contains", "value": 1.0 if ok else 0.0,
            "comment": f"missing={missing} forbidden_present={present_bad}"}


def main() -> int:
    ap = argparse.ArgumentParser(description="Регресс через Langfuse")
    ap.add_argument("--ids", default=None,
                    help="подмножество case_id через запятую")
    ap.add_argument("--run-name", default=None)
    ap.add_argument("--dataset", default=DATASET)
    ap.add_argument("--yaml", default="backend/rag/golden_set.yaml")
    ap.add_argument("--soft", action="store_true",
                    help="пул: exit 0 даже при провалах (смотреть UI)")
    args = ap.parse_args()

    lf = _lf.get_langfuse()
    assert lf is not None, "Langfuse недоступен (LANGFUSE_ENABLED=1?)"
    with open(args.yaml, encoding="utf-8") as f:
        for c in yaml.safe_load(f):
            _EXPECT[c["id"]] = {"contains": c.get("contains", []),
                                "excludes": c.get("excludes", []),
                                "expect_silence": bool(
                                    c.get("expect_silence", False))}
    import datetime
    prefix = "pool" if args.dataset != DATASET else "regression"
    run_name = args.run_name or datetime.datetime.now().strftime(
        f"{prefix}-%Y%m%d-%H%M%S")
    only = set(args.ids.split(",")) if args.ids else None

    ds = lf.get_dataset(args.dataset)
    items = [i for i in ds.items
             if only is None or (i.metadata or {}).get("case_id") in only]
    if not items:
        print("нет кейсов (импорт: import_golden_to_langfuse.py)")
        return 2
    result = lf.run_experiment(
        name=args.dataset,
        run_name=run_name,
        data=list(items),
        task=task,
        evaluators=[evaluator_contains],
        max_concurrency=1,
    )
    scores = []
    for ir in getattr(result, "item_results", []) or []:
        for ev in getattr(ir, "evaluations", []) or []:
            name = ev.get("name") if isinstance(ev, dict) \
                else getattr(ev, "name", "")
            value = ev.get("value") if isinstance(ev, dict) \
                else getattr(ev, "value", 0)
            scores.append((name, value))
    fails = [s for s in scores
             if s[0] == "regression_contains"
             and float(s[1] or 0) < 1.0]
    print(f"run={run_name} items={len(items)} fails={len(fails)}")
    try:
        _get_searcher().close()
    except Exception:
        pass
    # Строгий регресс падает в CI; мягкий пул — нет (оценка в UI).
    return 1 if (fails and not args.soft) else 0


if __name__ == "__main__":
    raise SystemExit(main())
