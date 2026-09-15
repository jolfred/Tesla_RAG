"""Выборочный LLM-судья (Фаза 5 плана наблюдаемости): аудит, не гейт.

Судья — тот же GigaChat через готовый LLMGrader (решение пользователя),
поэтому трактуем оценку как faithfulness-аудит, а не независимую истину:
relevance не измеряем (NULL). Эталона нет — key_facts пустые, судья ищет
выдумки и несоответствие вопросу. Запуск:
    .venv/bin/python -m backend.observability.judge --sample 5
    .venv/bin/python -m backend.observability.judge --trace-id <id>
Пропускает трейсы, у которых уже есть judgement.
"""

from __future__ import annotations

import argparse

from backend.observability.store import TraceStore
from backend.scripts.benchmark.graders import LLMGrader
from backend.utils.logger import setup_logger

logger = setup_logger("judge")

NOREF_EXPECTED = (
    "Эталонного ответа нет. Оцени достоверность: нет ли выдуманных имён, "
    "дат, должностей и фактов; отвечает ли ответ на вопрос."
)


def judge_trace(store: TraceStore, trace_id: str,
                grader: LLMGrader | None = None) -> dict | None:
    """Осудить один трейс, записать в judgements. Повтор — пропуск."""
    trace = store.fetch_trace(trace_id)
    if not trace or not trace.get("final_answer"):
        return None
    try:
        cur = store._conn.execute(
            "SELECT COUNT(*) FROM judgements WHERE trace_id = ?", (trace_id,))
        if cur.fetchone()[0]:
            return {"trace_id": trace_id, "skipped": True}
    except Exception:
        pass
    grader = grader or LLMGrader()
    try:
        res = grader.grade(
            {"id": trace_id, "question": trace.get("question") or "",
             "expected": NOREF_EXPECTED, "key_facts": []},
            trace.get("final_answer") or "",
        )
    except Exception as e:
        logger.warning("judge failed for %s: %s", trace_id, e)
        return None
    score = res.get("score")
    store.add_judgement(
        trace_id, "gigachat-grader", faithfulness=score, relevance=None,
        notes=res.get("reason", ""))
    return {"trace_id": trace_id, "faithfulness": score,
            "notes": res.get("reason", "")}


def sample_traces(store: TraceStore, limit: int = 5,
                  kind: str = "narrative") -> list[str]:
    """Последние prod-трейсы указанного kind без judgement."""
    try:
        cur = store._conn.execute(
            "SELECT trace_id FROM traces WHERE source = 'prod' "
            "AND kind = ? AND trace_id NOT IN "
            "(SELECT trace_id FROM judgements) "
            "ORDER BY rowid DESC LIMIT ?",
            (kind, limit),
        )
        return [r[0] for r in cur.fetchall()]
    except Exception as e:
        logger.warning("sample failed: %s", e)
        return []


def main() -> int:
    ap = argparse.ArgumentParser(description="Выборочный LLM-судья")
    ap.add_argument("--trace-id", default=None)
    ap.add_argument("--sample", type=int, default=5)
    ap.add_argument("--kind", default="narrative")
    ap.add_argument("--db", default=None)
    args = ap.parse_args()

    store = TraceStore(args.db)
    try:
        ids = [args.trace_id] if args.trace_id else sample_traces(
            store, args.sample, args.kind)
        if not ids:
            print("Нет трейсов для судейства")
            return 0
        grader = LLMGrader()
        done = 0
        for tid in ids:
            res = judge_trace(store, tid, grader)
            if not res:
                print(f"[{tid}] ошибка судьи")
            elif res.get("skipped"):
                print(f"[{tid}] уже осуждён, пропуск")
            else:
                done += 1
                print(f"[{tid}] faithfulness={res['faithfulness']}: "
                      f"{res['notes'][:150]}")
        print(f"Осуждено: {done}/{len(ids)}")
        return 0
    finally:
        store.close()


if __name__ == "__main__":
    main()
