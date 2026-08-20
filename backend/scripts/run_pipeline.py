#!/usr/bin/env python3
"""Run full pipeline in background, writing progress periodically."""

import sys, time, json, os
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent.parent))

log_path = Path(os.environ.get("LOG_FILE", "/tmp/pipeline_progress.log"))

def log(msg):
    with open(log_path, "a") as f:
        f.write(f"{time.strftime('%H:%M:%S')} {msg}\n")

log("Starting pipeline...")

from backend.rag.pipeline import process_all_documents

start = time.time()
result = process_all_documents()
elapsed = time.time() - start

summary = {
    "elapsed_seconds": round(elapsed),
    "total_processed": result["total_processed"],
    "total_errors": result["total_errors"],
}

log(f"Finished: {json.dumps(summary)}")
print(json.dumps(summary))
