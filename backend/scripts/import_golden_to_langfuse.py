"""Импорт yaml-набора → Langfuse Dataset.

По умолчанию: golden_set.yaml → `regression-golden-set`.
Пул вопросов: --source backend/rag/question_pool.yaml --dataset question-pool.

Идемпотентен по case id: существующие items не дублируются
(проверка по metadata.case_id).
"""
from __future__ import annotations

import argparse

import yaml

from backend.observability import langfuse_client as _lf
from backend.utils.logger import setup_logger

logger = setup_logger("lf_import_golden")


def main() -> int:
    ap = argparse.ArgumentParser(description="Импорт набора в Dataset")
    ap.add_argument("--source", default="backend/rag/golden_set.yaml")
    ap.add_argument("--dataset", default="regression-golden-set")
    args = ap.parse_args()

    lf = _lf.get_langfuse()
    assert lf is not None, "Langfuse недоступен (LANGFUSE_ENABLED=1?)"
    with open(args.source, encoding="utf-8") as f:
        cases = yaml.safe_load(f)
    try:
        ds = lf.get_dataset(args.dataset)
        existing = {i.metadata.get("case_id") for i in ds.items}
    except Exception:
        lf.create_dataset(
            name=args.dataset,
            description=f"Импорт {args.source}",
        )
        existing = set()
    added = 0
    for c in cases:
        if c["id"] in existing:
            continue
        lf.create_dataset_item(
            dataset_name=args.dataset,
            input={"question": c["question"]},
            expected_output={
                "contains": c.get("contains", []),
                "excludes": c.get("excludes", []),
                "intent": c.get("expect_intent"),
                "expect_silence": bool(c.get("expect_silence", False)),
            },
            metadata={"case_id": c["id"],
                      "intent": c.get("expect_intent"),
                      "notes": c.get("notes", "")},
        )
        added += 1
    lf.flush()
    print(f"dataset={args.dataset} added={added} total={len(cases)}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
