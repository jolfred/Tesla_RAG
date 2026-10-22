"""Read actual subscription quota and run a small Codex CLI compatibility check.

No API key, paid endpoint, study input or production import. The app-server
reader mirrors Tesla's existing RPC, using a queue because Windows selectors
cannot watch anonymous pipes. Missing quota always blocks generation.
"""
from __future__ import annotations

import argparse
from datetime import datetime, timezone
import json
from pathlib import Path
import queue
import shutil
import subprocess
import tempfile
import threading
import time


MODEL = "gpt-6-luna"
EFFORT = "medium"


def read_limits(timeout=35):
    binary = shutil.which("codex")
    if not binary:
        raise RuntimeError("Codex CLI is unavailable")
    proc = subprocess.Popen([binary, "app-server", "--listen", "stdio://"],
        stdin=subprocess.PIPE, stdout=subprocess.PIPE, stderr=subprocess.DEVNULL,
        encoding="utf-8", bufsize=1)
    lines = queue.Queue()

    def drain():
        for line in proc.stdout:
            lines.put(line)
        lines.put(None)

    threading.Thread(target=drain, daemon=True).start()
    deadline = time.monotonic() + timeout

    def send(value):
        proc.stdin.write(json.dumps(value) + "\n")
        proc.stdin.flush()

    def receive(rid):
        while True:
            remaining = deadline - time.monotonic()
            if remaining <= 0:
                raise TimeoutError("Subscription quota check timed out")
            try:
                line = lines.get(timeout=remaining)
            except queue.Empty:
                raise TimeoutError("Subscription quota check timed out") from None
            if line is None:
                raise RuntimeError("Codex app-server closed before returning quota")
            value = json.loads(line)
            if value.get("id") == rid:
                if "error" in value:
                    raise RuntimeError("Codex quota RPC failed")
                return value["result"]

    try:
        send({"id": 1, "method": "initialize", "params": {
            "clientInfo": {"name": "tesla-yunost-research", "version": "2.0"}}})
        receive(1)
        send({"method": "initialized"})
        send({"id": 2, "method": "account/rateLimits/read", "params": {
            "excludeResetCreditDetails": True}})
        result = receive(2)
        limits = result.get("rateLimitsByLimitId", {}).get("codex") or result.get("rateLimits", {})
        safe = {}
        for window in ("primary", "secondary"):
            used = (limits.get(window) or {}).get("usedPercent")
            if isinstance(used, bool) or not isinstance(used, (int, float)) or not 0 <= used <= 100:
                raise RuntimeError(f"Actual {window} quota is unavailable")
            safe[window + "_used_percent"] = used
        safe["checked_at_utc"] = datetime.now(timezone.utc).isoformat()
        safe["eligible"] = all(safe[w + "_used_percent"] < 90 for w in ("primary", "secondary"))
        return safe
    finally:
        proc.terminate()
        try:
            proc.wait(timeout=3)
        except subprocess.TimeoutExpired:
            proc.kill()
            proc.wait(timeout=3)
        proc.stdin.close()
        proc.stdout.close()


def require_quota():
    limits = read_limits()
    if not limits["eligible"]:
        raise RuntimeError("Codex quota remaining is 10 percent or less")
    return limits


def compatibility_check(output: Path):
    output = output.resolve()
    root = Path(__file__).resolve().parents[3]
    private = (root / "storage/experiments/yunost-2024").resolve()
    if not output.is_relative_to(private) or output == private:
        raise ValueError("Use a new private study directory")
    output.mkdir(parents=True, exist_ok=False)
    limits = require_quota()
    (output / "quota-before.json").write_text(json.dumps(limits, indent=2), encoding="utf-8")
    schema = {"type": "object", "properties": {"marker": {"type": "string"}},
              "required": ["marker"], "additionalProperties": False}
    schema_path = output / "schema.json"
    schema_path.write_text(json.dumps(schema), encoding="utf-8")
    prompt = 'Return the JSON object {"marker":"synthetic-subscription-check"}. Do not use tools.'
    (output / "input.txt").write_text(prompt, encoding="utf-8")
    command = [shutil.which("codex"), "exec", "--ephemeral", "--ignore-user-config", "--ignore-rules",
        "--sandbox", "read-only", "--skip-git-repo-check", "--json", "-m", MODEL,
        "-c", f'model_reasoning_effort="{EFFORT}"', "--output-schema", str(schema_path),
        "-o", str(output / "answer.json"), "-"]
    started = time.monotonic()
    with tempfile.TemporaryDirectory(prefix="yunost-subscription-check-") as isolated:
        with (output / "events.jsonl").open("w", encoding="utf-8") as log:
            result = subprocess.run(command, input=prompt, encoding="utf-8", cwd=isolated,
                stdout=log, stderr=subprocess.STDOUT, timeout=180)
    answer = json.loads((output / "answer.json").read_text(encoding="utf-8")) if (output / "answer.json").exists() else None
    success = result.returncode == 0 and answer == {"marker": "synthetic-subscription-check"}
    report = {"status": "passed" if success else "failed", "model": MODEL, "effort": EFFORT,
        "transport": "codex_cli_chatgpt_subscription", "study_data_used": False,
        "api_key_used": False, "exit_code": result.returncode, "command": command,
        "wall_seconds": time.monotonic() - started}
    (output / "report.json").write_text(json.dumps(report, indent=2), encoding="utf-8")
    print(json.dumps(report))
    return 0 if success else 1


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--check", type=Path, help="Run one synthetic CLI generation in this new directory")
    args = parser.parse_args()
    if args.check:
        raise SystemExit(compatibility_check(args.check))
    print(json.dumps(read_limits()))
