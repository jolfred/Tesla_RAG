"""Linux bwrap transport isolation; native ingestion and prompts stay unchanged.

Run: job_sandbox.py CONFIG.json [--check-only]. No fallback outside bwrap.
Host config paths: workers, inputs, output_parent (existing empty directory),
auth_file, python_venv, codex_bin_dir, vendor; optional previous and synthetic.
worker_job_file is an inputs filename or /inputs/ path (default job-config.json).
Results: output_parent/work/result; launcher logs remain outside the sandbox.
Runtime lock: node_version, codex_version, codex_sha256,
openwiki_pnpm_lock_sha256, openwiki_dist_tree_sha256, openwiki_patched_sources.
Tree hash is SHA256 of UTF-8 JSON {dist-relative POSIX filename: SHA256},
sort_keys=True, separators=(',', ':'), ensure_ascii=True, with no newline.
"""
import argparse
import hashlib
import json
import os
from pathlib import Path
import shutil
import subprocess
import sys

WORKERS = "/study/experiments/wiki-quality/yunost-2024"
PRIVATE = "/study/storage/experiments/yunost-2024"
OUTPUT = PRIVATE + "/working/result"
PREVIOUS = PRIVATE + "/checkpoints/previous"
PYTHON = "/runtime-python/bin/python"


CLI_SHIM = r'''#!/runtime-python/bin/python
"""Hide the native source tree from Codex; only stdin/schema/output cross over."""
import json, os
from pathlib import Path
import shutil, subprocess, sys, tempfile

def namespace(schema, output):
    cmd = ['bwrap', '--ro-bind', '/', '/', '--unshare-all', '--share-net',
           '--die-with-parent', '--new-session']
    for directory in ('/inputs', '/study', '/vendor', '/tmp', '/home', '/codex-home'):
        cmd += ['--tmpfs', directory]
    cmd += ['--proc', '/proc', '--dev', '/dev', '--dir', '/home/research',
            '--dir', '/tmp/cli-input', '--dir', '/tmp/workspace',
            '--ro-bind', '/codex-home/auth.json', '/codex-home/auth.json',
            '--ro-bind', str(schema), '/tmp/cli-input/schema.json',
            '--bind', str(output), '/tmp/cli-output', '--chdir', '/tmp/workspace',
            '--setenv', 'HOME', '/home/research', '--setenv', 'CODEX_HOME', '/codex-home',
            '--setenv', 'PATH', '/codex-native:/usr/local/bin:/usr/bin:/bin']
    return cmd

def isolation_check():
    with tempfile.TemporaryDirectory(prefix='tesla-cli-probe-') as temp:
        temp = Path(temp)
        schema = temp / 'schema.json'; schema.write_text('{}')
        output = temp / 'output'; output.mkdir()
        # This is the same mount builder as exec; it never starts Codex.
        probe = r"""import json,os,pathlib,sys
from pathlib import Path
for name in ('/inputs','/study','/vendor','/home'):
    expected=['research'] if name=='/home' else []
    assert sorted(os.listdir(name))==expected, name
for name in sys.argv[1:]:assert not os.path.lexists(name), name
assert sorted(os.listdir('/codex-home'))==['auth.json']
assert sorted(os.listdir('/tmp/cli-input'))==['schema.json']
assert Path('/tmp/cli-input/schema.json').read_text()=='{}'
try:Path('/tmp/cli-input/schema.json').write_text('changed')
except OSError as e:assert e.errno in (13,30)
else:raise AssertionError('Schema was writable')
assert not any(Path('/tmp/workspace').iterdir())
assert not any(Path('/tmp/cli-output').iterdir())
p=Path('/tmp/cli-output/probe');p.write_text('ok');p.unlink()
print(json.dumps({'status':'passed','model_calls':0,'cli_input_only_namespace':True}))
"""
        subprocess.run(namespace(schema, output) + ['/runtime-python/bin/python', '-c', probe,
            str(temp), __file__, '/study/storage/experiments/yunost-2024/working/result/native',
            '/inputs/tesla.tar'], check=True)

args = sys.argv[1:]
if args == ['--check-cli-isolation']:
    isolation_check()
    raise SystemExit(0)
if not args or args[0] != 'exec':
    os.execv('/codex-native/codex', ['codex'] + args)

def argument(name):
    if args.count(name) != 1:raise ValueError('Expected one ' + name)
    i=args.index(name)
    if i+1 >= len(args):raise ValueError('Missing value for ' + name)
    return i+1

schema_index, output_index = argument('--output-schema'), argument('-o')
schema = Path(args[schema_index]).resolve(strict=True)
destination = Path(args[output_index]).absolute()
if not destination.is_relative_to('/study/storage/experiments/yunost-2024/working'):
    raise ValueError('Codex output must stay inside this study attempt')
args[schema_index]='/tmp/cli-input/schema.json'
args[output_index]='/tmp/cli-output/result.json'
extra = [flag for flag in ('--ignore-user-config', '--ignore-rules') if flag not in args]
args[1:1]=extra+['-c','web_search="disabled"']
with tempfile.TemporaryDirectory(prefix='tesla-cli-output-') as temp:
    process=subprocess.run(namespace(schema, Path(temp))+['/codex-native/codex']+args)
    result=Path(temp)/'result.json'
    if result.is_file():shutil.copyfile(result,destination)
    raise SystemExit(process.returncode)
'''


def sha(file):
    return hashlib.sha256(file.read_bytes()).hexdigest()


def write_json(file, value):
    file.write_text(json.dumps(value, indent=2, ensure_ascii=True) + "\n", encoding="utf-8")


def internal_check(config):
    """Executed inside the same namespace as the worker; never calls a model."""
    import dotenv  # noqa: F401 -- verify the actual isolated Python dependency
    import sqlite3
    sqlite3.connect(":memory:").execute("select 1").fetchone()
    lock = config["expected_runtime_lock"]
    assert subprocess.check_output(["node", "--version"], text=True).strip() == lock["node_version"]
    assert subprocess.check_output(["/codex-native/codex", "--version"], text=True).strip() == lock["codex_version"]
    assert sha(Path("/codex-native/codex")) == lock["codex_sha256"]
    assert sha(Path("/vendor/pnpm-lock.yaml")) == lock["openwiki_pnpm_lock_sha256"]
    tree = {}
    for file in sorted(Path("/vendor/dist").rglob("*")):
        assert not file.is_symlink(), "OpenWiki dist must not contain links"
        if file.is_file():
            tree[file.relative_to("/vendor/dist").as_posix()] = sha(file)
    assert tree, "Missing OpenWiki dist"
    tree_hash = hashlib.sha256(json.dumps(tree, sort_keys=True, separators=(",", ":"),
                                        ensure_ascii=True).encode("utf-8")).hexdigest()
    assert tree_hash == lock["openwiki_dist_tree_sha256"]
    for name, expected in lock["openwiki_patched_sources"].items():
        relative = Path(name)
        assert not relative.is_absolute() and ".." not in relative.parts and relative.parts[0] == "src"
        assert sha(Path("/vendor") / relative) == expected, "Patched source changed"
    node_check = """import assert from 'node:assert/strict';
import Database from '/vendor/node_modules/better-sqlite3/lib/index.js';
import {resolveReasoningConfig} from '/vendor/dist/config/reasoning.js';
const db = new Database(':memory:'); assert.equal(db.prepare('select 1 as n').get().n,1); db.close();
assert.deepEqual(resolveReasoningConfig('openai-chatgpt','gpt-6-luna'),
 {effort:'medium',transport:'responses-reasoning'});"""
    subprocess.run(["node", "--input-type=module", "-e", node_check], check=True)
    subprocess.run(["codex", "--check-cli-isolation"], check=True, stdout=subprocess.DEVNULL)
    for name in config.get("forbidden_paths", []):
        assert Path(name).is_absolute(), "forbidden_paths must be absolute namespace paths"
        assert not os.path.lexists(name), "Forbidden path is visible: " + name
    for directory in ("/inputs", WORKERS, "/vendor"):
        probe = Path(directory) / ".sandbox-readonly-probe"
        try:
            probe.write_text("probe", encoding="utf-8")
        except OSError as error:
            assert error.errno in (13, 30), "Unexpected readonly-probe error"
        else:
            probe.unlink()
            raise RuntimeError("Expected a read-only mount: " + directory)
    for directory in (PRIVATE + "/working", "/tmp"):
        probe = Path(directory) / ".sandbox-write-probe"
        probe.write_text("probe", encoding="utf-8")
        probe.unlink()
    assert not Path(OUTPUT).exists(), "Worker output must start absent"
    result = {"status": "passed", "model_calls": 0, "runtime_lock_verified": True,
              "cli_input_only_namespace_verified": True,
              "read_only_mounts_verified": True, "forbidden_paths_checked": config.get("forbidden_paths", [])}
    print(json.dumps(result, ensure_ascii=True))


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("config", type=Path)
    parser.add_argument("--check-only", action="store_true")
    parser.add_argument("--internal-check", action="store_true", help=argparse.SUPPRESS)
    args = parser.parse_args()
    if sys.platform != "linux":
        raise RuntimeError("This launcher requires Linux and bwrap")
    config = json.loads(args.config.read_text(encoding="utf-8"))
    if args.internal_check:
        internal_check(config)
        return
    bwrap = shutil.which("bwrap")
    if not bwrap:
        raise RuntimeError("bwrap is required; no unsandboxed fallback")
    if config["arm"] not in ("tesla", "openwiki"):
        raise ValueError("arm must be tesla or openwiki")
    if not isinstance(config.get("synthetic", False), bool):
        raise ValueError("synthetic must be a boolean")
    job_file = Path(config.get("worker_job_file", "job-config.json"))
    if not job_file.is_absolute():
        job_file = Path("/inputs") / job_file
    if not job_file.is_relative_to("/inputs") or ".." in job_file.parts:
        raise ValueError("worker_job_file must stay inside /inputs")
    paths = {name: Path(config[name]).resolve(strict=True) for name in
             ("workers", "inputs", "output_parent", "auth_file", "python_venv", "codex_bin_dir", "vendor")}
    output = paths["output_parent"]
    if not output.is_dir() or any(output.iterdir()):
        raise ValueError("output_parent must be an existing empty directory")
    if any(output == p or output.is_relative_to(p) or p.is_relative_to(output)
           for name, p in paths.items() if name != "output_parent"):
        raise ValueError("Output and read-only runtime/input paths must not overlap")
    if not paths["auth_file"].is_file():
        raise ValueError("auth_file must contain only the Codex login JSON")
    support = paths["inputs"] / ".sandbox-support"
    support.mkdir(exist_ok=False)
    (support / "shim").mkdir()
    shim = support / "shim/codex"
    shim.write_text(CLI_SHIM, encoding="utf-8")
    shim.chmod(0o755)
    write_json(support / "check.json", {"expected_runtime_lock": config["expected_runtime_lock"],
                                      "forbidden_paths": config.get("forbidden_paths", [])})
    work = output / "work"
    work.mkdir()
    command = [bwrap, "--unshare-all", "--share-net", "--die-with-parent", "--new-session",
               "--clearenv", "--ro-bind", "/usr", "/usr"]
    for name in ("bin", "sbin", "lib", "lib64"):
        host = Path("/" + name)
        if host.is_symlink():
            command += ["--symlink", os.readlink(host), str(host)]
        elif host.exists():
            command += ["--ro-bind", str(host), str(host)]
    for name in ("/etc/resolv.conf", "/etc/hosts", "/etc/nsswitch.conf", "/etc/passwd",
                 "/etc/group", "/etc/ssl/certs", "/etc/ca-certificates.conf", "/etc/localtime"):
        if Path(name).exists():
            command += ["--ro-bind", name, name]
    command += ["--proc", "/proc", "--dev", "/dev", "--tmpfs", "/tmp", "--tmpfs", "/run",
                "--tmpfs", "/home", "--dir", "/home/research", "--tmpfs", "/codex-home"]
    for name, destination in (("workers", WORKERS), ("inputs", "/inputs"), ("vendor", "/vendor"),
                              ("python_venv", "/runtime-python"), ("codex_bin_dir", "/codex-native"),
                              ("auth_file", "/codex-home/auth.json")):
        command += ["--ro-bind", str(paths[name]), destination]
    if config.get("previous"):
        command += ["--ro-bind", str(Path(config["previous"]).resolve(strict=True)), PREVIOUS]
    command += ["--bind", str(work), PRIVATE + "/working", "--chdir", "/study",
                "--setenv", "HOME", "/home/research", "--setenv", "CODEX_HOME", "/codex-home",
                "--setenv", "PATH", "/inputs/.sandbox-support/shim:/codex-native:/usr/local/bin:/usr/bin:/bin",
                "--setenv", "PYTHONDONTWRITEBYTECODE", "1", "--setenv", "PYTHON_DOTENV_DISABLED", "1",
                "--setenv", "LANG", "C.UTF-8", "--setenv", "TZ", "Europe/Moscow"]
    logs = output / "launcher-logs"
    logs.mkdir()
    report = {"transport_isolation": "bwrap", "native_core_modified": False,
              "worker_exit": None, "check_exit": None, "returncode": 1, "check_only": args.check_only,
              "model_calls": 0 if args.check_only else None}
    try:
        with (logs / "check-stdout.txt").open("wb") as stdout, (logs / "check-stderr.txt").open("wb") as stderr:
            check = subprocess.run(command + [PYTHON, WORKERS + "/job_sandbox.py",
                                   "/inputs/.sandbox-support/check.json", "--internal-check"], stdout=stdout, stderr=stderr)
        report["check_exit"] = check.returncode
        report["returncode"] = check.returncode
        if check.returncode:
            write_json(output / "check.json", {"status": "failed", "returncode": check.returncode, "model_calls": 0})
            raise RuntimeError("Sandbox runtime check failed; see launcher-logs")
        write_json(output / "check.json", json.loads((logs / "check-stdout.txt").read_text(encoding="utf-8")))
        if not args.check_only:
            previous = [PREVIOUS] if config.get("previous") else []
            if config["arm"] == "openwiki":
                worker = ["node", WORKERS + "/openwiki_subscription_check.mjs", "/vendor", OUTPUT, PYTHON]
                if config.get("synthetic", False):
                    worker += previous
                else:
                    worker += previous or ["-"]
                    worker += [str(job_file)]
            elif config.get("synthetic", False):
                worker = [PYTHON, WORKERS + "/tesla_fixture.py", OUTPUT, "--subscription",
                          "--native-archive", config.get("synthetic_native_archive", "/inputs/tesla-native.tar"),
                          "--canon-dir", config.get("synthetic_canon_dir", "/inputs/canon")]
            else:
                worker = [PYTHON, WORKERS + "/tesla_run_month.py", str(job_file)]
            with (logs / "worker-stdout.txt").open("wb") as stdout, (logs / "worker-stderr.txt").open("wb") as stderr:
                report["worker_exit"] = subprocess.run(command + worker, stdout=stdout, stderr=stderr).returncode
                report["returncode"] = report["worker_exit"]
    finally:
        write_json(output / "launcher-report.json", report)
    if report["worker_exit"] not in (None, 0):
        raise SystemExit(report["worker_exit"])


if __name__ == "__main__":
    main()
