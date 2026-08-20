#!/usr/bin/env python3
"""Run pipeline to build Neo4j graph from existing Qdrant chunks."""

import sys, time, json
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent.parent))

from backend.rag.pipeline import process_all_documents

start = time.time()
result = process_all_documents()
elapsed = time.time() - start

summary = {
    "elapsed_seconds": round(elapsed),
    "total_processed": result["total_processed"],
    "total_errors": result["total_errors"],
    "processed": result["processed"][:10],
    "errors": result["errors"][:5],
}

report_path = Path(__file__).resolve().parent.parent.parent / "pipeline_result.json"
with open(report_path, "w") as f:
    json.dump(summary, f, ensure_ascii=False, indent=2)

print(json.dumps(summary, ensure_ascii=False, indent=2))
