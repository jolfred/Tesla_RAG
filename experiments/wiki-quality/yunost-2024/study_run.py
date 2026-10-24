"""Run one frozen monthly job natively on Linux, preserving attempt evidence.

Only the selected month and this arm/repetition's checkpoint enter bwrap.
Runtime configuration contains server-local paths, never credentials themselves.
"""
import argparse
from contextlib import contextmanager
import json
from pathlib import Path
import shutil
import subprocess
import sys

import prepare

PRIVATE = prepare.ROOT / "storage/experiments/yunost-2024"
VIRTUAL = "/study/storage/experiments/yunost-2024"


def files(folder):
    found = {}
    for p in sorted(folder.rglob("*")):
        if p.is_symlink(): raise ValueError("Links are forbidden in study evidence")
        if p.is_file() and p != folder / "checksums.json":
            found[p.relative_to(folder).as_posix()] = prepare.sha(p.read_bytes())
    return found


def verify_evidence(folder):
    expected = json.loads((folder / "checksums.json").read_text(encoding="utf-8"))
    if files(folder) != expected: raise ValueError("Attempt evidence changed: " + str(folder))
    return expected


def steps(snapshot):
    return [(pair, arm) for pair in json.loads((snapshot / "allocation.json").read_text(encoding="utf-8"))
            for arm in pair["order"]]


def step_name(pair, arm):
    return f"p{pair['pair']:03d}-r{pair['repetition']:02d}-{pair['batch']}-{arm}"


def coordinator_ok(folder):
    report = folder / "coordinator-report.json"
    if report.exists():
        return json.loads(report.read_text(encoding="utf-8")).get("returncode") == 0
    attempt = folder / "attempt.json"
    return not attempt.exists() or json.loads(attempt.read_text(encoding="utf-8")).get("transport") != "native-linux"


def next_step(snapshot):
    run_root = PRIVATE / "executions" / snapshot.name
    for pair, arm in steps(snapshot):
        folder = run_root / step_name(pair, arm)
        if not folder.exists(): return pair, arm
        verify_evidence(folder)
        report_path = folder / "output/result/report.json"
        report = json.loads(report_path.read_text(encoding="utf-8")) if report_path.exists() else {}
        launch = json.loads((folder / "output/launcher-report.json").read_text(encoding="utf-8"))
        if (not coordinator_ok(folder) or report.get("status") != "completed" or launch.get("returncode") != 0
                or report.get("snapshot_id") != snapshot.name or report.get("arm") != arm
                or report.get("repetition") != pair["repetition"] or report.get("month") != pair["batch"]):
            raise RuntimeError("Recorded unsuccessful attempt requires explicit inspection: " + str(folder))
    return None


def previous_result(snapshot, pair, arm):
    if pair["batch"] == "2024-01": return None
    month = f"2024-{int(pair['batch'][-2:]) - 1:02d}"
    match = [p for p, a in steps(snapshot) if a == arm and p["repetition"] == pair["repetition"] and p["batch"] == month]
    assert len(match) == 1
    folder = PRIVATE / "executions" / snapshot.name / step_name(match[0], arm)
    verify_evidence(folder)
    checkpoint = folder / "output/result"
    verify_evidence(checkpoint)
    return checkpoint


def readiness(snapshot):
    """Require preserved live fixtures in the very same frozen job runtime."""
    root = PRIVATE / "runtime-checks" / snapshot.name
    passed = {"isolation": False, "openwiki": False, "tesla": False}
    for folder in sorted(root.glob("*")):
        if not (folder / "checksums.json").exists(): continue
        verify_evidence(folder)
        if not coordinator_ok(folder): continue
        launch_file = folder / "output/launcher-report.json"
        if not launch_file.exists(): continue
        launch = json.loads(launch_file.read_text(encoding="utf-8"))
        if launch.get("returncode") != 0: continue
        attempt = json.loads((folder / "attempt.json").read_text(encoding="utf-8"))
        if attempt["snapshot_id"] != snapshot.name: continue
        passed["isolation"] = True
        report_file = folder / "output/result" / ("fixture-report.json" if attempt["arm"] == "tesla" else "report.json")
        if attempt.get("synthetic") and report_file.exists():
            report = json.loads(report_file.read_text(encoding="utf-8"))
            if report.get("status") == "passed" and report.get("study_data_used") is False:
                passed[attempt["arm"]] = True
    return {"ready": all(passed.values()), "checks": passed}


def job_inputs(snapshot, pair, arm):
    sums = json.loads((snapshot / "checksums.json").read_text(encoding="utf-8"))
    selected = {"posts.jsonl": f"dataset/batches/{pair['batch']}/posts.jsonl"}
    if arm == "openwiki": selected["task.json"] = f"prompts/openwiki-input/{pair['batch']}.json"
    else:
        selected.update({"tesla.tar": "software/tesla.tar", "rules.md": "prompts/common/rules.md",
            "rules_mapping.md": "prompts/common/rules_mapping.md", "extract.md": "prompts/tesla/wiki_extract.md",
            "merge.md": "prompts/tesla/wiki_merge.md"})
    blobs = {name: (snapshot / rel).read_bytes() for name, rel in selected.items()}
    for name, rel in selected.items():
        if prepare.sha(blobs[name]) != sums[rel]: raise ValueError("Frozen input mismatch: " + rel)
    config = {"snapshot_id": snapshot.name, "month": pair["batch"], "repetition": pair["repetition"]}
    if arm == "openwiki":
        config.update(batch_file="/inputs/posts.jsonl", batch_sha256=sums[selected["posts.jsonl"]],
                      task_file="/inputs/task.json", task_sha256=sums[selected["task.json"]])
    else:
        config["output"] = VIRTUAL + "/working/result"
        for field, name in {"batch_file": "posts.jsonl", "native_archive": "tesla.tar", "rules": "rules.md",
                            "rules_mapping": "rules_mapping.md", "extract_prompt": "extract.md", "merge_prompt": "merge.md"}.items():
            config[field] = "/inputs/" + name
            config[field + "_sha256"] = sums[selected[name]]
    return blobs, config


@contextmanager
def schedule_lock():
    import fcntl
    PRIVATE.mkdir(parents=True, exist_ok=True)
    with (PRIVATE / "coordinator.lock").open("a") as lock:
        try:
            fcntl.flock(lock, fcntl.LOCK_EX | fcntl.LOCK_NB)
        except BlockingIOError:
            raise RuntimeError("Another study coordinator is already running") from None
        try:
            yield
        finally:
            fcntl.flock(lock, fcntl.LOCK_UN)


def runtime_paths(config_file):
    config = json.loads(config_file.read_text(encoding="utf-8"))
    paths = {}
    for name in ("python_venv", "codex_bin_dir", "node_bin_dir", "vendor", "auth_file"):
        path = Path(config[name])
        if not path.is_absolute(): raise ValueError("Runtime path must be absolute: " + name)
        paths[name] = path.resolve(strict=True)
        if not (paths[name].is_file() if name == "auth_file" else paths[name].is_dir()):
            raise ValueError("Invalid runtime path: " + name)
    job_root = Path(config.get("job_root", PRIVATE / "jobs"))
    if not job_root.is_absolute(): raise ValueError("job_root must be absolute")
    paths["job_root"] = job_root.resolve()
    return paths


def redact(data, secrets):
    for secret in secrets:
        data = data.replace(secret.encode("utf-8"), b"[redacted]")
    return data


def collect_evidence(job, folder, secrets):
    """Copy local output without following links; raw job artifacts stay preserved."""
    redacted = []
    for source in sorted(job.rglob("*")):
        rel = source.relative_to(job)
        if rel.parts[0] not in ("output", "supervisor-stdout.txt", "supervisor-stderr.txt", "sandbox-config.json"):
            continue
        if rel.parts[:4] == ("output", "work", "result", "native"): continue
        if source.is_symlink(): raise ValueError("Unexpected evidence symlink: " + rel.as_posix())
        if not source.is_file(): continue
        name = rel.as_posix()
        if name.startswith("output/work/"): name = "output/" + name[len("output/work/"):]
        data = source.read_bytes()
        safe = redact(data, secrets)
        if safe != data: redacted.append(name)
        target = folder / name
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_bytes(safe)
    return redacted


def run(snapshot, check=False, synthetic=None, runtime_config=None):
    if sys.platform != "linux": raise RuntimeError("Native Linux is required; no WSL fallback")
    if runtime_config is None: raise ValueError("--runtime-config is required")
    runtime_config = Path(runtime_config).resolve(strict=True)
    runtime = runtime_paths(runtime_config)
    with schedule_lock():
        return run_locked(snapshot, runtime, runtime_config, check, synthetic)


def run_locked(snapshot, runtime, runtime_config, check, synthetic):
    prepare.verify(snapshot)
    for protected in (snapshot, PRIVATE / "executions", PRIVATE / "runtime-checks"):
        if runtime["job_root"] == protected or runtime["job_root"].is_relative_to(protected):
            raise ValueError("job_root must stay outside frozen snapshots and attempt evidence")
    if not check and not synthetic and not readiness(snapshot)["ready"]:
        raise RuntimeError("Preserved isolated compatibility checks are required before historical generation")
    chosen = next_step(snapshot)
    if chosen is None: return {"status": "all_monthly_jobs_completed"}
    pair, arm = chosen
    if synthetic: arm = synthetic
    name = step_name(pair, arm)
    if check or synthetic:
        from datetime import datetime, timezone
        name += ("-check-" if check else "-fixture-") + datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%S%f")
    auth = json.loads(runtime["auth_file"].read_text(encoding="utf-8"))
    if auth.get("auth_mode") != "chatgpt": raise ValueError("ChatGPT subscription login required")
    secrets = sorted({value for value in auth.get("tokens", {}).values() if isinstance(value, str) and value},
                     key=len, reverse=True)
    folder = PRIVATE / ("runtime-checks" if check or synthetic else "executions") / snapshot.name / name
    folder.mkdir(parents=True, exist_ok=False, mode=0o700)
    job = runtime["job_root"] / (name + "-" + snapshot.name)
    if job == folder or job.is_relative_to(folder) or folder.is_relative_to(job):
        raise ValueError("Job staging and attempt evidence must not overlap")
    job_exit, launcher, failed, job_created = None, None, False, False
    coordinator = {"returncode": 1, "job_exit": None, "redacted_files": []}
    try:
        prepare.write_json(folder / "attempt.json", {"snapshot_id": snapshot.name, "pair": pair,
            "arm": arm, "check_only": check, "synthetic": synthetic, "transport": "native-linux",
            "linux_job": str(job), "runtime_config_sha256": prepare.sha(runtime_config.read_bytes()),
            "snapshot_checksums_sha256": prepare.sha((snapshot / "checksums.json").read_bytes()),
            "runtime_lock_sha256": prepare.sha((snapshot / "preparation/runtime-lock.json").read_bytes()),
            "export_exclusions": ["output/result/native (preserved in linux_job; pinned compiler source)"]})
        job.mkdir(parents=True, exist_ok=False, mode=0o700)
        job_created = True
        blobs, config = job_inputs(snapshot, pair, arm)
        if synthetic == "openwiki": blobs, config = {}, {}
        if synthetic == "tesla":
            blobs.pop("posts.jsonl")
            blobs.update({"canon/rules.md": blobs["rules.md"], "canon/rules_mapping.md": blobs["rules_mapping.md"]})
            config = {}
        prior = None if synthetic else previous_result(snapshot, pair, arm)
        if prior:
            config["previous_checksums_sha256"] = prepare.sha((prior / "checksums.json").read_bytes())
            if arm == "tesla": config["previous"] = VIRTUAL + "/checkpoints/previous"
            shutil.copytree(prior, job / "previous")
            verify_evidence(job / "previous")
        inputs, workers, output = job / "inputs", job / "workers", job / "output"
        inputs.mkdir(); workers.mkdir(); output.mkdir()
        for name_, data in blobs.items():
            target = inputs / name_
            target.parent.mkdir(parents=True, exist_ok=True)
            target.write_bytes(data)
        prepare.write_json(inputs / "job-config.json", config)
        for source in (snapshot / "preparation").iterdir():
            if source.suffix in (".py", ".mjs", ".json"):
                if source.is_symlink(): raise ValueError("Frozen workers must not contain links")
                shutil.copyfile(source, workers / source.name)
        sandbox = {key: str(runtime[key]) for key in ("python_venv", "codex_bin_dir", "node_bin_dir", "vendor", "auth_file")}
        sandbox.update(workers=str(workers), inputs=str(inputs), output_parent=str(output),
            previous=str(job / "previous") if prior else None, arm=arm, synthetic=bool(synthetic),
            synthetic_native_archive="/inputs/tesla.tar", synthetic_canon_dir="/inputs/canon",
            worker_job_file="job-config.json",
            expected_runtime_lock=json.loads((snapshot / "preparation/runtime-lock.json").read_text(encoding="utf-8")),
            forbidden_paths=[str(snapshot), str(runtime["job_root"]), str(Path.home() / ".codex"),
                             str(PRIVATE / "working/user-reviewed-reference-v2")])
        prepare.write_json(job / "sandbox-config.json", sandbox)
        command = [sys.executable, str(workers / "job_sandbox.py"), str(job / "sandbox-config.json")]
        if check: command.append("--check-only")
        print(json.dumps({"event": "started", "linux_job": str(job), "check_only": check}), flush=True)
        with (job / "supervisor-stdout.txt").open("wb") as stdout, (job / "supervisor-stderr.txt").open("wb") as stderr:
            job_exit = subprocess.run(command, stdout=stdout, stderr=stderr).returncode
    except BaseException as error:
        failed = True
        message = redact(f"{type(error).__name__}: {error}\n".encode("utf-8"), secrets)
        (folder / "supervisor-error-redacted.txt").write_bytes(message)
        if isinstance(error, (KeyboardInterrupt, SystemExit)): raise
        raise RuntimeError(message.decode("utf-8").rstrip()) from None
    finally:
        try:
            coordinator["job_exit"] = job_exit
            coordinator["redacted_files"] = collect_evidence(job, folder, secrets) if job_created else []
            report = folder / "output/launcher-report.json"
            launcher = json.loads(report.read_text(encoding="utf-8")) if report.exists() else None
            if not failed and job_exit == 0 and launcher and launcher.get("returncode") == 0 and not coordinator["redacted_files"]:
                coordinator["returncode"] = 0
        except BaseException as error:
            message = redact(f"{type(error).__name__}: {error}\n".encode("utf-8"), secrets)
            (folder / "collection-error-redacted.txt").write_bytes(message)
            if isinstance(error, (KeyboardInterrupt, SystemExit)): raise
            raise RuntimeError(message.decode("utf-8").rstrip()) from None
        finally:
            prepare.write_json(folder / "coordinator-report.json", coordinator)
            result = folder / "output/result"
            if result.exists(): prepare.write_json(result / "checksums.json", files(result))
            prepare.write_json(folder / "checksums.json", files(folder))
            verify_evidence(folder)
    return {"folder": str(folder), "job_exit": job_exit,
            "coordinator_exit": coordinator["returncode"], "launcher": launcher}


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("snapshot", type=Path)
    parser.add_argument("--runtime-config", type=Path, required=True)
    parser.add_argument("--check-only", action="store_true")
    parser.add_argument("--synthetic", choices=("openwiki", "tesla"))
    args = parser.parse_args()
    result = run(args.snapshot.resolve(), args.check_only, args.synthetic, args.runtime_config)
    print(json.dumps(result, ensure_ascii=False), flush=True)
    if result.get("job_exit") or result.get("coordinator_exit") or (result.get("launcher") or {}).get("returncode", 0):
        raise SystemExit(1)
