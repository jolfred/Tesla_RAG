"""Route the pinned native compiler straight to its existing Codex CLI path.

The research choice is Luna medium at BOTH stages, with no OpenCode/model
fallback and no extra retry. Linux native call_provider checks real quota
before every invocation and preserves JSON-schema validation and CLI logs.
"""
def make_provider(compiler):
    def call(native_effort, system_prompt, bundle_path, output_path, workdir,
             free_models, codex_fallback, agent, run_dir, validator=None):
        if tuple(free_models) != ("gpt-6-luna",) or codex_fallback:
            raise ValueError("Research requires one explicitly selected model, no fallback")
        record = {"provider": "codex", "model": "gpt-6-luna", "effort": "medium",
                  "native_effort_argument": native_effort, "status": "running"}
        compiler._provider_event(run_dir, record)
        try:
            result = compiler.call_provider("codex", "medium", system_prompt, bundle_path,
                output_path, workdir, model="gpt-6-luna", agent=agent)
            if validator is not None:
                validator(result)
            compiler._provider_event(run_dir, {**record, "status": "success"})
            return result
        except BaseException as exc:
            compiler._provider_event(run_dir, {**record, "status": "failed", "error_type": type(exc).__name__})
            raise
    return call
