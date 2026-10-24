"""Offline orchestration safeguards; subprocesses and Linux locking are mocked."""
from contextlib import nullcontext
import json
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest
from unittest.mock import patch

import prepare
import study_run


class StudyBoundaryTests(unittest.TestCase):
    def setUp(self):
        self.temp_parent = Path(__file__).resolve().parent / ".test-tmp"
        self.temp_parent.mkdir(exist_ok=True)
        self.temp = tempfile.TemporaryDirectory(prefix="yunost-orchestration-", dir=self.temp_parent)
        self.root = Path(self.temp.name)
        self.snapshot = self.root / "snapshots" / ("a" * 20)
        self.snapshot.mkdir(parents=True)
        self.pair = {"pair": 1, "repetition": 1, "batch": "2024-01", "order": ["openwiki", "tesla"]}
        prepare.write_json(self.snapshot / "allocation.json", [self.pair])

    def tearDown(self):
        self.temp.cleanup()
        try: self.temp_parent.rmdir()
        except OSError: pass

    def frozen_runtime(self):
        prepare.write_json(self.snapshot / "manifest.json", {"snapshot_id": self.snapshot.name, "source_records": 2})
        prepare.write_json(self.snapshot / "preparation/runtime-lock.json", {"frozen": "runtime"})
        (self.snapshot / "preparation/job_sandbox.py").write_text("# frozen launcher\n", encoding="utf-8")
        for month, text in (("2024-01", "CURRENT MONTH"), ("2024-02", "NEXT MONTH")):
            prepare.write_json(self.snapshot / f"prompts/openwiki-input/{month}.json", {"month": month})
            posts = self.snapshot / f"dataset/batches/{month}/posts.jsonl"
            posts.parent.mkdir(parents=True)
            posts.write_text(text + "\n", encoding="utf-8")
        prepare.write_json(self.snapshot / "annotations/gold-facts.json", {"gold": "MUST NOT BE STAGED"})
        prepare.write_json(self.snapshot / "checksums.json", study_run.files(self.snapshot))
        paths = {}
        for name in ("python_venv", "codex_bin_dir", "node_bin_dir", "vendor"):
            path = self.root / name
            path.mkdir()
            paths[name] = str(path)
        self.token = "offline-test-token-" + "x" * 64
        auth = self.root / "auth.json"
        prepare.write_json(auth, {"auth_mode": "chatgpt", "tokens": {"access_token": self.token}})
        paths["auth_file"] = str(auth)
        self.runtime_config = self.root / "runtime-config.json"
        prepare.write_json(self.runtime_config, paths)

    def record_completed(self, pair, arm):
        folder = self.root / "executions" / self.snapshot.name / study_run.step_name(pair, arm)
        prepare.write_json(folder / "output/result/report.json", {"status": "completed", "snapshot_id": self.snapshot.name,
            "arm": arm, "repetition": pair["repetition"], "month": pair["batch"]})
        (folder / "output/result/page.md").write_text(arm, encoding="utf-8")
        prepare.write_json(folder / "output/result/checksums.json", study_run.files(folder / "output/result"))
        prepare.write_json(folder / "output/launcher-report.json", {"returncode": 0})
        prepare.write_json(folder / "checksums.json", study_run.files(folder))
        return folder

    def invoke(self, launcher, **kwargs):
        with patch.object(study_run, "PRIVATE", self.root), patch.object(study_run.sys, "platform", "linux"), \
                patch.object(study_run, "schedule_lock", return_value=nullcontext()), \
                patch.object(study_run, "readiness", return_value={"ready": True}), \
                patch.object(study_run.subprocess, "run", side_effect=launcher) as launch:
            result = study_run.run(self.snapshot, runtime_config=self.runtime_config, **kwargs)
        self.assertEqual(launch.call_count, 1)
        return result

    def launcher(self, command, stdout, stderr, *, process_exit=0, launcher_exit=0, secret_log=False):
        self.assertEqual(command[0], sys.executable)
        self.assertEqual(Path(command[1]).name, "job_sandbox.py")
        self.assertNotIn("wsl", command)
        self.sandbox = json.loads(Path(command[2]).read_text(encoding="utf-8"))
        self.job = Path(command[2]).parent
        self.assertEqual(self.sandbox["expected_runtime_lock"], {"frozen": "runtime"})
        self.assertNotIn(self.token, Path(command[2]).read_text(encoding="utf-8"))
        self.assertEqual(Path(self.sandbox["workers"], "job_sandbox.py").read_text(encoding="utf-8"), "# frozen launcher\n")
        inputs = Path(self.sandbox["inputs"])
        self.config = json.loads((inputs / "job-config.json").read_text(encoding="utf-8"))
        expected_inputs = {"job-config.json"} if self.sandbox["synthetic"] else {"posts.jsonl", "task.json", "job-config.json"}
        self.assertEqual({p.name for p in inputs.iterdir()}, expected_inputs)
        output = Path(self.sandbox["output_parent"])
        self.assertEqual(list(output.iterdir()), [])
        prepare.write_json(output / "launcher-report.json", {"returncode": launcher_exit})
        if "--check-only" not in command:
            report = ({"status": "passed", "study_data_used": False} if self.sandbox["synthetic"] else
                      {"status": "completed", "snapshot_id": self.snapshot.name, "arm": self.sandbox["arm"],
                       "month": self.config["month"], "repetition": self.config["repetition"]})
            prepare.write_json(output / "work/result/report.json", report)
            page = output / "work/result/pages/wiki.md"
            page.parent.mkdir(parents=True)
            page.write_text("Preserved wiki\n", encoding="utf-8")
            native = output / "work/result/native/compiler.py"
            native.parent.mkdir()
            native.write_text("# pinned native source\n", encoding="utf-8")
        stdout.write(b"launcher stdout\n")
        stderr.write((self.token if secret_log else "launcher stderr").encode("utf-8"))
        return subprocess.CompletedProcess(command, process_exit)

    def test_native_job_uses_frozen_workers_and_seals_outputs(self):
        self.frozen_runtime()
        result = self.invoke(self.launcher)
        self.assertEqual(result["coordinator_exit"], 0)
        folder = Path(result["folder"])
        study_run.verify_evidence(folder)
        study_run.verify_evidence(folder / "output/result")
        self.assertTrue((folder / "output/result/pages/wiki.md").is_file())
        self.assertFalse((folder / "output/result/native").exists())
        self.assertTrue((self.job / "output/work/result/native/compiler.py").exists())
        with patch.object(study_run, "PRIVATE", self.root):
            self.assertEqual(study_run.next_step(self.snapshot), (self.pair, "tesla"))

    def test_failed_supervisor_cannot_pass_with_completed_worker_report(self):
        self.frozen_runtime()
        def failed(command, stdout, stderr):
            return self.launcher(command, stdout, stderr, process_exit=17)
        result = self.invoke(failed)
        self.assertEqual(result["coordinator_exit"], 1)
        study_run.verify_evidence(Path(result["folder"]))
        with patch.object(study_run, "PRIVATE", self.root):
            with self.assertRaisesRegex(RuntimeError, "unsuccessful attempt"):
                study_run.next_step(self.snapshot)

    def test_synthetic_job_never_stages_historical_posts_or_gold(self):
        self.frozen_runtime()
        result = self.invoke(self.launcher, synthetic="openwiki")
        self.assertEqual(result["coordinator_exit"], 0)
        self.assertEqual(set(p.name for p in (self.job / "inputs").iterdir()), {"job-config.json"})

    def test_secret_redaction_is_preserved_and_stops_schedule(self):
        self.frozen_runtime()
        def exposed(command, stdout, stderr):
            return self.launcher(command, stdout, stderr, secret_log=True)
        result = self.invoke(exposed)
        self.assertEqual(result["coordinator_exit"], 1)
        folder = Path(result["folder"])
        self.assertNotIn(self.token, (folder / "supervisor-stderr.txt").read_text(encoding="utf-8"))
        self.assertIn("[redacted]", (folder / "supervisor-stderr.txt").read_text(encoding="utf-8"))
        study_run.verify_evidence(folder)

    def test_only_current_month_is_selected_and_tampering_stops_staging(self):
        current = self.snapshot / "dataset/batches/2024-01/posts.jsonl"
        task = self.snapshot / "prompts/openwiki-input/2024-01.json"
        current.parent.mkdir(parents=True)
        task.parent.mkdir(parents=True)
        current.write_bytes(b"CURRENT MONTH\n")
        task.write_bytes(b"CURRENT TASK\n")
        future = self.snapshot / "dataset/batches/2024-02/posts.jsonl"
        future.parent.mkdir(parents=True)
        future.write_bytes(b"FUTURE MUST NOT BE STAGED\n")
        prepare.write_json(self.snapshot / "checksums.json", {
            p.relative_to(self.snapshot).as_posix(): prepare.sha(p.read_bytes()) for p in (current, task, future)})
        blobs, config = study_run.job_inputs(self.snapshot, self.pair, "openwiki")
        self.assertEqual(set(blobs), {"posts.jsonl", "task.json"})
        self.assertFalse(any(b"FUTURE" in x for x in blobs.values()))
        self.assertEqual(config["batch_sha256"], prepare.sha(current.read_bytes()))
        current.write_bytes(b"REPLACED\n")
        with self.assertRaisesRegex(ValueError, "Frozen input mismatch"):
            study_run.job_inputs(self.snapshot, self.pair, "openwiki")

    def test_unsuccessful_step_blocks_schedule_instead_of_being_replaced(self):
        folder = self.root / "executions" / self.snapshot.name / study_run.step_name(self.pair, "openwiki")
        prepare.write_json(folder / "output/result/report.json", {"status": "failed"})
        prepare.write_json(folder / "output/launcher-report.json", {"returncode": 1})
        prepare.write_json(folder / "checksums.json", study_run.files(folder))
        with patch.object(study_run, "PRIVATE", self.root):
            with self.assertRaisesRegex(RuntimeError, "unsuccessful attempt"):
                study_run.next_step(self.snapshot)

    def test_every_checkpoint_manifest_is_itself_protected(self):
        folder = self.root / "attempt"
        prepare.write_json(folder / "output/result/checksums.json", {"page.md": "original"})
        prepare.write_json(folder / "checksums.json", study_run.files(folder))
        study_run.verify_evidence(folder)
        prepare.write_json(folder / "output/result/checksums.json", {"page.md": "changed"})
        with self.assertRaisesRegex(ValueError, "evidence changed"):
            study_run.verify_evidence(folder)


if __name__ == "__main__": unittest.main()
