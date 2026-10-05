"""Recover documented old compilation without certifying its factual completeness."""
from __future__ import annotations

import hashlib
import json
import re
from pathlib import Path

from backend.wiki.ingest import connect
from backend.wiki.ingest_runner import _exclusive_compile

BLOCK = re.compile(
    r'^\[\d+\] id=(wall-?\d+_\d+) published=([^\n]+)\n"""\n(.*?)\n"""(?=\n|$)',
    re.M | re.S,
)


@_exclusive_compile
def reconcile_legacy(db: Path, wiki: Path, apply: bool = False) -> dict:
    """Require a completed receipt, a Wiki journal entry, matching text and date.

    Only queued rows change. Citation presence alone is not a completion receipt.
    Exact text after whitespace normalization is required; changed or shortened
    inputs remain queued. No article or extracted fact is modified.
    """
    wiki = wiki.resolve()
    done_path = wiki / "_batches/done.txt"
    log_path = wiki / "log.md"
    for path in (done_path, log_path):
        if not path.resolve().is_relative_to(wiki):
            raise ValueError("legacy evidence must stay inside the Wiki root")
    done = {s.strip() for s in done_path.read_text(encoding="utf-8").splitlines()}
    journal = log_path.read_text(encoding="utf-8")
    entries = {}
    for line in journal.splitlines():
        for name in re.findall(r'INGEST\s+`?_batches/chunks/([\w.-]+)', line):
            name = name if name.endswith(".txt") else name + ".txt"
            entries.setdefault(name, []).append(line)
    supported = done & entries.keys()
    con = connect(db)
    try:
        rows = {}
        for row in con.execute("SELECT * FROM posts"):
            rows.setdefault(row["post_id"], []).append(row)
        matched = set()
        evidence = []
        unresolved = []
        for name in sorted(supported):
            path = wiki / "_batches/chunks" / name
            if not path.is_file() or not path.resolve().is_relative_to(wiki):
                unresolved.append({"batch": name, "reason": "missing or outside-root chunk"})
                continue
            text = path.read_text(encoding="utf-8")
            blocks = BLOCK.findall(text)
            headers = re.findall(r'^\[\d+\] id=', text, re.M)
            if not blocks or len(blocks) != len(headers):
                unresolved.append({"batch": name, "reason": "incomplete chunk format"})
                continue
            for pid, date, body in blocks:
                found = False
                for row in rows.get(pid, []):
                    source = json.loads(row["source_json"])
                    clean = source.get("text_clean")
                    if (not isinstance(clean, str) or " ".join(body.split()) != " ".join(clean.split())
                            or not re.fullmatch(r"\d{4}-\d{2}-\d{2}", date)
                            or date != str(source.get("published_at", ""))[:10]):
                        continue
                    found = True
                    matched.add((pid, row["source_hash"]))
                    evidence.append({
                        "post_id": pid, "source_hash": row["source_hash"], "batch": name,
                        "batch_sha256": hashlib.sha256(text.encode()).hexdigest(),
                        "journal_sha256": hashlib.sha256("\n".join(entries[name]).encode()).hexdigest(),
                        "compiled_text_sha256": hashlib.sha256(body.encode()).hexdigest(),
                    })
                if not found:
                    unresolved.append({"batch": name, "post_id": pid,
                                       "reason": "no matching current text and publication date"})
        candidates = [(pid, sha) for pid, sha in sorted(matched) if con.execute(
            "SELECT state FROM posts WHERE post_id=? AND source_hash=?", (pid, sha)
        ).fetchone()[0] == "queued" and not con.execute(
            "SELECT 1 FROM facts WHERE post_id=? AND source_hash=?", (pid, sha)
        ).fetchone()]
        if apply:
            with con:
                con.execute("""CREATE TABLE IF NOT EXISTS legacy_receipts(
                    post_id TEXT NOT NULL, source_hash TEXT NOT NULL, batch TEXT NOT NULL,
                    evidence_json TEXT NOT NULL,
                    PRIMARY KEY(post_id,source_hash,batch))""")
                for item in evidence:
                    con.execute("INSERT OR REPLACE INTO legacy_receipts VALUES(?,?,?,?)", (
                        item["post_id"], item["source_hash"], item["batch"], json.dumps(item)))
                con.executemany("""UPDATE posts SET state='legacy_processed',
                    reason='Documented previous compilation; factual completeness not reverified',
                    updated_at=CURRENT_TIMESTAMP
                    WHERE post_id=? AND source_hash=? AND state='queued'""", candidates)
        return {
            "applied": apply, "completed_batches_with_journal": len(supported),
            "matched_previous_sources": len(matched), "newly_reconciled": len(candidates) if apply else 0,
            "eligible_queued_sources": len(candidates),
            "receipts_without_journal": sorted(done - entries.keys()),
            "unresolved": unresolved,
        }
    finally:
        con.close()
