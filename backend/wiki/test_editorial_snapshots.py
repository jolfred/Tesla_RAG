from __future__ import annotations

from datetime import datetime, timezone
import io
from pathlib import Path
import tarfile

from backend.wiki.editorial_snapshots import import_snapshots
from backend.wiki.editorial_store import EditorialStore


def _tar(path: Path, entries: list[tuple[str, bytes]]) -> None:
    with tarfile.open(path, "w:gz") as archive:
        for name, payload in entries:
            info = tarfile.TarInfo(name)
            info.size = len(payload)
            archive.addfile(info, io.BytesIO(payload))


def test_snapshot_import_is_idempotent_private_safe_and_does_not_rewrite_wiki(tmp_path):
    wiki = tmp_path / "wiki"
    (wiki / "hq").mkdir(parents=True)
    current = "---\nslug: hq/current\nkind: hq\n---\n# Current\nCurrent text.\n"
    (wiki / "hq/current.md").write_text(current, encoding="utf-8")
    (wiki / "hq/old.md").write_text("---\nredirect_to: hq/current\n---\n", encoding="utf-8")
    tar_path = tmp_path / "old-wiki.tar.gz"
    old_canonical = "---\nslug: hq/current\nkind: hq\n---\n# Earlier\nOld text.\n"
    old_alias = "---\nslug: hq/old\nkind: hq\n---\n# Legacy title\nLegacy text.\n"
    _tar(tar_path, [
        ("wiki/hq/current.md", old_canonical.encode()),
        ("wiki/hq/old.md", old_alias.encode()),
        ("wiki/hq/deleted.md", b"# Deleted article\n"),
        ("wiki/_editorial/issues.json", b"[]"),
        ("wiki/AGENTS.md", b"instructions"),
        ("wiki/hq/log.md", b"private log"),
        ("wiki/hq/../escape.md", b"# Escape"),
    ])
    fixed_mtime = 1_791_000_000.25
    import os
    os.utime(tar_path, (fixed_mtime, fixed_mtime))

    before_current = (wiki / "hq/current.md").read_bytes()
    result = import_snapshots(wiki, (p for p in [tar_path]))
    assert result["archives"] == 1
    assert result["imported"] == 2
    assert result["skipped"]["no_current_canonical_page"] == 1
    assert result["skipped"]["private_path"] == 1
    assert result["skipped"]["service_file"] == 2
    assert result["skipped"]["unsafe_path"] == 1
    assert not (wiki / "hq/deleted.md").exists()
    assert (wiki / "hq/current.md").read_bytes() == before_current

    store = EditorialStore(wiki)
    history = store.history("hq/current")
    archived = [store.version("hq/current", row["id"]) for row in history if row["kind"] == "archive"]
    assert len(archived) == 2
    assert {row["markdown"] for row in archived} == {old_canonical, old_alias}
    alias_version = next(row for row in archived if row["markdown"] == old_alias)
    assert "hq/old" in alias_version["reason"]
    expected_time = datetime.fromtimestamp(tar_path.stat().st_mtime, timezone.utc).isoformat(timespec="microseconds")
    assert {row["created_at"] for row in archived} == {expected_time}

    again = import_snapshots(wiki, [tar_path])
    assert again["imported"] == 0
    assert again["duplicates"] == 2
    assert again["baselines"] == 0
    assert (wiki / "hq/current.md").read_bytes() == before_current
