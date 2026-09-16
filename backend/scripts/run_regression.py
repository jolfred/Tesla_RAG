"""L4: регресс по Langfuse Dataset `regression-golden-set` через Experiment API.

Каждый запуск виден в UI как отдельный run. Живые вызовы:
Neo4j + Qdrant + GigaChat. max_concurrency=1 (общий searcher).
Exit 1 при любом провале (для CI).
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
    args = ap.parse_args()

    lf = _lf.get_langfuse()
    assert lf is not None, "Langfuse недоступен (LANGFUSE_ENABLED=1?)"
    with open("backend/rag/golden_set.yaml", encoding="utf-8") as f:
        for c in yaml.safe_load(f):
            _EXPECT[c["id"]] = {"contains": c.get("contains", []),
                                "excludes": c.get("excludes", [])}
    import datetime
    run_name = args.run_name or datetime.datetime.now().strftime(
        "regression-%Y%m%d-%H%M%S")
    only = set(args.ids.split(",")) if args.ids else None

    ds = lf.get_dataset(DATASET)
    items = [i for i in ds.items
             if only is None or (i.metadata or {}).get("case_id") in only]
    if not items:
        print("нет кейсов (импорт: import_golden_to_langfuse.py)")
        return 2
    result = lf.run_experiment(
        name=DATASET,
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
    return 1 if fails else 0


if __name__ == "__main__":
    raise SystemExit(main())
