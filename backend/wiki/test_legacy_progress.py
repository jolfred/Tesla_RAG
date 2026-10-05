import fcntl
import json
import tempfile
import unittest
from pathlib import Path

from backend.wiki.ingest import connect, export_posts, inventory
from backend.wiki.legacy_progress import reconcile_legacy


class LegacyProgressTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.root = Path(self.tmp.name)
        self.db = self.root / "ledger.sqlite"
        self.wiki = self.root / "wiki"
        chunks = self.wiki / "_batches/chunks"
        chunks.mkdir(parents=True)
        self.chunk = chunks / "posts_tesla_000.txt"
        self.chunk.write_text('[001] id=wall-1_1 published=2020-01-02\n"""\nТочный факт.\n"""\n')
        self.done = self.wiki / "_batches/done.txt"
        self.done.write_text(self.chunk.name + "\n" + self.chunk.name + "\n")
        self.log = self.wiki / "log.md"
        self.log.write_text('| 2026-10-01 | INGEST _batches/chunks/posts_tesla_000 | Пачка целиком. |\n')
        source = self.root / "posts.jsonl"
        source.write_text(json.dumps({"post_id": "wall-1_1", "text_raw": "Точный факт. #хештег",
                                      "text_clean": "Точный факт.", "published_at": "2020-01-02T12:00:00Z"}) + "\n")
        inventory(self.db, source)

    def state(self):
        con = connect(self.db)
        try:
            return con.execute("SELECT state FROM posts").fetchone()[0]
        finally:
            con.close()

    def test_dry_run_then_apply_and_repeat_preserve_articles(self):
        article = self.wiki / "person.md"
        article.write_text("Существующая статья.")
        before = article.read_bytes()
        preview = reconcile_legacy(self.db, self.wiki)
        self.assertEqual(preview["eligible_queued_sources"], 1)
        self.assertEqual(self.state(), "queued")
        self.assertEqual(reconcile_legacy(self.db, self.wiki, True)["newly_reconciled"], 1)
        self.assertEqual(self.state(), "legacy_processed")
        self.assertEqual(export_posts(self.db), [])
        self.assertEqual(reconcile_legacy(self.db, self.wiki, True)["newly_reconciled"], 0)
        self.assertEqual(article.read_bytes(), before)

    def test_done_marker_without_journal_is_insufficient(self):
        self.log.write_text("")
        result = reconcile_legacy(self.db, self.wiki, True)
        self.assertEqual(result["matched_previous_sources"], 0)
        self.assertEqual(self.state(), "queued")

    def test_changed_text_and_date_remain_queued(self):
        for change in ("Другой факт.", "2020-02-03"):
            original = self.chunk.read_text()
            self.chunk.write_text(original.replace("Точный факт.", change) if "факт" in change else original.replace("2020-01-02", change))
            self.assertEqual(reconcile_legacy(self.db, self.wiki, True)["matched_previous_sources"], 0)
            self.assertEqual(self.state(), "queued")
            self.chunk.write_text(original)

    def test_existing_review_is_not_overwritten(self):
        con = connect(self.db)
        con.execute("UPDATE posts SET state='review'")
        con.commit()
        con.close()
        self.assertEqual(reconcile_legacy(self.db, self.wiki, True)["newly_reconciled"], 0)
        self.assertEqual(self.state(), "review")

    def test_active_compiler_prevents_reconciliation(self):
        with self.db.with_suffix(".sqlite.compile.lock").open("a") as lock:
            fcntl.flock(lock, fcntl.LOCK_EX | fcntl.LOCK_NB)
            with self.assertRaisesRegex(RuntimeError, "another compiler"):
                reconcile_legacy(self.db, self.wiki, True)


if __name__ == "__main__":
    unittest.main()
