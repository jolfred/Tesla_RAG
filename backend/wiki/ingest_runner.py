"""Resumable extraction -> editorial merge -> validated application runner."""
from __future__ import annotations

import json
import datetime
import functools
import selectors
import re
import shutil
import subprocess
import tempfile
import time
from pathlib import Path
from typing import Any

from backend.wiki.ingest import (
    apply_proposals, connect, export_posts, import_results, relevant_page_catalog, relevant_pages,
    stage_proposals,
)
from backend.wiki.cli_isolation import opencode_command

FREE_MODELS = {
    "opencode/mimo-v2.6-flash-free",
    "opencode/nemotron-3-ultra-free",
    "opencode/longcat-2.5-preview-free",
}


def _atomic_json(path: Path, payload: Any) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_suffix(path.suffix + ".tmp")
    tmp.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")
    tmp.replace(path)


def _merge_rows(db: Path, wiki: Path, run_dir: Path, rows: list[Any], merge_prompt: Path,
                model: str, fallbacks: tuple[str, ...], codex_fallback: bool,
                agent: str, do_apply: bool) -> tuple[int, int]:
    grouped: dict[str, list[dict[str, Any]]] = {}
    for row in rows:
        fact = json.loads(row[0]); fact.update(post_id=row[1], source_hash=row[2], fact_ordinal=row[3])
        source = json.loads(row[4]); fact.update(source_url=source.get("post_url"), published_at=source.get("published_at"),
                                                 group_name=source.get("group_name"), group_domain=source.get("group_domain"),
                                                 source_kind=source.get("source_kind"), archive_source_uri=source.get("archive_source_uri"),
                                                 source_segments=source.get("source_segments"))
        grouped.setdefault(fact["page_slug"], []).append(fact)
    merge_calls = applied = 0
    for slug, facts in sorted(grouped.items()):
        refs = sorted({(f["post_id"], f["source_hash"], f["fact_ordinal"]) for f in facts})
        target = wiki / (slug + ("" if slug.endswith(".md") else ".md"))
        if not target.resolve().is_relative_to(wiki.resolve()):
            _set_facts_review(db, facts, "target resolves outside the Wiki directory")
            continue
        if target.is_file():
            pages = [{"page_slug":slug, "expected_sha256":__import__("hashlib").sha256(target.read_bytes()).hexdigest(),
                      "markdown":target.read_text(encoding="utf-8")}]
        else:
            query = " ".join([slug] + [fact.get("detail", "") for item in facts for fact in item.get("facts", [])])
            pages = relevant_pages(wiki, query, 5)
        context = json.dumps(pages, ensure_ascii=False, sort_keys=True)
        merge_key = __import__("hashlib").sha256((slug + "\n" + merge_prompt.read_text(encoding="utf-8") + "\n" + context + "\n" + "\n".join(":".join(map(str, ref)) for ref in refs)).encode()).hexdigest()[:16]
        merge_dir = run_dir / "merge" / merge_key; merge_dir.mkdir(parents=True, exist_ok=True)
        bundle_path = merge_dir / "merge-input.json"
        _atomic_json(bundle_path, {"candidate_facts": {slug:facts}, "target_page_slug":slug, "relevant_pages":pages[:5]})
        output = merge_dir / "merge.json"
        if not output.exists():
            try:
                choices = (model, *fallbacks)
                call_provider_resilient("medium", merge_prompt, bundle_path, output, merge_dir / "merge-work",
                                        choices, codex_fallback, agent, run_dir)
            except Exception as exc:
                _record_blocked_facts(db, facts, f"merge blocked: {type(exc).__name__}")
                raise
        try:
            merged = _json_object(output.read_text(encoding="utf-8"))
        except ValueError:
            _set_facts_review(db, facts, "merge output is not valid JSON")
            raise
        candidates = [x for x in merged.get("pages", []) if x.get("page_slug") == slug]
        if len(candidates) != 1:
            _set_facts_review(db, facts, "merge omitted or duplicated the requested target page")
            continue
        merged = {"pages": candidates}; _atomic_json(output, merged)
        try:
            stage_proposals(db, wiki, output)
        except (ValueError, TypeError, KeyError) as exc:
            _set_facts_review(db, facts, f"merge proposal validation failed: {type(exc).__name__}")
            continue
        merge_calls += 1
        con = connect(db); proposal = con.execute("SELECT state,reason FROM proposals WHERE page_slug=?", (slug,)).fetchone(); con.close()
        if not proposal or proposal["state"] != "staged":
            _set_facts_review(db, facts, proposal["reason"] if proposal else "merge proposal was not staged")
            continue
        if do_apply: applied += apply_proposals(db, wiki).get("applied_pages", 0)
    return merge_calls, applied


def _json_object(text: str) -> dict[str, Any]:
    raw = text.strip()
    if raw.startswith("```"):
        raw = re.sub(r"^```(?:json)?\s*", "", raw, count=1)
        raw = re.sub(r"\s*```$", "", raw, count=1)
    try:
        obj = json.loads(raw)
    except json.JSONDecodeError as exc:
        # A complete child object in a broken batch is not a valid batch.
        raise ValueError("provider output is not a complete JSON object") from exc
    if not isinstance(obj, dict):
        raise ValueError("provider output must be a JSON object")
    return obj


def _output_schema(stage: str) -> dict[str, Any]:
    def obj(properties: dict) -> dict:
        return {"type":"object", "properties":properties, "required":list(properties), "additionalProperties":False}
    def array(items: dict) -> dict:
        return {"type":"array", "items":items}
    string = {"type":"string"}
    nullable = {"type":["string","null"]}
    source = obj({"post_id":string,"source_hash":string})
    if stage == "extract":
        fact = obj({"detail":string,"quote":string,"person":nullable,"role":nullable,"role_level":nullable,"attribution":nullable})
        item = obj({"class":string,"page_slug":string,"section":string,"confidence":string,"joke_flag":{"type":"boolean"},
                    "role_scope":nullable,"status":nullable,"date_event":nullable,"facts":array(fact)})
        post = obj({"post_id":string,"source_hash":string,"outcome":string,"reason":nullable,"items":array(item)})
        return obj({"posts":array(post)})
    covered = obj({"post_id":string,"source_hash":string,"ordinal":{"type":"integer"}})
    patch = obj({"old_text":string,"new_text":string})
    page = obj({"page_slug":string,"expected_sha256":nullable,"new_page":{"type":"boolean"},
                "source_post_ids":array(string),"source_refs":array(source),"covered_facts":array(covered),"markdown":nullable,"patches":array(patch)})
    return obj({"pages":array(page)})


def _opencode_text(stdout: str) -> str:
    chunks = []
    for line in stdout.splitlines():
        try: event = json.loads(line)
        except json.JSONDecodeError: continue
        if isinstance(event, dict) and event.get("type") == "error":
            status = event.get("error", {}).get("data", {}).get("statusCode")
            raise RuntimeError(f"OpenCode returned a provider error (HTTP {status or 'unknown'})")
        if not isinstance(event, dict):
            continue
        part = event.get("part", {})
        if event.get("type") == "text" and isinstance(part, dict) and isinstance(part.get("text"), str): chunks.append(part["text"])
        elif event.get("type") == "text" and isinstance(event.get("text"), str): chunks.append(event["text"])
    return "\n".join(chunks) if chunks else stdout


def _run_cli(cmd: list[str], work: str | Path, log_path: Path, *, input_text: str | None = None):
    """Persist progress while a provider is running, including failed attempts."""
    with log_path.open("w", encoding="utf-8") as log:
        proc = subprocess.run(cmd, input=input_text, text=True, cwd=work,
                              stdout=log, stderr=subprocess.STDOUT, timeout=900)
        # Offline tests supply a completed result in place of subprocess.run.
        if isinstance(getattr(proc, "stdout", None), str):
            log.write(proc.stdout)
        if isinstance(getattr(proc, "stderr", None), str):
            log.write("\n" + proc.stderr)
    return proc, log_path.read_text(encoding="utf-8")


def read_codex_limits(timeout: float = 35.0) -> dict[str, int]:
    """Read authenticated rate limits from Codex app-server; never return account identifiers."""
    binary = shutil.which("codex")
    if not binary: raise RuntimeError("Codex CLI unavailable for rate-limit check")
    proc = subprocess.Popen([binary, "app-server", "--listen", "stdio://"], stdin=subprocess.PIPE,
                            stdout=subprocess.PIPE, stderr=subprocess.DEVNULL, text=True, bufsize=1)
    selector = selectors.DefaultSelector(); selector.register(proc.stdout, selectors.EVENT_READ)
    deadline = time.monotonic() + timeout
    def send(obj: dict[str, Any]) -> None:
        assert proc.stdin
        proc.stdin.write(json.dumps(obj) + "\n"); proc.stdin.flush()
    def response(rid: int) -> dict[str, Any]:
        while time.monotonic() < deadline:
            if not selector.select(timeout=min(1.0, max(0, deadline-time.monotonic()))): continue
            line = proc.stdout.readline()
            if not line: raise RuntimeError("Codex app-server closed")
            obj = json.loads(line)
            if obj.get("id") == rid: return obj
        raise TimeoutError("Codex rate-limit check timed out")
    try:
        send({"id": 1, "method": "initialize", "params": {"clientInfo": {"name": "tesla-wiki-ingest", "version": "1.0"}}})
        response(1); send({"method": "initialized"})
        send({"id": 2, "method": "account/rateLimits/read", "params": {"excludeResetCreditDetails": True}})
        result = response(2)
        if "error" in result: raise RuntimeError("Codex rate-limit RPC returned an error")
        limits = result.get("result", {}).get("rateLimits", {})
        primary = limits.get("primary", {}).get("usedPercent")
        secondary = limits.get("secondary", {}).get("usedPercent")
        if not isinstance(primary, (int, float)) or not 0 <= primary <= 100:
            raise RuntimeError("Codex primary rate limit is unavailable")
        if not isinstance(secondary, (int, float)) or not 0 <= secondary <= 100:
            raise RuntimeError("Codex secondary rate limit is unavailable")
        return {"primary_used_percent": primary,
                "secondary_used_percent": secondary}
    finally:
        selector.close(); proc.terminate()
        try: proc.wait(timeout=3)
        except subprocess.TimeoutExpired: proc.kill()


def call_provider(provider: str, effort: str, system_prompt: Path, bundle_path: Path,
                  output_path: Path, workdir: Path, model: str | None = None,
                  agent: str = "plan") -> dict[str, Any]:
    """Call a CLI; only the supplied batch bundle is in the model context."""
    workdir.mkdir(parents=True, exist_ok=True); output_path.parent.mkdir(parents=True, exist_ok=True)
    prompt = system_prompt.read_text(encoding="utf-8")
    _validate_canonical_prompt(prompt)
    if provider == "codex":
        # Explicit Luna model; keep each stage's requested reasoning effort.
        schema_path = output_path.with_suffix(".schema.json")
        _atomic_json(schema_path, _output_schema("extract" if "extract" in system_prompt.name else "merge"))
        cmd = ["codex", "exec", "--ephemeral", "--sandbox", "read-only", "--skip-git-repo-check",
               "-m", "gpt-6-luna", "-c", f'model_reasoning_effort="{effort}"', "--output-schema", str(schema_path), "-o", str(output_path), "-"]
        user = "Return only the JSON object required by the system instructions.\n\nINPUT BUNDLE:\n" + bundle_path.read_text(encoding="utf-8")
        with tempfile.TemporaryDirectory(prefix="tesla-wiki-cli-") as isolated:
            proc, _ = _run_cli(cmd, isolated, output_path.with_suffix(".cli.log"), input_text=prompt + "\n\n" + user)
        if proc.returncode != 0: raise RuntimeError(f"codex exited {proc.returncode}; see CLI log")
        response = output_path.read_text(encoding="utf-8") if output_path.exists() else ""
    elif provider == "opencode":
        if model not in FREE_MODELS: raise ValueError("OpenCode model is not in the verified free-model allowlist")
        prompt_file = output_path.parent / (output_path.stem + "-system-prompt.md")
        prompt_file.write_text(prompt, encoding="utf-8")
        # Keep automatic ancestor instructions and repository files out of the
        # provider context. Only the two explicitly attached files are supplied.
        with tempfile.TemporaryDirectory(prefix="tesla-wiki-cli-") as isolated:
            staged_prompt = Path(isolated) / "stage-instructions.md"
            staged_bundle = Path(isolated) / "input-bundle.json"
            shutil.copyfile(prompt_file, staged_prompt)
            shutil.copyfile(bundle_path, staged_bundle)
            cmd = opencode_command(Path(isolated), model, agent, effort)
            proc, stdout = _run_cli(cmd, isolated, output_path.with_suffix(".cli.log"))
        if proc.returncode != 0: raise RuntimeError(f"opencode exited {proc.returncode}; see CLI log")
        response = _opencode_text(stdout)
        _atomic_json(output_path, _json_object(response))
    else:
        raise ValueError("provider must be codex or opencode; GigaChat remains a separate explicit command")
    if provider == "codex":
        obj = _json_object(response)
        _atomic_json(output_path, obj)
        return obj
    return _json_object(response)


def _exclusive_compile(function):
    @functools.wraps(function)
    def locked(db: Path, *args, **kwargs):
        import fcntl
        db.parent.mkdir(parents=True, exist_ok=True)
        with db.with_suffix(db.suffix + ".compile.lock").open("a") as lock:
            try:
                fcntl.flock(lock, fcntl.LOCK_EX | fcntl.LOCK_NB)
            except BlockingIOError as exc:
                raise RuntimeError("another compiler is already using this ledger") from exc
            return function(db, *args, **kwargs)
    return locked


@_exclusive_compile
def compile_wiki(db: Path, wiki: Path, run_dir: Path,
                 extract_prompt: Path, merge_prompt: Path, max_posts: int = 5,
                 batch_size: int = 50, char_budget: int = 40000,
                 extract_model: str = "opencode/longcat-2.5-preview-free",
                 extract_fallback_models: tuple[str, ...] = ("opencode/mimo-v2.6-flash-free", "opencode/nemotron-3-ultra-free"),
                 merge_model: str = "opencode/longcat-2.5-preview-free",
                 merge_fallback_models: tuple[str, ...] = ("opencode/mimo-v2.6-flash-free", "opencode/nemotron-3-ultra-free"),
                 do_apply: bool = False, codex_fallback: bool = True,
                 agent: str = "plan") -> dict[str, int]:
    if batch_size < 1 or batch_size > 50: raise ValueError("batch_size must be 1..50")
    if char_budget < 1: raise ValueError("char_budget must be positive")
    if max_posts < 1: raise ValueError("max_posts must be positive")
    if not do_apply and max_posts > batch_size:
        raise ValueError("multi-batch compile requires --apply to preserve accumulated page proposals")
    run_dir.mkdir(parents=True, exist_ok=True)
    queue = export_posts(db, min(batch_size, max_posts), state="queued", max_chars=char_budget)
    # Continue through the queue, preserving per-batch inputs and outputs.
    extracted = refused = calls = processed = merge_calls = applied = 0
    if do_apply:
        con = connect(db)
        pending = con.execute("SELECT f.payload,p.post_id,p.source_hash,f.ordinal,p.source_json FROM facts f JOIN posts p USING(post_id,source_hash) WHERE f.state='extracted'").fetchall()
        con.close()
        if pending:
            merge_calls, applied = _merge_rows(db, wiki, run_dir, pending, merge_prompt, merge_model,
                                              merge_fallback_models, codex_fallback, agent, True)
    while queue and processed < max_posts:
        calls += 1
        queue = queue[:min(batch_size, max_posts - processed)]
        processed += len(queue)
        batch_identity = "\n".join(x["post_id"] + ":" + x["source_hash"] for x in queue)
        batch_key = __import__("hashlib").sha256(batch_identity.encode()).hexdigest()[:16]
        batch_dir = run_dir / f"batch-{batch_key}"; batch_dir.mkdir(parents=True, exist_ok=True)
        bundle_posts = [{"post_id": post["post_id"], "source_hash": post["source_hash"],
                         "source_kind": post.get("source_kind", "vk_post"),
                         "published_at": post.get("published_at"), "text_raw": post.get("text_raw", ""),
                         "archive_source_uri": post.get("archive_source_uri"),
                         "source_segments": post.get("source_segments")}
                        for post in queue]
        query = " ".join(post["post_id"] + " " + str(post.get("text_clean") or post.get("text_raw") or "") for post in queue)
        pages = relevant_page_catalog(wiki, query, 5)
        bundle_posts = [{**x, "group_name": post.get("group_name"), "group_domain": post.get("group_domain"),
                         "post_url": post.get("post_url")}
                        for x, post in zip(bundle_posts, queue)]
        extract_bundle = batch_dir / "extract-input.json"
        _atomic_json(extract_bundle, {"posts": bundle_posts, "relevant_pages": pages})
        extract_out = batch_dir / "extract.json"
        if not extract_out.exists():
            try:
                call_provider_resilient("low", extract_prompt, extract_bundle, extract_out,
                    batch_dir / "extract-work", (extract_model, *extract_fallback_models), codex_fallback, agent, run_dir)
            except Exception as exc:
                _record_queued_reason(db, queue, f"extraction blocked: {type(exc).__name__}")
                raise
        extract_result = _json_object(extract_out.read_text(encoding="utf-8"))
        expected = {(x["post_id"], x["source_hash"]) for x in bundle_posts}
        received = [(str(x.get("post_id", "")), str(x.get("source_hash", ""))) for x in extract_result.get("posts", [])]
        if len(received) != len(set(received)) or set(received) != expected:
            raise ValueError(f"batch {batch_key}: extraction must return exactly one result per supplied post; output retained for repair")
        # Persist/import before fetching next batch. Reimport is idempotent by (post, source hash, item ordinal).
        _atomic_json(batch_dir / "extract.json", extract_result)
        got = import_results(db, extract_out)
        extracted += got.get("extracted", 0); refused += got.get("refused", 0) + got.get("review", 0)
        if do_apply:
            con = connect(db)
            rows = con.execute("SELECT f.payload,p.post_id,p.source_hash,f.ordinal,p.source_json FROM facts f JOIN posts p USING(post_id,source_hash) WHERE f.state='extracted'").fetchall()
            con.close()
            mc, ac = _merge_rows(db, wiki, run_dir, rows, merge_prompt, merge_model, merge_fallback_models, codex_fallback, agent, True)
            merge_calls += mc; applied += ac
        remaining = max_posts - processed
        queue = export_posts(db, min(batch_size, remaining), state="queued", max_chars=char_budget) if remaining > 0 else []

    # Resume and merge every grounded high-confidence fact that has not reached a page.
    con = connect(db)
    fact_rows = con.execute("SELECT f.payload,p.post_id,p.source_hash,f.ordinal,p.source_json FROM facts f JOIN posts p USING(post_id,source_hash) WHERE f.state='extracted' ORDER BY f.page_path,p.post_id,f.ordinal").fetchall()
    con.close()
    if fact_rows:
        mc, ac = _merge_rows(db, wiki, run_dir, fact_rows, merge_prompt, merge_model,
                             merge_fallback_models, codex_fallback, agent, do_apply)
        merge_calls += mc; applied += ac
    return {"batches": calls, "merge_calls": merge_calls, "extracted_facts": extracted, "review_or_refused": refused,
            "staged_pages": _count_state(db, "staged"), "applied_pages": applied,
            "review_posts": _count_posts(db, "review"), "queued_posts": _count_posts(db, "queued")}


def _count_state(db: Path, state: str) -> int:
    con = connect(db)
    count = con.execute("SELECT count(*) FROM proposals WHERE state=?", (state,)).fetchone()[0]
    con.close(); return count


def _count_posts(db: Path, state: str) -> int:
    con = connect(db); count = con.execute("SELECT count(*) FROM posts WHERE state=?", (state,)).fetchone()[0]
    con.close(); return count


def _record_queued_reason(db: Path, posts: list[dict[str, Any]], reason: str) -> None:
    con = connect(db)
    for post in posts:
        con.execute("UPDATE posts SET reason=?,updated_at=CURRENT_TIMESTAMP WHERE post_id=? AND source_hash=? AND state='queued'",
                    (reason, post["post_id"], post["source_hash"]))
    con.commit(); con.close()


def _record_blocked_facts(db: Path, facts: list[dict[str, Any]], reason: str) -> None:
    con = connect(db)
    for item in facts:
        con.execute("UPDATE facts SET reason=? WHERE post_id=? AND source_hash=? AND ordinal=? AND state='extracted'",
                    (reason, item["post_id"], item["source_hash"], item["fact_ordinal"]))
    con.commit(); con.close()


def _set_facts_review(db: Path, facts: list[dict[str, Any]], reason: str) -> None:
    con = connect(db)
    for item in facts:
        con.execute("UPDATE facts SET state='review',reason=? WHERE post_id=? AND source_hash=? AND ordinal=? AND state='extracted'",
                    (reason,item["post_id"],item["source_hash"],item["fact_ordinal"]))
        con.execute("UPDATE posts SET state='review',reason=?,updated_at=CURRENT_TIMESTAMP WHERE post_id=? AND source_hash=?",
                    (reason,item["post_id"],item["source_hash"]))
    con.commit(); con.close()


def _codex_eligible(run_dir: Path) -> bool:
    try:
        limits = read_codex_limits()
    except Exception:
        _atomic_json(run_dir / "quota-status.json", {"selected_provider": "blocked", "reason": "actual Codex limits unavailable", "limit_values_available": False})
        return False
    remaining = min(100 - limits["primary_used_percent"], 100 - limits["secondary_used_percent"])
    limits["primary_remaining_percent"] = 100 - limits["primary_used_percent"]
    limits["secondary_remaining_percent"] = 100 - limits["secondary_used_percent"]
    limits["minimum_remaining_percent"] = remaining
    limits["threshold_percent"] = 10
    limits["selected_provider"] = "codex" if remaining > 10 else "blocked"
    _atomic_json(run_dir / "quota-status.json", limits)
    return remaining > 10


def _validate_canonical_prompt(prompt: str) -> None:
    root = Path(__file__).resolve().parents[2]
    for relative in ("schema/rules.md", "schema/rules_mapping.md"):
        canonical = (root / relative).read_text(encoding="utf-8")
        if canonical not in prompt:
            raise ValueError(f"operational prompt is missing verbatim {relative}")


def call_provider_resilient(effort: str, system_prompt: Path, bundle_path: Path, output_path: Path,
                            workdir: Path, free_models: tuple[str, ...], codex_fallback: bool,
                            agent: str, run_dir: Path) -> dict[str, Any]:
    failures = []
    for free_model in dict.fromkeys(free_models):
        if free_model not in FREE_MODELS:
            failures.append({"model": free_model, "error": "model_not_allowlisted"}); continue
        try:
            _provider_event(run_dir, {"provider":"opencode","model":free_model,"effort":effort,"status":"running"})
            result = call_provider("opencode", effort, system_prompt, bundle_path, output_path, workdir, free_model, agent)
            _provider_event(run_dir, {"provider":"opencode","model":free_model,"effort":effort,"status":"success"})
            return result
        except (subprocess.TimeoutExpired, RuntimeError, ValueError) as exc:
            log = output_path.with_suffix(".cli.log")
            if log.exists():
                shutil.copyfile(log, output_path.with_suffix("." + free_model.rsplit("/", 1)[-1] + ".cli.log"))
            failures.append({"model": free_model, "error": type(exc).__name__, "detail":str(exc)})
            _atomic_json(output_path.with_suffix(".free-failed.json"), failures)
    if codex_fallback and _codex_eligible(run_dir):
        try:
            _provider_event(run_dir, {"provider":"codex","model":"gpt-6-luna","effort":effort,"status":"running"})
            result = call_provider("codex", effort, system_prompt, bundle_path, output_path, workdir)
            _provider_event(run_dir, {"provider":"codex","model":"gpt-6-luna","effort":effort,"status":"success"})
            return result
        except (subprocess.TimeoutExpired, RuntimeError, ValueError) as exc:
            failures.append({"model":"gpt-6-luna","error":type(exc).__name__})
    _atomic_json(output_path.with_suffix(".blocked.json"), {"reason":"all free OpenCode models failed; Codex ineligible or disabled","free_failures":failures})
    _provider_event(run_dir, {"provider":"blocked","effort":effort,"status":"blocked"})
    raise RuntimeError("all free OpenCode models failed; Codex fallback is disabled, unavailable, failed, or blocked by the actual quota guard; see saved provider status")


def _provider_event(run_dir: Path, event: dict[str, Any]) -> None:
    path=run_dir/"provider-events.jsonl"; path.parent.mkdir(parents=True,exist_ok=True)
    with path.open("a",encoding="utf-8") as f:
        f.write(json.dumps({"at":datetime.datetime.now(datetime.timezone.utc).isoformat(),**event},ensure_ascii=False)+"\n")
