"""Прогон бенчмарка RAG-ассистента Штаба Тесла.

Справка по режимам:
- searcher: in-process GraphRAGSearcher (нужны Neo4j, Qdrant на 6333 и ключ GigaChat)
- api: HTTP-запросы к /api/v1/chat (нужен запущенный uvicorn)

Примеры:
    .venv/bin/python -m backend.scripts.benchmark.runner --mode searcher
    .venv/bin/python -m backend.scripts.benchmark.runner --mode api --api-url http://localhost:8000
    .venv/bin/python -m backend.scripts.benchmark.runner --ids q1,q2 --no-grade
"""

import argparse
import json
import time
from datetime import datetime, timezone
from pathlib import Path

import httpx

from backend.config import USER_API_KEY
from backend.rag.searcher import GraphRAGSearcher
from backend.utils.logger import setup_logger

from backend.scripts.benchmark.graders import LLMGrader, heuristic_score
from backend.scripts.benchmark.report import (
    DEFAULT_OUTPUT_DIR,
    LATEST_REPORT,
    load_done,
    print_report,
    summarize,
    write_report,
)

logger = setup_logger("benchmark")

DEFAULT_DATA = Path(__file__).resolve().parent / "data" / "questions.json"
_REQUEST_TIMEOUT = 300.0


def load_cases(path: Path, ids: list[str]) -> list[dict]:
    with open(path, encoding="utf-8") as f:
        cases = json.load(f)
    if ids:
        cases = [c for c in cases if c["id"] in ids]
    return cases


def ask_searcher(searcher: GraphRAGSearcher, question: str) -> dict:
    return searcher.search(question)


def ask_api(url: str, api_key: str, question: str) -> dict:
    with httpx.Client(base_url=url, headers={"X-API-Key": api_key}, timeout=_REQUEST_TIMEOUT) as client:
        resp = client.post("/api/v1/chat", json={"question": question})
        resp.raise_for_status()
        return resp.json()


def grade_answer(case: dict, answer: str, grader: LLMGrader | None) -> tuple:
    """Возвращает (score, reason, method). score может быть None, если оценить нельзя."""
    if grader is not None:
        try:
            result = grader.grade(case, answer)
            return result["score"], result.get("reason", ""), "llm"
        except Exception as e:
            logger.warning("LLM grading failed for %s, using heuristic: %s", case.get("id"), e)
    score = heuristic_score(case, answer)
    if score is None:
        return None, "Невозможно оценить: нет ключевых фактов", "heuristic"
    return score, f"Эвристика: вхождение ключевых фактов", "heuristic"


def run_case(case: dict, ask_fn, grader: LLMGrader | None, no_grade: bool) -> dict:
    result = {
        "id": case["id"],
        "category": case.get("category", ""),
        "type": case.get("type", "fact"),
        "question": case["question"],
        "expected": case["expected"],
        "error": None,
    }
    t0 = time.monotonic()
    try:
        raw = ask_fn(case["question"])
        result["answer"] = raw.get("answer", "")
        result["mode"] = raw.get("mode", "")
        result["sources"] = [
            {"title": s.get("title", ""), "url": s.get("url", "")}
            for s in raw.get("sources", [])
        ]
        result["facts_count"] = raw.get("facts_count", 0)
        result["posts_used"] = raw.get("posts_used", 0)
    except Exception as e:
        logger.error("Query failed for %s: %s", case["id"], e)
        result["error"] = f"{type(e).__name__}: {e}"
        result["answer"] = ""
        result["mode"] = ""
        result["sources"] = []
    result["elapsed"] = round(time.monotonic() - t0, 2)

    if not no_grade and result.get("answer"):
        score, reason, method = grade_answer(case, result["answer"], grader)
        result["score"] = score
        result["grade_reason"] = reason
        result["grade_method"] = method
    else:
        result["score"] = None
        result["grade_reason"] = "" if no_grade else "Нет ответа (ошибка запроса)"
        result["grade_method"] = ""
    return result


def parse_args(argv=None) -> argparse.Namespace:
    p = argparse.ArgumentParser(
        description="Бенчмарк RAG-ассистента Штаба Тесла (оценка 0/1/2)",
    )
    p.add_argument("--mode", choices=["searcher", "api"], default="searcher",
                   help="searcher = in-process GraphRAGSearcher; api = HTTP /api/v1/chat")
    p.add_argument("--api-url", default="http://localhost:8000",
                   help="базовый URL API в режиме api")
    p.add_argument("--api-key", default=USER_API_KEY,
                   help="X-API-Key в режиме api (по умолчанию USER_API_KEY из .env)")
    p.add_argument("--data", type=Path, default=DEFAULT_DATA,
                   help="путь к JSON с тестовыми вопросами")
    p.add_argument("--output", type=Path, default=None,
                   help="путь к JSON-отчёту (по умолчанию storage/benchmark/report_<ts>.json)")
    p.add_argument("--ids", default="",
                   help="подмножество тестов через запятую, например q1,q2")
    p.add_argument("--grader-model", default="",
                   help="модель GigaChat для оценки (по умолчанию GIGACHAT_MODEL из .env)")
    p.add_argument("--no-grade", action="store_true",
                   help="только собрать ответы, без оценки")
    p.add_argument("--resume", action="store_true",
                   help="продолжить прогон: пропустить вопросы, уже имеющие ответ в отчёте")
    return p.parse_args(argv)


def main(argv=None) -> int:
    args = parse_args(argv)
    cases = load_cases(args.data, [x.strip() for x in args.ids.split(",") if x.strip()])
    if not cases:
        print(f"Нет тестов в {args.data} (ids={args.ids!r})")
        return 1

    grader = None
    if not args.no_grade:
        grader = LLMGrader(model=args.grader_model or None)

    out_path = args.output
    if not out_path:
        out_path = DEFAULT_OUTPUT_DIR / f"report_{datetime.now(timezone.utc).strftime('%Y%m%d_%H%M%S')}.json"

    results = []
    if args.resume:
        src = args.output if args.output and args.output.suffix else LATEST_REPORT
        results.extend(load_done(src))
        if results:
            print(f"Resume: загружено {len(results)} отвеченных вопросов из {src}")

    done_ids = {r["id"] for r in results}
    remaining = [c for c in cases if c["id"] not in done_ids]
    if not remaining:
        print("Все выбранные вопросы уже отвечены — обновляю итоговый отчёт.")
    else:
        searcher = None
        try:
            if args.mode == "searcher":
                searcher = GraphRAGSearcher()
                ask_fn = lambda q: ask_searcher(searcher, q)
            else:
                ask_fn = lambda q: ask_api(args.api_url, args.api_key, q)

            for case in remaining:
                logger.info("Benchmark %s: %s", case["id"], case["question"][:80])
                results.append(run_case(case, ask_fn, grader, args.no_grade))
                write_report(LATEST_REPORT, args.mode, results)
                logger.info("Progress: %d/%d saved to %s", len(results), len(cases), LATEST_REPORT)
        finally:
            if searcher is not None:
                try:
                    searcher.close()
                except Exception:
                    pass

    summary = summarize(results)
    print_report(summary, results)

    out_path.parent.mkdir(parents=True, exist_ok=True)
    write_report(out_path, args.mode, results)
    write_report(LATEST_REPORT, args.mode, results)
    print(f"\nОтчёт сохранён: {out_path}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
