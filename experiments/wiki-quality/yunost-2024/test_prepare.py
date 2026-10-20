"""Offline checks of corpus selection, provenance and transport contracts."""
import hashlib
from contextlib import closing
import json
from pathlib import Path
import sqlite3
import tempfile
import types
import unittest

import prepare
from tesla_transport import make_provider


class PreparationTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory(prefix="yunost-study-test-")
        self.root = Path(self.tmp.name)
        self.config = {"source_domain": "spoyunost2020", "group_id": "198864697", "publication_year": 2024}

    def tearDown(self):
        self.tmp.cleanup()

    def row(self, pid="1", date="2024-03-01T00:00:00Z", text="Exact synthetic evidence"):
        return dict(group_domain="spoyunost2020", group_id="198864697", group_name="Synthetic group",
                    post_id=pid, post_url=f"https://vk.com/wall-198864697_{pid}", published_at=date,
                    text_raw=text, text_clean="DIFFERENT CLEANED TEXT", attachments={"photos": ["excluded"]})

    def source(self, rows):
        p = self.root / "source.jsonl"
        p.write_text("".join(json.dumps(x) + "\n" for x in rows), encoding="utf-8")
        return p

    def test_moscow_boundaries_and_order(self):
        rows, _, excluded = prepare.select_records(self.source([
            self.row("3", "2024-12-31T21:00:00Z"), self.row("2", "2024-12-31T20:59:59Z"),
            self.row("1", "2023-12-31T21:00:00Z"), self.row("4", "2023-12-31T20:59:59Z")]), self.config)
        self.assertEqual([r["record"]["post_id"] for r in rows], ["wall-198864697_1", "wall-198864697_2"])
        self.assertEqual(len(excluded["outside_year"]), 2)
        self.assertEqual([r["batch"] for r in rows], ["2024-01", "2024-12"])

    def test_verbatim_text_and_no_attachment_content(self):
        text = "Синтетика\n  exact spacing 🧪"
        rows, _, _ = prepare.select_records(self.source([self.row(text=text)]), self.config)
        r = rows[0]["record"]
        self.assertEqual(r["text_raw"], text)
        self.assertEqual(r["text_clean"], text)
        self.assertEqual(r["source_hash"], hashlib.sha256(text.encode()).hexdigest())
        self.assertNotIn("attachments", r)

    def test_identical_duplicates_and_conflicting_edits(self):
        r = self.row()
        selected, _, excluded = prepare.select_records(self.source([r, r]), self.config)
        self.assertEqual(len(selected), 1)
        self.assertEqual(excluded["identical_duplicate_lines"], [2])
        with self.assertRaisesRegex(ValueError, "different exported versions"):
            prepare.select_records(self.source([r, self.row(text="changed")]), self.config)

    def test_wrong_identity_and_naive_timestamp_fail(self):
        wrong = self.row(); wrong["group_domain"] = "spoyunost"
        with self.assertRaises(ValueError):
            prepare.select_records(self.source([wrong]), self.config)
        with self.assertRaises(ValueError):
            prepare.select_records(self.source([self.row(date="2024-01-01T00:00:00")]), self.config)

    def test_balanced_order_and_chronological_replicates(self):
        months = [f"2024-{x:02d}" for x in range(1, 13)]
        a = prepare.allocation(months, 5, 20241020)
        self.assertEqual(a, prepare.allocation(months, 5, 20241020))
        self.assertEqual(sum(x["order"][0] == "tesla" for x in a), 30)
        for rep in range(1, 6):
            self.assertEqual([x["batch"] for x in a if x["repetition"] == rep], months)

    def test_snapshot_tamper_and_extra_file_fail(self):
        prepare.write_json(self.root / "manifest.json", {"snapshot_id": "test", "source_records": 1})
        sums = {"manifest.json": prepare.sha((self.root / "manifest.json").read_bytes())}
        prepare.write_json(self.root / "checksums.json", sums)
        self.assertEqual(prepare.verify(self.root)["checked_files"], 1)
        (self.root / "future.txt").write_text("not in snapshot")
        with self.assertRaises(ValueError): prepare.verify(self.root)
        (self.root / "future.txt").unlink()
        (self.root / "manifest.json").write_text("changed")
        with self.assertRaises(ValueError): prepare.verify(self.root)

    def test_prompt_composition_and_registry_is_read_only(self):
        (self.root / "schema/prompts").mkdir(parents=True)
        (self.root / ".opencode/skills/wiki-editorial").mkdir(parents=True)
        (self.root / "storage").mkdir()
        for name in ("rules.md", "rules_mapping.md"):
            (self.root / "schema" / name).write_text("CANON " + name, encoding="utf-8")
        for name in prepare.PROMPTS.values():
            (self.root / "schema/prompts" / name).write_text("DEFAULT\n" + prepare.MARKER + "\nSTALE", encoding="utf-8")
        (self.root / ".opencode/skills/wiki-editorial/SKILL.md").write_text("EXISTING SKILL", encoding="utf-8")
        db = self.root / "storage/admin.db"
        with closing(sqlite3.connect(db)) as c:
            c.execute("CREATE TABLE prompts(key TEXT,text TEXT,updated_at TEXT)")
            c.execute("INSERT INTO prompts VALUES('wiki_extract','OVERRIDE','2026-10-20')")
            c.commit()
        before = db.read_bytes()
        result = prepare.prompt_snapshot(self.root)
        self.assertEqual(before, db.read_bytes())
        expected = "OVERRIDE\n\n" + prepare.MARKER + "\n\nCANON rules.md\n\nCANON rules_mapping.md\n\n--- EDITORIAL SKILL ---\n\nEXISTING SKILL"
        self.assertEqual(result["stages"]["wiki_extract"]["effective"], expected)
        self.assertNotIn("STALE", result["stages"]["wiki_merge"]["effective"])

    def test_preflight_remains_closed_for_draft_materials(self):
        prepare.write_json(self.root / "manifest.json", {"snapshot_id": "test", "source_records": 145})
        prepare.write_json(self.root / "protocol.json", {"planned_repetitions": 5, "arms": ["tesla", "openwiki"],
                                                       "prompt_scope_status": "blocked_historical_details"})
        sums = {p.name: prepare.sha(p.read_bytes()) for p in self.root.iterdir()}
        prepare.write_json(self.root / "checksums.json", sums)
        result = prepare.preflight(self.root)
        self.assertFalse(result["ready_for_generation"])
        self.assertEqual(result["planned_monthly_updates"], 120)
        self.assertTrue(any("historical details" in b for b in result["blockers"]))


class TransportTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory(prefix="yunost-transport-test-")
        self.root = Path(self.tmp.name)
        self.prompt = self.root / "wiki_extract.md"; self.prompt.write_text("EXISTING CANON", encoding="utf-8")
        self.bundle = self.root / "bundle.json"; self.bundle.write_text('{"posts":[]}', encoding="utf-8")
        self.compiler = types.SimpleNamespace(_validate_canonical_prompt=lambda x: None,
            _output_schema=lambda stage: {"type": "object", "properties": {}, "additionalProperties": False},
            _json_object=json.loads)

    def tearDown(self): self.tmp.cleanup()

    def provider(self, status="completed", content='{"posts":[]}', retry=0):
        requests = []
        response = types.SimpleNamespace(status=status, output_text=content,
            model_dump=lambda **kw: {"status": status, "model": "gpt-6-luna", "output_text": content, "usage": {"input_tokens": 1, "output_tokens": 1}})
        def create(**kwargs): requests.append(kwargs); return response
        client = types.SimpleNamespace(max_retries=retry, responses=types.SimpleNamespace(create=create))
        return make_provider(client, self.compiler, self.root / "calls"), requests

    def invoke(self, fn, **kw):
        return fn("low", self.prompt, self.bundle, self.root / "output.json", self.root,
                  ("gpt-6-luna",), False, "unused", self.root, **kw)

    def test_medium_responses_and_complete_request_response_logs(self):
        fn, requests = self.provider(); self.invoke(fn)
        r = requests[0]
        self.assertEqual(r["model"], "gpt-6-luna")
        self.assertEqual(r["reasoning"], {"effort": "medium"})
        self.assertEqual(r["instructions"], "EXISTING CANON")
        self.assertEqual(r["input"], 'Return only the JSON object required by the system instructions.\n\nINPUT BUNDLE:\n{"posts":[]}')
        self.assertEqual(r["text"]["format"]["name"], "extract")
        self.assertNotIn("temperature", r)
        self.assertEqual(len(list((self.root / "calls").glob("*/response.json"))), 1)

    def test_incomplete_and_invalid_response_never_become_output(self):
        for status, content in [("incomplete", "{}"), ("completed", "broken JSON")]:
            fn, _ = self.provider(status, content)
            with self.assertRaises(ValueError): self.invoke(fn)
            self.assertFalse((self.root / "output.json").exists())

    def test_failed_validation_retains_raw_response(self):
        fn, _ = self.provider()
        def reject(x): raise ValueError("bad identity")
        with self.assertRaises(ValueError): self.invoke(fn, validator=reject)
        self.assertFalse((self.root / "output.json").exists())
        self.assertTrue(list((self.root / "calls").glob("*/response.json")))

    def test_retries_and_fallback_forbidden(self):
        with self.assertRaises(ValueError): self.provider(retry=2)
        fn, requests = self.provider()
        with self.assertRaises(ValueError):
            fn("low", self.prompt, self.bundle, self.root / "out", self.root, ("other",), False, "unused", self.root)
        self.assertEqual(requests, [])


if __name__ == "__main__":
    unittest.main()
