"""Run the official OpenCode client with only approved compilation inputs mounted."""
from __future__ import annotations

import json
import os
import shutil
from pathlib import Path


def opencode_command(work: Path, model: str, agent: str, effort: str = "low") -> list[str]:
    sandbox = shutil.which("bwrap")
    client = shutil.which("opencode")
    if not sandbox or not client:
        raise RuntimeError("isolated OpenCode compilation requires bubblewrap and OpenCode CLI")
    root = Path(__file__).resolve().parents[2]
    state = root / ".opencode/cache/compiler-cli"
    for folder in ("home", "config", "cache", "data", "mcp", "mcp/runtime"):
        (state / folder).mkdir(parents=True, exist_ok=True)
    home = os.environ.get("HOME", "/home/jolf")
    config: dict = {"$schema":"https://opencode.ai/config.json"}
    # MiMo and LongCat document a thinking switch, not a hard Low budget.
    # Use nonthinking mode for extraction and validated text-patch drafts.
    if effort in {"low", "medium"} and model in {"opencode/mimo-v2.6-flash-free", "opencode/longcat-2.5-preview-free"}:
        config["provider"] = {"opencode": {"models": {
            model.split("/", 1)[1]: {"options": {"thinking": {"type": "disabled"}}}
        }}}
    memory = root / ".opencode/bin/codebase-memory-mcp"
    if memory.is_file():
        config["mcp"] = {"codebase-memory-mcp": {
            "type":"local", "command":["/app/codebase-memory-mcp", "--tool-profile=analysis"],
            "env":{"CBM_CACHE_DIR":"/state/mcp", "CBM_RUNTIME_DIR":"/state/mcp/runtime"},
            "enabled":True,
        }}
    (work / "opencode.json").write_text(json.dumps(config), encoding="utf-8")
    cmd = [sandbox, "--die-with-parent", "--unshare-pid", "--clearenv"]
    for path in ("/usr", "/bin", "/lib", "/lib64", "/etc/resolv.conf", "/etc/ssl/certs"):
        if Path(path).exists():
            cmd.extend(["--ro-bind", path, path])
    cmd.extend(["--proc","/proc", "--dev","/dev", "--dir","/app",
                "--ro-bind",client,"/app/opencode", "--bind",str(state),"/state",
                "--bind",str(state / "home"),home, "--bind",str(work),"/work", "--dir","/tmp"])
    if memory.is_file():
        cmd.extend(["--ro-bind",str(memory),"/app/codebase-memory-mcp"])
    environment = {"HOME":home, "PATH":"/app:/usr/bin:/bin", "XDG_CONFIG_HOME":"/state/config",
                   "XDG_CACHE_HOME":"/state/cache", "XDG_DATA_HOME":"/state/data",
                   "OPENCODE_CONFIG":"/work/opencode.json"}
    for key, value in environment.items():
        cmd.extend(["--setenv",key,value])
    cmd.extend(["--chdir","/work", "/app/opencode","run",
                "Follow the attached system prompt and return only its requested JSON object. Use the attached input bundle as the complete context. No tools are needed.",
                "--format","json", "--agent",agent, "--model",model, "--dir","/work",
                "--file","/work/stage-instructions.md", "--file","/work/input-bundle.json"])
    # The current official catalog exposes Low/Medium variants for LongCat.
    # MiMo and Nemotron expose no variants: do not pretend they honor effort.
    if model in {"opencode/longcat-2.5-preview-free", "opencode/muse-spark-1.3-contributor-free", "opencode/ling-3.1-flash-free"}:
        if effort not in {"low", "medium", "high"}:
            raise ValueError("unsupported LongCat reasoning effort")
        cmd.extend(["--variant", effort])
    return cmd
