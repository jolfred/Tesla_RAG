"""Offline safeguards at the orchestration boundary; no model or WSL calls."""
import json
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

import prepare
import study_run


class StudyBoundaryTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory(prefix="yunost-orchestration-")
        self.root = Path(self.temp.name)
        self.snapshot = self.root / "snapshots" / ("a" * 20)
        self.snapshot.mkdir(parents=True)
        self.pair = {"pair": 1, "repetition": 1, "batch": "2024-01", "order": ["openwiki", "tesla"]}
        prepare.write_json(self.snapshot / "allocation.json", [self.pair])

    def tearDown(self): self.temp.cleanup()

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
