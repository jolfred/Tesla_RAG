"""Регресс-раннер (Фаза 4): golden_set.yaml одной командой.

Гоняет вопросы через searcher с source=regression (трейсы пишутся
в стор автоматически), сверяет intent/слоты/contains/excludes/шаблон,
кладёт историю в storage/logs/regression_<ts>.json. Exit code 1 при провале.
    .venv/bin/python -m backend.scripts.run_regression [--ids q1,q2] [--db PATH]
"""

from __future__ import annotations

import argparse
import json
from datetime import datetime, timezone
from pathlib import Path

import yaml

from backend.observability.store import TraceStore
from backend.rag.searcher import GraphRAGSearcher

GOLDEN_PATH = Path(__file__).resolve().parent.parent / "rag" / "golden_set.yaml"
LOGS_DIR = (
    Path(__file__).resolve().parent.parent.parent / "storage" / "logs"
)


def _span_output(trace: dict | None, name: str, key: str):
    for sp in (trace or {}).get("spans") or []:
        if sp.get("name") == name:
            try:
                return json.loads(sp.get("output_json") or "{}").get(key)
            except ValueError:
                return None
    return None


def check_case(searcher: GraphRAGSearcher, store: TraceStore,
               case: dict) -> dict:
    q = case["question"]
    out = searcher.search(q, source="regression")
    trace = store.fetch_trace(out.get("trace_id") or "")
    answer = out.get("answer", "")
    fails: list[str] = []

    def _fail(msg: str) -> None:
        fails.append(msg)

    if case.get("expect_intent") and (trace or {}).get("intent") != case["expect_intent"]:
        _fail(f"intent: {(trace or {}).get('intent')} != {case['expect_intent']}")
    for k, v in (case.get("expect_slots") or {}).items():
        if k == "org_filter":
            got = (trace or {}).get("org_filter_raw")
        elif k == "target_name":
            got = _span_output(trace, "classify_and_plan", "target_name")
        else:
            got = None
        if got != v and not (got and v in got):
            _fail(f"slot {k}: {got!r} != {v!r}")
    for s in case.get("expect_contains") or []:
        if s not in answer:
            _fail(f"answer не содержит {s!r}")
    for s in case.get("expect_excludes") or []:
        if s in answer:
            _fail(f"answer содержит запрещённое {s!r}")
    head = case.get("expect_template_start") or ""
    if head and not answer.startswith(head):
        _fail(f"answer не начинается с {head!r}")
    return {"id": case.get("id"), "question": q,
            "trace_id": out.get("trace_id"),
            "llm_calls": out.get("llm_calls"),
            "ok": not fails, "fails": fails}


def main() -> int:
    ap = argparse.ArgumentParser(description="Регресс по golden-набору")
    ap.add_argument("--ids", default=None)
    ap.add_argument("--db", default=None)
    args = ap.parse_args()

    cases = yaml.safe_load(GOLDEN_PATH.read_text(encoding="utf-8"))
    if args.ids:
        want = set(args.ids.split(","))
        cases = [c for c in cases if c.get("id") in want]
    store = TraceStore(args.db)
    searcher = GraphRAGSearcher()
    results = []
    try:
        for case in cases:
            print(f"[{case.get('id')}] {case['question'][:60]}...", flush=True)
            try:
                res = check_case(searcher, store, case)
            except Exception as e:
                res = {"id": case.get("id"), "question": case["question"],
                       "ok": False, "fails": [f"exception: {e}"]}
            results.append(res)
            print(("  OK " if res["ok"] else "  FAIL ") + "; ".join(res.get("fails", []) or ["-"]), flush=True)
    finally:
        searcher.close()
        store.close()

    ok = sum(1 for r in results if r["ok"])
    LOGS_DIR.mkdir(parents=True, exist_ok=True)
    path = LOGS_DIR / ("regression_%s.json"
                       % datetime.now(timezone.utc).strftime("%Y%m%d_%H%M%S"))
    path.write_text(json.dumps(results, ensure_ascii=False, indent=2),
                    encoding="utf-8")
    print(f"{ok}/{len(results)} passed, saved {path}")
    return 0 if ok == len(results) else 1


if __name__ == "__main__":
    raise SystemExit(main())
