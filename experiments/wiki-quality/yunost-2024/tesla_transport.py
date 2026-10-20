"""Research-only Responses transport for the existing Tesla compiler.

No CLI, credentials, automatic fallback or production imports. A caller supplies
an official SDK client (max_retries=0) after approving the study configuration.
Tests supply a fake client; importing this file cannot make a network request.
"""
from __future__ import annotations

import json
from pathlib import Path
import time
from uuid import uuid4


def make_provider(client, compiler, log_dir: Path, *, model: str = "gpt-6-luna",
                  effort: str = "medium", max_output_tokens: int = 16384):
    if model != "gpt-6-luna" or effort != "medium":
        raise ValueError("The user selected gpt-6-luna / medium; version the protocol before changing it")
    if getattr(client, "max_retries", None) != 0:
        raise ValueError("Research client must disable automatic retries")
    if max_output_tokens < 1:
        raise ValueError("max_output_tokens must be positive")
    log_dir.mkdir(parents=True, exist_ok=True)
    sequence = 0

    def write(path, value):
        path.write_text(json.dumps(value, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")

    def call(effort_from_native, system_prompt, bundle_path, output_path,
             workdir, free_models, codex_fallback, agent, run_dir, validator=None):
        nonlocal sequence
        if codex_fallback or tuple(free_models) != (model,):
            raise ValueError("Research transport forbids model switching and CLI fallback")
        prompt = Path(system_prompt).read_text(encoding="utf-8")
        compiler._validate_canonical_prompt(prompt)
        stage = "extract" if "extract" in Path(system_prompt).name else "merge"
        # This wrapper is copied verbatim from native call_provider('codex').
        user = "Return only the JSON object required by the system instructions.\n\nINPUT BUNDLE:\n" + Path(bundle_path).read_text(encoding="utf-8")
        request = {"model": model, "reasoning": {"effort": effort},
                   "instructions": prompt, "input": user, "store": False,
                   "max_output_tokens": max_output_tokens,
                   "text": {"format": {"type": "json_schema", "name": stage,
                                        "strict": True, "schema": compiler._output_schema(stage)}}}
        sequence += 1
        record = log_dir / f"{sequence:04d}-{stage}-{uuid4().hex}"
        record.mkdir(exist_ok=False)
        write(record / "request.json", request)
        started = time.monotonic()
        try:
            response = client.responses.create(**request)
            write(record / "response.json", response.model_dump(mode="json"))
            if response.status != "completed":
                raise ValueError("Response incomplete or failed; retained as a failed attempt")
            result = compiler._json_object(response.output_text)
            if validator is not None:
                validator(result)
            Path(output_path).parent.mkdir(parents=True, exist_ok=True)
            write(Path(output_path), result)
            write(record / "status.json", {"status": "accepted", "wall_seconds": time.monotonic() - started,
                                           "native_effort_argument": effort_from_native,
                                           "actual_effort": effort, "stage": stage})
            return result
        except BaseException as exc:
            # Error strings can contain headers/credentials in some SDKs.
            # Save only class/status here; raw successful response is already retained.
            write(record / "status.json", {"status": "failed", "error_type": type(exc).__name__,
                                           "http_status": getattr(exc, "status_code", None),
                                           "wall_seconds": time.monotonic() - started})
            raise

    return call
