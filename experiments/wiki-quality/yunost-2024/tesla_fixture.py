"""Run the pinned native compiler with a fake Responses client; no network/LLM.

The complete two-stage path creates a page from empty state and then updates it
with insert_after. Production modules are imported from a private Git archive.
"""
from __future__ import annotations

import argparse
from contextlib import nullcontext
import json
import os
from pathlib import Path
import shutil
import subprocess
import sys
import tarfile
import types

import prepare
from tesla_transport import make_provider


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("output", type=Path, help="New directory under storage/experiments/yunost-2024")
    parser.add_argument("--native-archive", type=Path, help="Already frozen git archive; useful on an isolated Linux runner")
    args = parser.parse_args()
    folder = args.output.resolve()
    private = (prepare.ROOT / "storage/experiments/yunost-2024").resolve()
    if not folder.is_relative_to(private) or folder == private:
        raise ValueError("Fixture output must be a new private study directory")
    folder.mkdir(parents=True, exist_ok=False)
    config = json.loads((prepare.HERE / "protocol.json").read_text(encoding="utf-8"))
    archive = folder / "tesla-native.tar"
    if args.native_archive:
        shutil.copyfile(args.native_archive, archive)
    else:
        subprocess.run(["git", "-C", str(prepare.ROOT), "archive", "--format=tar", "--output", str(archive),
                        config["tesla_commit"], "backend", "schema", ".opencode/skills/wiki-editorial/SKILL.md"], check=True)
    project = folder / "native"
    project.mkdir()
    with tarfile.open(archive) as handle:
        if handle.pax_headers.get("comment") != config["tesla_commit"]:
            raise ValueError("Archive Git commit does not match the protocol")
        handle.extractall(project, filter="data")
    os.environ["PYTHON_DOTENV_DISABLED"] = "1"
    os.environ["LANGFUSE_ENABLED"] = "0"
    os.environ["TESLA_ADMIN_DB"] = str(folder / "unused-admin.db")
    sys.path.insert(0, str(project))
    from backend.wiki import ingest_runner as compiler
    from backend.wiki.ingest import inventory
    if os.name == "nt":
        from filelock import FileLock

    requests = []

    def create(**request):
        requests.append(request)
        assert request["model"] == "gpt-6-luna"
        assert request["reasoning"] == {"effort": "medium"}
        data = json.loads(request["input"].split("INPUT BUNDLE:\n", 1)[1])
        if request["text"]["format"]["name"] == "extract":
            result = {"posts": []}
            for p in data["posts"]:
                result["posts"].append({"post_id": p["post_id"], "source_hash": p["source_hash"],
                    "outcome": "extracted", "reason": None, "items": [{"class": "event", "page_slug": "lso/synthetic",
                    "section": "## История", "confidence": "high", "joke_flag": False, "role_scope": None,
                    "status": "verified", "date_event": "2024", "facts": [{"detail": p["text_raw"], "quote": p["text_raw"],
                    "person": None, "role": None, "role_level": None, "attribution": None}]}]})
        else:
            slug = data["target_page_slug"]
            facts = data["candidate_facts"][slug]
            refs = [{"post_id": f["post_id"], "source_hash": f["source_hash"]} for f in facts]
            text = "\n".join(f['facts'][0]['detail'] + f" (Источник: [{f['post_id']}]({f['source_url']}))" for f in facts)
            existing = next((p for p in data["relevant_pages"] if p["page_slug"] == slug), None)
            page = {"page_slug": slug, "new_page": existing is None,
                    "expected_sha256": existing["expected_sha256"] if existing else None,
                    "source_post_ids": [r["post_id"] for r in refs], "source_refs": refs,
                    "covered_facts": [{**r, "ordinal": f["fact_ordinal"]} for r, f in zip(refs, facts)],
                    "markdown": None, "patches": []}
            if existing:
                page["patches"] = [{"operation": "insert_after", "old_text": "## История", "new_text": text}]
            else:
                page["markdown"] = "---\nslug: lso/synthetic\nkind: lso\nstatus: verified\ntitle: Synthetic fixture\ntags: [fixture]\n---\n\n# Synthetic fixture\n\n## История\n\n" + text + "\n"
            result = {"pages": [page]}
        payload = {"id": "synthetic-response", "status": "completed", "model": "gpt-6-luna",
                   "output_text": json.dumps(result, ensure_ascii=False), "usage": {"synthetic": True}}
        return types.SimpleNamespace(status="completed", output_text=payload["output_text"], model_dump=lambda **kwargs: payload)

    client = types.SimpleNamespace(max_retries=0, responses=types.SimpleNamespace(create=create))
    compiler.call_provider_resilient = make_provider(client, compiler, folder / "calls")
    prompts = prepare.prompt_snapshot(project)
    for key, p in prompts["stages"].items():
        (folder / (key + ".md")).write_text(p["effective"], encoding="utf-8")
    db, wiki = folder / "ledger.sqlite", folder / "wiki"
    wiki.mkdir()
    summaries = []
    for index, body in enumerate(("5 января 2024 года прошёл первый синтетический тренинг.",
                                  "10 февраля 2024 года прошёл второй синтетический тренинг."), 1):
        post = {"post_id": f"wall-1_{index}", "group_id": "1", "group_domain": "synthetic",
                "group_name": "Synthetic", "published_at": f"2024-0{index}-15T12:00:00Z",
                "post_url": f"https://vk.com/wall-1_{index}", "text_raw": body, "text_clean": body}
        source = folder / f"month-{index}.jsonl"
        source.write_text(json.dumps(post, ensure_ascii=False) + "\n", encoding="utf-8")
        inventory(db, source)
        # Native fcntl lock is Linux-only. Keep native compiler unchanged and use
        # the established cross-platform filelock library for the fixture.
        lock = FileLock(str(db) + ".research.lock", timeout=0) if os.name == "nt" else nullcontext()
        compile_fn = compiler.compile_wiki.__wrapped__ if os.name == "nt" else compiler.compile_wiki
        with lock:
            result = compile_fn(db, wiki, folder / f"run-{index}",
                folder / "wiki_extract.md", folder / "wiki_merge.md", max_posts=50,
                extract_model="gpt-6-luna", extract_fallback_models=(), merge_model="gpt-6-luna",
                merge_fallback_models=(), do_apply=True, codex_fallback=False)
        assert result["applied_pages"] == 1, result
        assert result["queued_posts"] == 0, result
        summaries.append(result)
    content = (wiki / "lso/synthetic.md").read_text(encoding="utf-8")
    assert "первый синтетический" in content and "второй синтетический" in content
    assert len(requests) == 4, len(requests)
    report = {"status": "passed", "llm_calls": 0, "fake_responses": len(requests),
              "tesla_commit": config["tesla_commit"], "native_compiler_modified": False,
              "native_archive_sha256": prepare.sha(archive.read_bytes()),
              "checks": ["empty_wiki_creation", "next_month_insert_after", "old_fact_retained",
                         "exact_quote_validation", "medium_both_stages", "request_response_logs"],
              "lock_adapter": "filelock around compile_wiki.__wrapped__" if os.name == "nt" else "native fcntl",
              "platform": sys.platform, "summaries": summaries}
    prepare.write_json(folder / "fixture-report.json", report)
    print(json.dumps({"status": "passed", "llm_calls": 0, "report": str(folder / "fixture-report.json")}))


if __name__ == "__main__":
    if hasattr(sys.stdout, "reconfigure"): sys.stdout.reconfigure(encoding="utf-8")
    main()
