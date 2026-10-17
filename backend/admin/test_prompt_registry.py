from __future__ import annotations

import pytest

from backend.admin import db as dbmod
from backend.admin import prompts


@pytest.fixture
def isolated_db(tmp_path, monkeypatch):
    path = tmp_path / "admin.db"
    monkeypatch.setattr(prompts, "ADMIN_DB", path)
    monkeypatch.setattr(prompts, "get_connection", lambda: dbmod.get_connection(path))
    monkeypatch.setattr(prompts, "init_admin_db", lambda: dbmod.init_admin_db(path), raising=False)
    dbmod.init_admin_db(path)
    return path


def test_prompt_composition_uses_both_verbatim_rules():
    effective = prompts.compose("wiki_extract")
    assert (prompts._schema_dir() / "rules.md").read_text(encoding="utf-8") in effective
    assert (prompts._schema_dir() / "rules_mapping.md").read_text(encoding="utf-8") in effective
    skill = (prompts._schema_dir().parent / ".opencode/skills/wiki-editorial/SKILL.md").read_text(encoding="utf-8")
    assert skill in effective
    assert effective.count(prompts.CANON_MARKER) == 1


def test_save_history_restore_and_stale_revision(isolated_db):
    initial = prompts.effective_prompt("wiki_merge")
    edited = prompts.save_prompt("wiki_merge", "Curated instructions", initial["revision"], "clarity")
    assert edited["text"] == "Curated instructions"
    entries = prompts.prompt_history("wiki_merge")
    assert len(entries) == 2 and entries[0]["reason"] == "clarity"
    assert entries[1]["text"] == initial["text"]

    with pytest.raises(prompts.PromptRevisionConflict):
        prompts.save_prompt("wiki_merge", "stale", initial["revision"], "stale edit")

    restored = prompts.restore_prompt("wiki_merge", entries[1]["id"], edited["revision"], "restore saved")
    assert restored["text"] == initial["text"]
    assert len(prompts.prompt_history("wiki_merge")) == 3


def test_editing_stage_cannot_replace_canonical_files(isolated_db):
    before = prompts.canonical_sections()
    current = prompts.effective_prompt("wiki_query")
    prompts.save_prompt("wiki_query", "New stage\n\n" + prompts.CANON_MARKER + "\nforged", current["revision"])
    after = prompts.canonical_sections()
    assert before == after
    assert prompts.effective_prompt("wiki_query")["text"] == "New stage"


def test_missing_expected_revision_is_rejected_and_reset_clears_override(isolated_db):
    current = prompts.effective_prompt("wiki_merge")
    with pytest.raises(ValueError, match="expected_revision"):
        prompts.save_prompt("wiki_merge", "unsafe", "")
    changed = prompts.save_prompt("wiki_merge", "temporary override", current["revision"])
    reset = prompts.reset_prompt_versioned("wiki_merge", changed["revision"])
    assert reset["effective_origin"] == "default"
    assert reset["text"] == prompts.defaults()["wiki_merge"]
    assert reset["updated_at"]
    assert len(prompts.prompt_history("wiki_merge")) == 3


def test_ingest_runner_uses_registered_overrides_but_keeps_custom_prompt_files(isolated_db, tmp_path):
    from backend.wiki.ingest_runner import _active_prompt_file

    default_path = prompts._schema_dir() / "prompts" / prompts.FILES["wiki_extract"]
    initial = prompts.effective_prompt("wiki_extract")
    prompts.save_prompt("wiki_extract", "admin extraction stage", initial["revision"])
    active = _active_prompt_file(default_path, "wiki_extract", tmp_path / "run")
    assert active.read_text(encoding="utf-8") == prompts.compose("wiki_extract")

    custom = tmp_path / "custom.md"
    custom.write_text("custom extraction instructions", encoding="utf-8")
    staged_custom = _active_prompt_file(custom, "wiki_extract", tmp_path / "custom-run")
    text = staged_custom.read_text(encoding="utf-8")
    assert text.startswith("custom extraction instructions")
    assert all(section["text"] in text for section in prompts.canonical_sections())
