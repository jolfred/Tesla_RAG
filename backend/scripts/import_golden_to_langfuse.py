"""Разовый импорт golden_set.yaml → Langfuse Dataset `regression-golden-set`.

Идемпотентен по case id: существующие items не дублируются
(проверка по metadata.case_id).
"""
from __future__ import annotations

import yaml

from backend.observability import langfuse_client as _lf
from backend.utils.logger import setup_logger

logger = setup_logger("lf_import_golden")

DATASET = "regression-golden-set"


def main() -> int:
    lf = _lf.get_langfuse()
    assert lf is not None, "Langfuse недоступен (LANGFUSE_ENABLED=1?)"
    with open("backend/rag/golden_set.yaml", encoding="utf-8") as f:
        cases = yaml.safe_load(f)
    try:
        ds = lf.get_dataset(DATASET)
        existing = {i.metadata.get("case_id") for i in ds.items}
    except Exception:
        lf.create_dataset(
            name=DATASET,
            description="Регресс RAG-ответов (миграция golden_set.yaml)",
        )
        existing = set()
    added = 0
    for c in cases:
        if c["id"] in existing:
            continue
        lf.create_dataset_item(
            dataset_name=DATASET,
            input={"question": c["question"]},
            expected_output={
                "contains": c.get("contains", []),
                "excludes": c.get("excludes", []),
                "intent": c.get("expect_intent"),
            },
            metadata={"case_id": c["id"],
                      "intent": c.get("expect_intent")},
        )
        added += 1
    lf.flush()
    print(f"dataset={DATASET} added={added} total={len(cases)}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
