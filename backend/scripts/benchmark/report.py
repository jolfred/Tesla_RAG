"""Формирование, печать и сохранение отчётов бенчмарка."""

import json
from datetime import datetime, timezone
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent.parent.parent
DEFAULT_OUTPUT_DIR = REPO_ROOT / "storage" / "benchmark"
LATEST_REPORT = DEFAULT_OUTPUT_DIR / "report_latest.json"


def summarize(results: list[dict]) -> dict:
    scored = [r for r in results if r.get("score") is not None]
    total = sum(r["score"] for r in scored)
    dist = {0: 0, 1: 0, 2: 0}
    for r in scored:
        dist[r["score"]] += 1
    return {
        "total_questions": len(results),
        "scored": len(scored),
        "max_score": len(scored) * 2,
        "total_score": total,
        "average": round(total / len(scored), 2) if scored else 0.0,
        "pass_rate": round(dist[2] / len(scored) * 100, 1) if scored else 0.0,
        "distribution": dist,
    }


def print_report(summary: dict, results: list[dict]) -> None:
    print("\n" + "=" * 80)
    print("ОТЧЁТ БЕНЧМАРКА RAG-АССИСТЕНТА")
    print("=" * 80)
    print(
        f"Итог: {summary['total_score']}/{summary['max_score']}  "
        f"(средний балл {summary['average']:.2f}/2, "
        f"доля «отлично» {summary['pass_rate']}%)"
    )
    print(f"Распределение: 2 — {summary['distribution'][2]}, "
          f"1 — {summary['distribution'][1]}, 0 — {summary['distribution'][0]}")
    print("\n" + "-" * 80)
    header = f"{'ID':<5}{'Мод':<6}{'Балл':<6}{'Сек':<6}Вопрос"
    print(header)
    print("-" * 80)
    for r in results:
        score = "—" if r.get("score") is None else str(r.get("score"))
        mode = r.get("mode") or ("" if r.get("error") else "—")
        print(f"{r['id']:<5}{mode:<6}{score:<6}{r.get('elapsed', 0):<6}{str(r.get('question', ''))[:70]}")
        if r.get("error"):
            print(f"      ! ошибка: {r['error'][:100]}")
        elif r.get("answer"):
            snippet = r["answer"].replace("\n", " ")[:120]
            print(f"      ответ: {snippet}...")
    print("-" * 80)
    print("Детали оценок — в JSON-отчёте.")


def write_report(path: Path, mode: str, results: list[dict]) -> None:
    report = {
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "mode": mode,
        "summary": summarize(results),
        "results": results,
    }
    path.parent.mkdir(parents=True, exist_ok=True)
    with open(path, "w", encoding="utf-8") as f:
        json.dump(report, f, ensure_ascii=False, indent=2)


def load_done(path: Path) -> list[dict]:
    """Возвращает результаты вопросов с ответом из существующего отчёта (для --resume)."""
    if not path.exists():
        return []
    try:
        prev = json.loads(path.read_text(encoding="utf-8"))
    except (json.JSONDecodeError, OSError):
        return []
    return [r for r in prev.get("results", []) if r.get("answer")]


def load_done_ids(path: Path) -> set[str]:
    return {r["id"] for r in load_done(path)}
