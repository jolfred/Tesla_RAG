"""Invoke one frozen monthly job, with bwrap and append-only attempt evidence.

This orchestration adapter never changes ingestion, scores answers or supplies
reference facts to either method. Windows holds the complete private snapshot;
Linux receives only the selected month and this arm/repetition's checkpoint.
"""
import argparse
import base64
import io
import json
from pathlib import Path
import subprocess
import sys
import zipfile

import prepare

PRIVATE = prepare.ROOT / "storage/experiments/yunost-2024"
LINUX = "/home/opencode/tesla-research/yunost-2024-shared"
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


def next_step(snapshot):
    run_root = PRIVATE / "executions" / snapshot.name
    for pair, arm in steps(snapshot):
        folder = run_root / step_name(pair, arm)
        if not folder.exists(): return pair, arm
        verify_evidence(folder)
        report_path = folder / "output/result/report.json"
        report = json.loads(report_path.read_text(encoding="utf-8")) if report_path.exists() else {}
        launch = json.loads((folder / "output/launcher-report.json").read_text(encoding="utf-8"))
        if (report.get("status") != "completed" or launch.get("returncode") != 0
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


# Executed only in the isolated Linux research area. No credential is printed.
REMOTE = r'''
import base64,io,json,os,pathlib,subprocess,sys,zipfile
d=json.load(sys.stdin)
base=pathlib.Path('/home/opencode/tesla-research/yunost-2024-shared')
job=base/'jobs'/d['name']
job.mkdir(parents=True,exist_ok=False)
with zipfile.ZipFile(io.BytesIO(base64.b64decode(d['zip']))) as z:
    for n in z.namelist():
        assert not n.startswith('/') and '..' not in pathlib.PurePosixPath(n).parts
    z.extractall(job)
auth=base/'private-codex-home/auth.json'
auth.parent.mkdir(mode=0o700,exist_ok=True)
fd=os.open(auth,os.O_CREAT|os.O_TRUNC|os.O_WRONLY,0o600)
with os.fdopen(fd,'w') as f: json.dump(d['auth'],f)
out=job/'output'; out.mkdir()
cfg={'workers':str(job/'workers'),'inputs':str(job/'inputs'),'output_parent':str(out),
     'previous':str(job/'previous') if (job/'previous').exists() else None,
     'auth_file':str(auth),
     'python_venv':'/mnt/c/Users/Alfred/Projects/Tesla_RAG/storage/experiments/yunost-2024/runtime-linux',
     'codex_bin_dir':'/home/opencode/tesla-research/yunost-2024-subscription-fixture/codex-complete/package/vendor/x86_64-unknown-linux-musl/bin',
     'vendor':str(base/'vendor/openwiki'),'arm':d['arm'],'synthetic':d['synthetic'],
     'synthetic_native_archive':'/inputs/tesla.tar','synthetic_canon_dir':'/inputs/canon',
     'worker_job_file':'job-config.json','expected_runtime_lock':d['runtime_lock'],
     'forbidden_paths':[str(base/'storage'),str(base/'jobs'),'/home/opencode/.codex',
         '/mnt/c/Users/Alfred/Projects/Tesla_RAG/storage/experiments/yunost-2024/working/user-reviewed-reference-v2']}
(job/'sandbox-config.json').write_text(json.dumps(cfg))
cmd=['python3',str(job/'workers/job_sandbox.py'),str(job/'sandbox-config.json')]
if d['check']: cmd.append('--check-only')
with open(job/'supervisor-stdout.txt','w') as stdout,open(job/'supervisor-stderr.txt','w') as stderr:
    p=subprocess.Popen(cmd,stdout=stdout,stderr=stderr)
    print(json.dumps({'event':'started','linux_job':str(job),'check_only':d['check']}),flush=True)
    while True:
        try: p.wait(timeout=30);break
        except subprocess.TimeoutExpired:
            print(json.dumps({'event':'running','model_request_files':len(list(out.rglob('*-request.json'))),
                              'cli_logs':len(list(out.rglob('*.cli.log')))}),flush=True)
buffer=io.BytesIO()
with zipfile.ZipFile(buffer,'w',zipfile.ZIP_DEFLATED) as z:
    for path in sorted(job.rglob('*')):
        rel=path.relative_to(job)
        if rel.parts[0] not in ('output','supervisor-stdout.txt','supervisor-stderr.txt'):continue
        if rel.parts[:4]==('output','work','result','native'):continue
        assert not path.is_symlink(),'Unexpected evidence symlink'
        if path.is_file():
            name=rel.as_posix()
            if name.startswith('output/work/'):name='output/'+name[len('output/work/'):]
            content=path.read_bytes()
            for secret in d['auth'].get('tokens',{}).values():
                if isinstance(secret,str) and len(secret)>32:
                    assert secret.encode() not in content,'Credential found in output; export blocked'
            z.write(path,name)
print(json.dumps({'event':'export','zip':base64.b64encode(buffer.getvalue()).decode(),'returncode':p.returncode}),flush=True)
'''


def run(snapshot, check=False, synthetic=None):
    prepare.verify(snapshot)
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
    folder = PRIVATE / ("runtime-checks" if check or synthetic else "executions") / snapshot.name / name
    folder.mkdir(parents=True, exist_ok=False)
    blobs, cfg = job_inputs(snapshot, pair, arm)
    if synthetic == "openwiki": blobs, cfg = {}, {}
    if synthetic == "tesla":
        blobs.pop("posts.jsonl")
        blobs.update({"canon/rules.md": blobs["rules.md"], "canon/rules_mapping.md": blobs["rules_mapping.md"]})
        cfg = {}
    prior = None if synthetic else previous_result(snapshot, pair, arm)
    if prior:
        cfg["previous_checksums_sha256"] = prepare.sha((prior / "checksums.json").read_bytes())
        if arm == "tesla": cfg["previous"] = VIRTUAL + "/checkpoints/previous"
    buffer = io.BytesIO()
    with zipfile.ZipFile(buffer, "w", zipfile.ZIP_DEFLATED) as z:
        for name_, data in blobs.items(): z.writestr("inputs/" + name_, data)
        z.writestr("inputs/job-config.json", prepare.encoded(cfg))
        for p in (snapshot / "preparation").iterdir():
            if p.suffix in (".py", ".mjs", ".json"): z.write(p, "workers/" + p.name)
        if prior:
            for p in sorted(prior.rglob("*")):
                if p.is_file(): z.write(p, "previous/" + p.relative_to(prior).as_posix())
    auth = json.loads((Path.home() / ".codex/auth.json").read_text(encoding="utf-8"))
    if auth.get("auth_mode") != "chatgpt": raise ValueError("ChatGPT subscription login required")
    runtime_lock = json.loads((snapshot / "preparation/runtime-lock.json").read_text(encoding="utf-8"))
    payload = {"name": name + "-" + snapshot.name, "zip": base64.b64encode(buffer.getvalue()).decode(),
               "auth": {k:auth[k] for k in ("auth_mode", "tokens", "last_refresh") if k in auth},
               "arm": arm, "runtime_lock": runtime_lock, "check": check, "synthetic": bool(synthetic)}
    prepare.write_json(folder / "attempt.json", {"snapshot_id": snapshot.name, "pair": pair,
        "arm": arm, "check_only": check, "synthetic": synthetic,
        "linux_job": LINUX + "/jobs/" + payload["name"],
        "snapshot_checksums_sha256": prepare.sha((snapshot / "checksums.json").read_bytes()),
        "runtime_lock_sha256": prepare.sha((snapshot / "preparation/runtime-lock.json").read_bytes()),
        "export_exclusions": ["output/result/native (reconstructable pinned compiler source)"]})
    process = subprocess.Popen(["wsl", "-d", "Ubuntu", "--", "python3", "-c", REMOTE],
        stdin=subprocess.PIPE, stdout=subprocess.PIPE, stderr=subprocess.PIPE, encoding="utf-8")
    process.stdin.write(json.dumps(payload)); process.stdin.close()
    exported = False
    for line in process.stdout:
        event = json.loads(line)
        if event["event"] == "export":
            with zipfile.ZipFile(io.BytesIO(base64.b64decode(event["zip"]))) as z:
                for n in z.namelist():
                    if not (folder / n).resolve().is_relative_to(folder.resolve()): raise ValueError("Unsafe export path")
                z.extractall(folder)
            exported = True
        else: print(json.dumps(event), flush=True)
    stderr = process.stderr.read(); code = process.wait()
    if code or not exported:
        for secret in auth.get("tokens", {}).values():
            if isinstance(secret, str): stderr = stderr.replace(secret, "[redacted]")
        (folder / "supervisor-error-redacted.txt").write_text(stderr[-10000:], encoding="utf-8")
    result = folder / "output/result"
    if result.exists(): prepare.write_json(result / "checksums.json", files(result))
    prepare.write_json(folder / "checksums.json", files(folder))
    verify_evidence(folder)
    report = folder / "output/launcher-report.json"
    return {"folder": str(folder), "transport_exit": code,
            "launcher": json.loads(report.read_text(encoding="utf-8")) if report.exists() else None}


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("snapshot", type=Path)
    parser.add_argument("--check-only", action="store_true")
    parser.add_argument("--synthetic", choices=("openwiki", "tesla"))
    args = parser.parse_args()
    result = run(args.snapshot.resolve(), args.check_only, args.synthetic)
    print(json.dumps(result, ensure_ascii=False), flush=True)
    if result.get("transport_exit") or (result.get("launcher") or {}).get("returncode", 0):
        raise SystemExit(1)
