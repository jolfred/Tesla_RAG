"""L3: выборочный судья — LLMGrader (GigaChat 0/1/2) → Score `faithfulness_llm`.

Честное правило: без эталона не судим. Судятся трейсы, у которых в
metadata лежит `expected` (пишет run_regression L4) либо эталон передан
флагом --expected. Прод-трейсы без эталона пропускаются.
"""
from __future__ import annotations

import argparse
import base64
import os

import httpx

import backend.config  # noqa: F401 — грузит .env (ключи Langfuse)
from backend.observability import langfuse_client as _lf
from backend.scripts.benchmark.graders import LLMGrader
from backend.utils.logger import setup_logger

logger = setup_logger("lf_judge")

SCORE_NAME = "faithfulness_llm"


def _api():
    host = os.getenv("LANGFUSE_HOST", "http://localhost:3000").rstrip("/")
    auth = base64.b64encode(
        f"{os.getenv('LANGFUSE_PUBLIC_KEY', '')}"
        f":{os.getenv('LANGFUSE_SECRET_KEY', '')}".encode()
    ).decode()
    return host, {"Authorization": f"Basic {auth}"}


def get_trace(trace_id: str) -> dict:
    host, headers = _api()
    r = httpx.get(f"{host}/api/public/traces/{trace_id}",
                  headers=headers, timeout=30)
    r.raise_for_status()
    return r.json()


def list_traces(limit: int = 20) -> list[dict]:
    host, headers = _api()
    r = httpx.get(f"{host}/api/public/traces",
                  params={"limit": limit}, headers=headers, timeout=30)
    r.raise_for_status()
    return r.json().get("data", [])


def trace_scores(trace_id: str) -> list[dict]:
    host, headers = _api()
    r = httpx.get(f"{host}/api/public/scores", params={"traceId": trace_id},
                  headers=headers, timeout=30)
    r.raise_for_status()
    return r.json().get("data", [])


def judge_trace(trace: dict, expected: str | None,
                key_facts: list[str] | None = None) -> dict | None:
    tid = trace["id"]
    meta = trace.get("metadata") or {}
    expected = expected or meta.get("expected")
    if not expected:
        logger.info("trace %s: эталона нет — пропуск", tid[:8])
        return None
    if any(s.get("name") == SCORE_NAME for s in trace.get("scores", [])):
        logger.info("trace %s: уже осуждён — пропуск", tid[:8])
        return None
    question = trace.get("input") or ""
    answer = trace.get("output") or ""
    if isinstance(question, dict):
        question = question.get("question", str(question))
    if isinstance(answer, dict):
        answer = str(answer)
    if not question or not answer:
        logger.info("trace %s: пустой input/output — пропуск", tid[:8])
        return None
    case = {"question": question, "expected": expected,
            "key_facts": key_facts or meta.get("key_facts", [])}
    res = LLMGrader().grade(case, answer)
    value = res.get("score")
    try:
        value = float(value)
    except (TypeError, ValueError):
        logger.warning("trace %s: судья не вернул число: %r", tid[:8], res)
        return None
    _lf.score(tid, SCORE_NAME, value, data_type="NUMERIC",
              comment=str(res.get("comment", ""))[:500])
    _lf.flush()
    logger.info("trace %s: %s=%s", tid[:8], SCORE_NAME, value)
    return {"trace_id": tid, "score": value}


def main() -> int:
    ap = argparse.ArgumentParser(description="Судья трейсов Langfuse")
    ap.add_argument("--trace-id")
    ap.add_argument("--sample", type=int, default=0)
    ap.add_argument("--expected", default=None)
    ap.add_argument("--kind", default=None,
                    help="только трейсы с metadata.kind=...")
    args = ap.parse_args()

    if args.trace_id:
        t = get_trace(args.trace_id)
        r = judge_trace(t, args.expected)
        print("scored" if r else "skipped", r or args.trace_id[:8])
        return 0

    n_scored, n_skipped = 0, 0
    for t in list_traces(limit=max(args.sample, 1)):
        if args.kind and (t.get("metadata") or {}).get("kind") != args.kind:
            continue
        try:
            if judge_trace(t, args.expected):
                n_scored += 1
            else:
                n_skipped += 1
        except Exception as e:
            logger.warning("trace %s: %s", t["id"][:8], e)
            n_skipped += 1
        if n_scored + n_skipped >= args.sample and args.sample:
            break
    print(f"scored={n_scored} skipped={n_skipped}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
