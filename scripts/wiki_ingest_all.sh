#!/bin/bash
# Безопасная инвентаризация всех разрешённых корпусов; не вызывает LLM и не меняет статьи.
set -euo pipefail
ROOT="$(cd "$(dirname "$0")/.." && pwd)"
for f in "$ROOT"/storage/posts/posts_*.jsonl; do
    base="$(basename "$f")"
    case "$base" in
        posts_kgeu_official.jsonl|posts_spoyunost.jsonl) echo "SKIP $base (правило 10)"; continue;;
    esac
    echo "$(date -u +%FT%TZ) INVENTORY $base"
    "$ROOT/.venv/bin/python" "$ROOT/scripts/wiki_ingest.py" inventory "$f"
done
echo "$(date -u +%FT%TZ) ALL DONE"
