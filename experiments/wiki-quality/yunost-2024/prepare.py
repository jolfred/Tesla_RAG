"""Freeze review materials. Standard library only; never imports an LLM client.

This is a data/provenance adapter, not an evaluation framework or a generator.
No command in this module can perform a model call or publish Wiki content.
"""
from __future__ import annotations

import argparse
from collections import Counter
import csv
from datetime import datetime, timedelta, timezone
import hashlib
import html
import json
from pathlib import Path
import random
import sqlite3
import subprocess
import sys

ROOT = Path(__file__).resolve().parents[3]
HERE = Path(__file__).resolve().parent
MSK = timezone(timedelta(hours=3), "Europe/Moscow (2024: UTC+03:00)")
MARKER = "--- CANONICAL RULES (VERBATIM; MUST FOLLOW) ---"
PROMPTS = {"wiki_extract": "wiki_extract_en.md", "wiki_merge": "wiki_merge_en.md"}


def sha(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def encoded(value: object) -> bytes:
    return (json.dumps(value, ensure_ascii=False, sort_keys=True, indent=2) + "\n").encode("utf-8")


def write_json(path: Path, value: object) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_bytes(encoded(value))


def git(root: Path, *args: str) -> str:
    return subprocess.check_output(["git", "-C", str(root), *args], text=True, encoding="utf-8").strip()


def parse_date(value: str) -> datetime:
    result = datetime.fromisoformat(value.replace("Z", "+00:00"))
    if result.tzinfo is None:
        raise ValueError("Publication timestamp must specify an offset")
    return result


def select_records(source: Path, config: dict) -> tuple[list[dict], list[dict], dict]:
    """Retain text verbatim; reject inconsistent identities and edit ambiguity."""
    selected, excluded, original = [], [], []
    identities: dict[str, str] = {}
    raw_lines = source.read_bytes().decode("utf-8-sig").splitlines()
    duplicate_lines = []
    for number, line in enumerate(raw_lines, 1):
        if not line.strip():
            continue
        record = json.loads(line)
        if record.get("group_domain") != config["source_domain"] or str(record.get("group_id")) != config["group_id"]:
            raise ValueError(f"Unexpected source identity at line {number}")
        date = parse_date(record["published_at"])
        wall_id = f"wall-{abs(int(record['group_id']))}_{record['post_id']}"
        if wall_id not in record["post_url"]:
            raise ValueError(f"URL/id mismatch at line {number}")
        if date.astimezone(MSK).year != config["publication_year"]:
            excluded.append({"source_line": number, "post_id": wall_id, "published_at": record["published_at"], "reason": "outside_Moscow_publication_year"})
            continue
        text = record.get("text_raw")
        if not isinstance(text, str):
            raise ValueError(f"Missing raw text at line {number}")
        digest = sha(text.encode("utf-8"))
        # Conflicting copies of one post must be adjudicated before freezing.
        if wall_id in identities:
            if identities[wall_id] != sha(encoded(record)):
                raise ValueError(f"Multiple different exported versions of {wall_id}; select explicitly")
            duplicate_lines.append(number)
            continue
        identities[wall_id] = sha(encoded(record))
        visible = {key: record[key] for key in ("group_id", "group_domain", "group_name", "post_url", "published_at", "text_raw")}
        visible.update(post_id=wall_id, source_hash=digest, source_kind="vk_post")
        # Native retrieval may use text_clean. Giving raw text here avoids
        # exposing an undocumented alternative cleaning pipeline to one arm.
        visible["text_clean"] = text
        month = date.astimezone(MSK).strftime("%Y-%m")
        selected.append({"record": visible, "batch": month, "source_line": number,
                         "published_at_moscow": date.astimezone(MSK).isoformat(),
                         "original_line_sha256": sha(line.encode("utf-8")),
                         "attachment_counts": {k: len(v) if isinstance(v, list) else int(bool(v)) for k, v in (record.get("attachments") or {}).items()}})
        original.append({"source_line": number, "raw_json_line": line})
    selected.sort(key=lambda item: (parse_date(item["record"]["published_at"]), int(item["record"]["post_id"].rsplit("_", 1)[1])))
    return selected, original, {"outside_year": excluded, "identical_duplicate_lines": duplicate_lines}


def allocation(months: list[str], repetitions: int, seed: int) -> list[dict]:
    pairs = [(r, month) for month in months for r in range(1, repetitions + 1)]
    orders = [("tesla", "openwiki")] * ((len(pairs) + 1) // 2) + [("openwiki", "tesla")] * (len(pairs) // 2)
    random.Random(seed).shuffle(orders)
    return [{"pair": index, "repetition": rep, "batch": month, "order": list(order)} for index, ((rep, month), order) in enumerate(zip(pairs, orders), 1)]


def prompt_snapshot(root: Path, canon_dir: Path | None = None) -> dict:
    """Reproduce the existing registry composition using a read-only DB handle."""
    canon = [((canon_dir or root / "schema") / name).read_text(encoding="utf-8") for name in ("rules.md", "rules_mapping.md")]
    skill = (root / ".opencode/skills/wiki-editorial/SKILL.md").read_text(encoding="utf-8")
    overrides, histories = {}, []
    db = root / "storage/admin.db"
    if db.exists():
        con = sqlite3.connect(db.resolve().as_uri() + "?mode=ro", uri=True)
        con.row_factory = sqlite3.Row
        try:
            con.execute("BEGIN")
            tables = {r[0] for r in con.execute("SELECT name FROM sqlite_master WHERE type='table'")}
            if "prompts" in tables:
                overrides = {r["key"]: dict(r) for r in con.execute("SELECT key,text,updated_at FROM prompts WHERE key IN ('wiki_extract','wiki_merge')")}
            if "prompt_history" in tables:
                histories = [dict(r) for r in con.execute("SELECT id,key,text,revision,reason,created_at FROM prompt_history WHERE key IN ('wiki_extract','wiki_merge') ORDER BY id")]
        finally:
            con.close()
    result = {"history": histories, "stages": {}, "composition_source": "backend/admin/prompts.py:compose"}
    for key, filename in PROMPTS.items():
        default = (root / "schema/prompts" / filename).read_text(encoding="utf-8")
        raw_override = overrides.get(key, {}).get("text")
        stage = (raw_override if raw_override else default).split(MARKER, 1)[0].rstrip()
        effective = stage.strip() + "\n\n" + MARKER + "\n\n" + "\n\n".join(canon) + "\n\n--- EDITORIAL SKILL ---\n\n" + skill
        result["stages"][key] = {"origin": "admin_override" if raw_override else "default_file", "source_file": "storage/admin.db" if raw_override else "schema/prompts/" + filename,
                                  "stage": stage, "effective": effective, "sha256": sha(effective.encode("utf-8"))}
    return result


def production_fingerprint(root: Path) -> dict:
    paths = [root / "storage/admin.db", root / "storage/wiki/_ingest/ledger.sqlite"]
    paths += [Path(str(p) + suffix) for p in list(paths) for suffix in ("-wal", "-shm")]
    wiki = root / "storage/wiki"
    if wiki.exists():
        paths += [p for p in wiki.rglob("*.md") if p.is_file() and not any(part.startswith("_") for part in p.relative_to(wiki).parts)]
    return {p.relative_to(root).as_posix(): sha(p.read_bytes()) for p in paths if p.is_file()}


def openwiki_task_payload(month: str, initial_month: str, canon_dir: Path) -> dict:
    """Visible task metadata; both arms use the selected research canon."""
    return {
        "user_request_verbatim": "Возьмем статьи СПО юность за 2024 год и сделаем два варианта вики на нашей системе и с langchain wiki.",
        "confirmed_user_scope": {"initial_wiki": "empty" if month == initial_month else "previous_month_checkpoint",
                                 "evidence": "selected_2024_exported_post_text_only", "outside_sources": False,
                                 "available_through_batch": month},
        "source_specific_connector_raw_data": {"connectorId": "custom-mcp", "path": month + "/posts.jsonl"},
        "canonical_domain_rules_verbatim": {name: (canon_dir / name).read_text(encoding="utf-8")
                                            for name in ("rules.md", "rules_mapping.md")}}


def review_html(rows: list[dict], config: dict) -> str:
    esc = html.escape
    chunks = ['<!doctype html><html lang="ru"><meta charset="utf-8"><title>Юность 2024 — материалы исследования</title>',
              '<style>body{max-width:1000px;margin:35px auto;padding:0 20px;font:17px/1.5 system-ui;color:#222}pre{white-space:pre-wrap;overflow-wrap:anywhere;background:#f6f4fa;padding:18px}summary{cursor:pointer;font-weight:600}article{border-bottom:1px solid #ddd;padding:12px 0}small{color:#555}a{color:#603da0}</style>',
              f'<h1>СПО «Юность»: {len(rows)} публикаций</h1><p>Даты отбора: 2024 год, Europe/Moscow. Только текст локального экспорта. Это материалы для проверки и разметки; эталон ещё не утверждён.</p>',
              '<p>Обратите внимание на даты событий и публикаций, должности и их периоды, анонсы, отчёты и возможные розыгрыши. Фото, документы по внешним ссылкам и современное описание группы во вход не входят.</p>']
    for month in sorted({r["batch"] for r in rows}):
        part = [r for r in rows if r["batch"] == month]
        chunks.append(f'<details><summary>{month} · {len(part)} публикаций</summary>')
        for row in part:
            r = row["record"]
            chunks.append(f'<article id="{esc(r["post_id"])}"><h3><a href="{esc(r["post_url"], quote=True)}">{esc(r["post_id"])}</a></h3><small>{esc(row["published_at_moscow"])} · строка экспорта {row["source_line"]} · SHA-256 текста {r["source_hash"]}</small><pre>{esc(r["text_raw"])}</pre></article>')
        chunks.append('</details>')
    return "\n".join(chunks) + "\n</html>\n"


def verify(folder: Path) -> dict:
    checksums = json.loads((folder / "checksums.json").read_text(encoding="utf-8"))
    actual = {p.relative_to(folder).as_posix() for p in folder.rglob("*") if p.is_file() and p != folder / "checksums.json"}
    if actual != set(checksums):
        raise ValueError("Snapshot file set changed; create a new version instead of editing a freeze")
    for name, digest in checksums.items():
        target = (folder / name).resolve()
        if not target.is_relative_to(folder.resolve()) or not target.is_file() or sha(target.read_bytes()) != digest:
            raise ValueError(f"Snapshot checksum mismatch: {name}")
    manifest = json.loads((folder / "manifest.json").read_text(encoding="utf-8"))
    return {"snapshot_id": manifest["snapshot_id"], "checked_files": len(checksums), "source_records": manifest["source_records"], "llm_calls": 0}


def freeze(root: Path, vendor: Path, config_path: Path) -> Path:
    config = json.loads(config_path.read_text(encoding="utf-8"))
    if (config["source_file"] != "storage/posts/posts_spoyunost2020.jsonl" or config["timezone"] != "Europe/Moscow"
            or config["publication_year"] != 2024 or config["utc_offset_hours_in_study_year"] != 3):
        raise ValueError("Unexpected corpus or timezone; update the protocol and review adapter first")
    if git(vendor, "rev-parse", "HEAD") != config["openwiki_commit"]:
        raise ValueError("OpenWiki checkout does not match protocol")
    if git(root, "rev-parse", config["tesla_commit"]) != config["tesla_commit"]:
        raise ValueError("Tesla baseline commit is not available")
    # An edited compiler cannot silently be advertised as the committed baseline.
    checked = ["backend/wiki", "backend/admin/prompts.py", "schema", "scripts/wiki_ingest.py", ".opencode/skills/wiki-editorial/SKILL.md"]
    if git(root, "diff", config["tesla_commit"], "--", *checked):
        raise ValueError("Compiler/prompt files differ from the pinned baseline; choose and record a new version")
    before = production_fingerprint(root)
    source = root / config["source_file"]
    rows, originals, exclusions = select_records(source, config)
    if not rows:
        raise ValueError("Empty selected corpus")
    canon_dir = HERE / "instruction-proposal" if config.get("instruction_profile") == "instruction-proposal_research_copy_only" else root / "schema"
    if canon_dir != root / "schema":
        proposed = json.loads((canon_dir / "manifest.json").read_text(encoding="utf-8"))
        for name in ("rules.md", "rules_mapping.md"):
            if sha((canon_dir / name).read_bytes()) != proposed[name]["proposed_sha256"]:
                raise ValueError("Research canon differs from the disclosed proposal")
    prompts = prompt_snapshot(root, canon_dir)
    helper_hashes = {p.name: sha(p.read_bytes()) for p in sorted(HERE.iterdir()) if p.is_file() and p.suffix in {".py", ".json", ".md", ".mjs", ".txt", ".patch"}}
    patch_name = config.get("openwiki_compatibility_patch")
    if patch_name:
        actual_patch = subprocess.check_output(["git", "-C", str(vendor), "diff", config["openwiki_commit"], "--"])
        if actual_patch.replace(b"\r\n", b"\n") != (HERE / patch_name).read_bytes().replace(b"\r\n", b"\n"):
            raise ValueError("OpenWiki modifications do not match the disclosed compatibility patch")
    identity = {"preparer_git_commit": git(root, "rev-parse", "HEAD"), "config_sha256": sha(config_path.read_bytes()), "source_file_sha256": sha(source.read_bytes()), "prompt_hashes": {k: v["sha256"] for k, v in prompts["stages"].items()}, "preparation_files": helper_hashes}
    snapshot_id = sha(encoded(identity))[:20]
    folder = root / "storage/experiments/yunost-2024/snapshots" / snapshot_id
    if folder.exists():
        verify(folder)
        return folder
    folder.mkdir(parents=True)
    try:
        months = sorted({r["batch"] for r in rows})
        write_json(folder / "protocol.json", config)
        write_json(folder / "dataset/source-map.json", rows)
        write_json(folder / "dataset/original-selected-lines.json", originals)
        write_json(folder / "dataset/exclusions.json", exclusions)
        for month in months:
            part = [row["record"] for row in rows if row["batch"] == month]
            out = folder / "dataset/batches" / month / "posts.jsonl"
            out.parent.mkdir(parents=True)
            out.write_text("".join(json.dumps(r, ensure_ascii=False, sort_keys=True) + "\n" for r in part), encoding="utf-8")
            # A visible task payload, not a replacement for upstream system prompts.
            write_json(folder / "prompts/openwiki-input" / (month + ".json"), openwiki_task_payload(month, months[0], canon_dir))
        for key, prompt in prompts["stages"].items():
            path = folder / "prompts/tesla" / (key + ".md")
            path.parent.mkdir(parents=True, exist_ok=True)
            path.write_bytes(prompt["effective"].encode("utf-8"))
        write_json(folder / "prompts/tesla/registry-snapshot.json", prompts)
        for name in ("rules.md", "rules_mapping.md"):
            path = folder / "prompts/common" / name
            path.parent.mkdir(parents=True, exist_ok=True)
            path.write_bytes((canon_dir / name).read_bytes())
        if canon_dir != root / "schema":
            for name in ("CHANGES.diff", "manifest.json", "README.md"):
                path = folder / "prompts/research-canon-provenance" / name
                path.parent.mkdir(parents=True, exist_ok=True)
                path.write_bytes((canon_dir / name).read_bytes())
        for path in HERE.iterdir():
            if path.is_file() and path.name in helper_hashes:
                target = folder / "preparation" / path.name
                target.parent.mkdir(parents=True, exist_ok=True)
                target.write_bytes(path.read_bytes())
        openwiki_files = ["package.json", "pnpm-lock.yaml", "LICENSE", "src/agent/prompts/personal.ts", "src/agent/prompt.ts", "src/agent/index.ts", "src/cli/commands.ts", "src/connectors/tools.ts", "src/config/openwiki-home.ts", "src/ingestion/ingestion.ts"]
        for name in openwiki_files:
            # Read Git blobs, not a checkout's possible CRLF conversion.
            content = subprocess.check_output(["git", "-C", str(vendor), "show", config["openwiki_commit"] + ":" + name])
            path = folder / "prompts/openwiki-upstream" / name
            path.parent.mkdir(parents=True, exist_ok=True)
            path.write_bytes(content)
        for name, repo, commit in (("tesla", root, config["tesla_commit"]), ("openwiki", vendor, config["openwiki_commit"])):
            path = folder / "software" / (name + ".tar")
            path.parent.mkdir(parents=True, exist_ok=True)
            subprocess.run(["git", "-C", str(repo), "archive", "--format=tar", "--output", str(path), commit], check=True)
        write_json(folder / "allocation.json", allocation(months, config["planned_repetitions"], config["allocation_seed"]))
        (folder / "REVIEW.html").write_text(review_html(rows, config), encoding="utf-8")
        annotations = folder / "annotations"
        annotations.mkdir()
        (annotations / "gold-facts.draft.jsonl").write_text("", encoding="utf-8")
        with (annotations / "source-review.csv").open("w", encoding="utf-8-sig", newline="") as handle:
            writer = csv.writer(handle)
            writer.writerow(["post_id", "batch", "source_hash", "reviewed_by", "eligible_facts_or_noise", "notes"])
            writer.writerows([r["record"]["post_id"], r["batch"], r["record"]["source_hash"], "", "", ""] for r in rows)
        write_json(annotations / "gold-schema.json", {"$schema": "https://json-schema.org/draft/2020-12/schema", "type": "object", "required": ["fact_id", "claim", "first_available_batch", "evidence", "annotator", "adjudication"], "properties": {"fact_id": {"type": "string", "minLength": 1}, "claim": {"type": "string", "minLength": 1}, "first_available_batch": {"enum": months}, "evidence": {"type": "array", "minItems": 1, "items": {"type": "object", "required": ["post_id", "quote"], "properties": {"post_id": {"enum": [r["record"]["post_id"] for r in rows]}, "quote": {"type": "string", "minLength": 1}}}}, "annotator": {"type": "string", "minLength": 1}, "adjudication": {"enum": ["draft", "approved", "excluded"]}}})
        write_json(folder / "approvals/recorded-scope.json", {"snapshot_id": snapshot_id,
            "decisions": config.get("generation_approvals", {}),
            "reference_limitations": config.get("reference_limitations"),
            "runtime_readiness_is_separate_from_user_authorization": True})
        if config.get("working_reference"):
            reference = root / "storage/experiments/yunost-2024" / config["working_reference"]
            reference_hashes = json.loads((reference / "checksums.json").read_text(encoding="utf-8"))
            for name, expected in reference_hashes.items():
                if sha((reference / name).read_bytes()) != expected:
                    raise ValueError("User-reviewed reference changed after recording")
                target = annotations / "user-reviewed-reference-v2" / name
                target.parent.mkdir(parents=True, exist_ok=True)
                target.write_bytes((reference / name).read_bytes())
            write_json(annotations / "user-reviewed-reference-v2/checksums.json", reference_hashes)
        for rep in range(1, config["planned_repetitions"] + 1):
            for arm in config["arms"]:
                (folder / "runs" / f"r{rep:02d}" / arm / "wiki").mkdir(parents=True)
        manifest = {"snapshot_id": snapshot_id, "created_at_utc": datetime.now(timezone.utc).isoformat(), "study_id": config["study_id"], "source_records": len(rows), "text_characters": sum(len(r["record"]["text_raw"]) for r in rows), "batches": dict(sorted(Counter(r["batch"] for r in rows).items())), "attachments_excluded": dict(Counter({key: sum(r["attachment_counts"].get(key, 0) for r in rows) for key in {k for r in rows for k in r["attachment_counts"]}})), "identity": identity, "tesla_commit": config["tesla_commit"], "openwiki_commit": config["openwiki_commit"], "preparer_git_commit": git(root, "rev-parse", "HEAD"), "status": config["status"], "runtime_adapters": "see_pinned_SUBSCRIPTION_RUN.md_and_RUNTIME_CHECKS.md", "results": None, "llm_calls": 0, "production_before": before}
        write_json(folder / "manifest.json", manifest)
        checksums = {p.relative_to(folder).as_posix(): sha(p.read_bytes()) for p in sorted(folder.rglob("*")) if p.is_file()}
        write_json(folder / "checksums.json", checksums)
        after = production_fingerprint(root)
        if before != after:
            raise RuntimeError("Production fingerprint changed during preparation; investigate before continuing")
        verify(folder)
        return folder
    except BaseException:
        # Preserve failed attempts for diagnosis. They are never reused as valid.
        raise


def preflight(folder: Path) -> dict:
    checked = verify(folder)
    config = json.loads((folder / "protocol.json").read_text(encoding="utf-8"))
    if config.get("paid_api_allowed") is False:
        from study_run import readiness
        runtime = readiness(folder)
        blockers = ["Missing preserved isolated runtime check: " + name for name, passed in runtime["checks"].items() if not passed]
    else:
        blockers = ["Materials have not been approved", "Historical gold facts have not been reviewed and approved", "Protocol is a draft, not yet frozen for execution", "Provider access, supported output limit, pricing and budget have not been verified/approved", "End-to-end paid execution, request logging, isolation and budget enforcement still require validation before a study run"]
    if config.get("prompt_scope_status", "").startswith("blocked"):
        blockers.insert(0, "Current canonical instructions contain historical details outside the selected corpus; research instruction profile needs an explicit decision and diff review")
    return {**checked, "ready_for_generation": not blockers, "blockers": blockers, "planned_repetitions": config["planned_repetitions"], "planned_monthly_updates": config["planned_repetitions"] * len(config["arms"]) * 12, "note": "Updates are not API calls: both methods may issue several calls per update. No cost estimate is asserted."}


def main() -> None:
    if hasattr(sys.stdout, "reconfigure"):
        sys.stdout.reconfigure(encoding="utf-8")
    parser = argparse.ArgumentParser(description=__doc__)
    sub = parser.add_subparsers(dest="command", required=True)
    prep = sub.add_parser("freeze", help="Prepare private review materials; no model calls")
    prep.add_argument("--vendor", type=Path, default=ROOT / "storage/experiments/yunost-2024/vendor/openwiki")
    prep.add_argument("--protocol", type=Path, default=HERE / "protocol.json")
    for name in ("verify", "preflight"):
        command = sub.add_parser(name)
        command.add_argument("snapshot", type=Path)
    args = parser.parse_args()
    if args.command == "freeze":
        folder = freeze(ROOT, args.vendor.resolve(), args.protocol.resolve())
        print(json.dumps({"snapshot": str(folder), **verify(folder)}, ensure_ascii=False))
    else:
        result = verify(args.snapshot.resolve()) if args.command == "verify" else preflight(args.snapshot.resolve())
        print(json.dumps(result, ensure_ascii=False, indent=2))
        if args.command == "preflight" and not result["ready_for_generation"]:
            sys.exit(2)


if __name__ == "__main__":
    main()
