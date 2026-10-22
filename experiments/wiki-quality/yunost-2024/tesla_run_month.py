"""Run one frozen chronological month with the pinned native Tesla compiler.

This is a thin invocation adapter, not a new ingestion method. A fresh job
directory preserves every attempt; no automatic retry or publication occurs.
"""
import argparse
from contextlib import closing
import json
import os
from pathlib import Path
import shutil
import sqlite3
import sys
import tarfile
import time

import prepare
from tesla_codex_transport import make_provider


def main(config_path):
    config = json.loads(config_path.read_text(encoding="utf-8"))
    folder = Path(config["output"]).resolve()
    private = (prepare.ROOT / "storage/experiments/yunost-2024").resolve()
    if not folder.is_relative_to(private) or folder == private:
        raise ValueError("Study job must be in the isolated private research root")
    folder.mkdir(parents=True, exist_ok=False)
    prepare.write_json(folder / "job-config.json", config)

    def verified(name):
        path = Path(config[name])
        if prepare.sha(path.read_bytes()) != config[name + "_sha256"]:
            raise ValueError("Frozen input hash mismatch: " + name)
        return path

    batch = verified("batch_file")
    records = [json.loads(line) for line in batch.read_text(encoding="utf-8").splitlines() if line.strip()]
    for record in records:
        if (record["group_domain"] != "spoyunost2020" or str(record["group_id"]) != "198864697"
                or prepare.parse_date(record["published_at"]).astimezone(prepare.MSK).strftime("%Y-%m") != config["month"]):
            raise ValueError("Source outside the selected community/month")
    if os.name == "nt": raise ValueError("The study runner requires Linux")
    project = folder / "native"
    project.mkdir()
    archive = verified("native_archive")
    with tarfile.open(archive) as handle:
        if handle.pax_headers.get("comment") != "19380cc8a3c59a242d4b6a44459248d357e1c5f6":
            raise ValueError("Wrong native compiler version")
        handle.extractall(project, filter="data")
    for name in ("rules", "rules_mapping"):
        shutil.copyfile(verified(name), project / "schema" / (name + ".md"))
    extract, merge = verified("extract_prompt"), verified("merge_prompt")
    wiki, db = folder / "wiki", folder / "ledger.sqlite"
    previous = config.get("previous")
    if previous:
        prior = Path(previous).resolve()
        if not prior.is_relative_to(private): raise ValueError("Previous checkpoint outside study root")
        report = json.loads((prior / "report.json").read_text(encoding="utf-8"))
        expected_previous_month = f"2024-{int(config['month'][-2:]) - 1:02d}"
        if (report["status"] != "completed" or report["snapshot_id"] != config["snapshot_id"]
                or report["month"] != expected_previous_month):
            raise ValueError("Previous checkpoint has wrong version/month/status")
        shutil.copytree(prior / "wiki", wiki)
        with closing(sqlite3.connect((prior / "ledger.sqlite").as_uri() + "?mode=ro", uri=True)) as source:
            with closing(sqlite3.connect(db)) as destination: source.backup(destination)
    else:
        if config["month"] != "2024-01": raise ValueError("Only January may start empty")
        wiki.mkdir()
    os.environ.update(PYTHON_DOTENV_DISABLED="1", LANGFUSE_ENABLED="0", TESLA_ADMIN_DB=str(folder / "unused-admin.db"))
    sys.path.insert(0, str(project))
    from backend.wiki import ingest_runner as compiler
    from backend.wiki.ingest import inventory
    compiler.call_provider_resilient = make_provider(compiler)
    started = time.monotonic()
    report = {"snapshot_id": config["snapshot_id"], "month": config["month"], "arm": "tesla",
              "model": "gpt-6-luna", "effort": "medium", "paid_api_allowed": False,
              "study_data_used": True, "native_compiler_modified": False, "source_records": len(records)}
    try:
        inventory(db, batch)
        summary = compiler.compile_wiki(db, wiki, folder / "run", extract, merge,
            max_posts=2**31 - 1, batch_size=50, char_budget=40000,
            extract_model="gpt-6-luna", extract_fallback_models=(),
            merge_model="gpt-6-luna", merge_fallback_models=(), do_apply=True, codex_fallback=False)
        report.update(status="completed", native_summary=summary)
    except BaseException as exc:
        report.update(status="failed", error_type=type(exc).__name__)
        raise
    finally:
        report["wall_seconds"] = time.monotonic() - started
        report["cli_calls"] = len(list(folder.rglob("*.cli.log")))
        prepare.write_json(folder / "report.json", report)
        print(json.dumps(report, ensure_ascii=False))


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("config", type=Path)
    main(parser.parse_args().config)
