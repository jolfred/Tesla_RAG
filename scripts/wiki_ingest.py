#!/usr/bin/env python3
"""LLM Wiki source ledger, resumable compiler, and concise status CLI."""
import argparse
import json
import re
import sys
from collections import Counter
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from backend.wiki.ingest import (  # noqa: E402
    apply, apply_proposals, connect, export_posts, import_results, inventory,
    ledger_view, retrieval_pack, stage_proposals, verify_posts,
)
from backend.wiki.ingest_runner import compile_wiki, read_codex_limits  # noqa: E402
from backend.wiki.legacy_progress import reconcile_legacy  # noqa: E402

DEFAULT_EXTRACT = "opencode/longcat-2.5-preview-free"
DEFAULT_MERGE = DEFAULT_EXTRACT
FREE_FALLBACKS = ["opencode/mimo-v2.6-flash-free", "opencode/nemotron-3-ultra-free"]
FREE_MODEL_CHOICES = (DEFAULT_EXTRACT, *FREE_FALLBACKS)


def status(db: Path, run_dir: Path, with_limits: bool = False) -> dict:
    con = connect(db)
    out = {}
    for table, field in (("posts", "state"), ("facts", "state"), ("proposals", "state")):
        out[table] = {row[0]: row[1] for row in con.execute(f"SELECT {field},count(*) FROM {table} GROUP BY {field}")}
    counts = out["posts"]
    out["progress"] = {
        "total_source_versions": sum(counts.values()),
        "previously_processed": counts.get("legacy_processed", 0),
        "current_run_accounted": sum(n for state, n in counts.items() if state not in {"queued", "legacy_processed"}),
        "still_queued": counts.get("queued", 0),
        "note": "Previous processing is recovered from receipts; it does not certify complete extraction or editorial verification.",
    }
    out["unfinished_review"] = {
        "posts": con.execute("SELECT count(*) FROM posts WHERE state='review'").fetchone()[0],
        "facts": con.execute("SELECT count(*) FROM facts WHERE state='review'").fetchone()[0],
        "proposals": con.execute("SELECT count(*) FROM proposals WHERE state='review'").fetchone()[0],
    }
    out["queued_reasons"] = [{"reason": r[0], "count": r[1]} for r in con.execute(
        "SELECT coalesce(reason,'') reason,count(*) FROM posts WHERE state='queued' AND reason IS NOT NULL GROUP BY reason ORDER BY count(*) DESC LIMIT 5")]
    con.close()
    events = run_dir / "provider-events.jsonl"
    out["provider_status"] = {"selected_provider":"not started"}
    if events.exists():
        try: out["provider_status"] = json.loads(events.read_text(encoding="utf-8").splitlines()[-1])
        except (ValueError, IndexError): pass
    if with_limits:
        try:
            limits = read_codex_limits()
            limits["primary_remaining_percent"] = 100 - limits["primary_used_percent"]
            limits["secondary_remaining_percent"] = 100 - limits["secondary_used_percent"]
            out["codex_limits"] = limits
        except Exception:
            out["codex_limits"] = {"available": False}
    return out


def parse_verify_pair(value: str) -> tuple[str, str]:
    if ":" not in value:
        raise ValueError("expected SOURCE_ID:SOURCE_SHA256")
    source_id, source_hash = value.rsplit(":", 1)
    if not source_id or not re.fullmatch(r"[0-9a-f]{64}", source_hash):
        raise ValueError("expected SOURCE_ID followed by a 64-character lowercase SHA-256")
    return source_id, source_hash


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--db", type=Path, default=ROOT / "storage/wiki/_ingest/ledger.sqlite")
    sub = parser.add_subparsers(dest="cmd", required=True)

    a = sub.add_parser("inventory"); a.add_argument("posts", type=Path)
    a.add_argument("--exclude-domain", action="append", default=["kgeu_official", "spoyunost"])
    a = sub.add_parser("export"); a.add_argument("--limit", type=int, default=50); a.add_argument("--char-budget", type=int, default=40000)
    a.add_argument("--state", default="queued"); a.add_argument("--out", type=Path, required=True)
    a = sub.add_parser("import"); a.add_argument("handoff", type=Path)
    a = sub.add_parser("apply"); a.add_argument("--wiki", type=Path, default=ROOT / "storage/wiki")
    a = sub.add_parser("merge-pack"); a.add_argument("--wiki", type=Path, default=ROOT / "storage/wiki")
    a.add_argument("--query", required=True); a.add_argument("--limit", type=int, default=5); a.add_argument("--out", type=Path, required=True)
    a = sub.add_parser("stage-merge"); a.add_argument("handoff", type=Path); a.add_argument("--wiki", type=Path, default=ROOT / "storage/wiki")
    a = sub.add_parser("apply-merge"); a.add_argument("--wiki", type=Path, default=ROOT / "storage/wiki")
    a = sub.add_parser("review"); a.add_argument("--state")
    a = sub.add_parser("verify"); a.add_argument("--source-id", "--post-id", dest="post_id", action="append", required=True,
        help="SOURCE_ID:SOURCE_SHA256; repeatable (typed IDs may contain colons)")
    a = sub.add_parser("status"); a.add_argument("--run-dir", type=Path, default=ROOT / "storage/wiki/_ingest/runs/default")
    a.add_argument("--limits", action="store_true", help="read actual Codex rate limits; never estimates from tokens")

    a = sub.add_parser("reconcile-legacy", help="recover previous completed batches without provider calls")
    a.add_argument("--wiki", type=Path, default=ROOT / "storage/wiki")
    a.add_argument("--apply", action="store_true", help="exclude documented matching old inputs from the new queue")
    a.add_argument("--report", type=Path, required=True)

    a = sub.add_parser("compile")
    a.add_argument("--wiki", type=Path, default=ROOT / "storage/wiki")
    a.add_argument("--run-dir", type=Path, default=ROOT / "storage/wiki/_ingest/runs/default")
    a.add_argument("--extract-model", choices=FREE_MODEL_CHOICES, default=DEFAULT_EXTRACT)
    a.add_argument("--extract-free-fallback", action="append", choices=FREE_MODEL_CHOICES, default=FREE_FALLBACKS)
    a.add_argument("--merge-model", choices=FREE_MODEL_CHOICES, default=DEFAULT_MERGE)
    a.add_argument("--merge-free-fallback", action="append", choices=FREE_MODEL_CHOICES, default=FREE_FALLBACKS)
    a.add_argument("--agent", choices=["plan"], default="plan", help="built-in OpenCode agent in an isolated filesystem with staged inputs")
    a.add_argument("--no-codex-fallback", action="store_true", help="do not use Luna after all free OpenCode models fail")
    a.add_argument("--max-posts", type=int, default=50); a.add_argument("--all", action="store_true", help="process every queued post")
    a.add_argument("--batch-size", type=int, default=50); a.add_argument("--char-budget", type=int, default=40000)
    a.add_argument("--apply", action="store_true", help="apply pages that pass all merge validation")
    a.add_argument("--execute", action="store_true", help="explicitly permit provider CLI calls")

    args = parser.parse_args()
    if args.cmd == "inventory": result = inventory(args.db, args.posts, args.exclude_domain)
    elif args.cmd == "export":
        if not 1 <= args.limit <= 50: parser.error("post limit must be 1..50")
        pack = {"posts": export_posts(args.db, args.limit, args.state, args.char_budget)}
        args.out.parent.mkdir(parents=True, exist_ok=True); args.out.write_text(json.dumps(pack, ensure_ascii=False, indent=2), encoding="utf-8")
        result = {"exported": len(pack["posts"])}
    elif args.cmd == "import": result = import_results(args.db, args.handoff)
    elif args.cmd == "apply": result = apply(args.db, args.wiki)
    elif args.cmd == "merge-pack":
        pack = retrieval_pack(args.db, args.wiki, args.query, args.limit)
        args.out.parent.mkdir(parents=True, exist_ok=True); args.out.write_text(json.dumps(pack, ensure_ascii=False, indent=2), encoding="utf-8")
        result = {"pages": len(pack["pages"]), "facts": len(pack["facts"])}
    elif args.cmd == "stage-merge": result = stage_proposals(args.db, args.wiki, args.handoff)
    elif args.cmd == "apply-merge": result = apply_proposals(args.db, args.wiki)
    elif args.cmd == "review": result = ledger_view(args.db, args.state)
    elif args.cmd == "verify":
        pairs = []
        for value in args.post_id:
            try: pairs.append(parse_verify_pair(value))
            except ValueError as exc: parser.error(str(exc))
        result = {"verified": verify_posts(args.db, pairs)}
    elif args.cmd == "status": result = status(args.db, args.run_dir, args.limits)
    elif args.cmd == "reconcile-legacy":
        result = reconcile_legacy(args.db, args.wiki, args.apply)
        args.report.parent.mkdir(parents=True, exist_ok=True)
        args.report.write_text(json.dumps(result, ensure_ascii=False, indent=2), encoding="utf-8")
        result = {key: value for key, value in result.items() if key != "unresolved"} | {"unresolved_records": len(result["unresolved"])}
    else:
        if not args.execute: parser.error("compile makes provider calls; pass --execute explicitly")
        if args.all and not args.apply: parser.error("--all requires --apply so each post batch is merged before continuing")
        result = compile_wiki(args.db, args.wiki, args.run_dir,
            ROOT / "schema/prompts/wiki_extract_en.md", ROOT / "schema/prompts/wiki_merge_en.md",
            (2**31 - 1 if args.all else args.max_posts), args.batch_size, args.char_budget,
            args.extract_model, tuple(args.extract_free_fallback), args.merge_model,
            tuple(args.merge_free_fallback), args.apply, not args.no_codex_fallback, args.agent)
    print(json.dumps(result, ensure_ascii=False, indent=2))


if __name__ == "__main__": main()
