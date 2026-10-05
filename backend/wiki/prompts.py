"""Canonical Wiki instructions shared by query and compilation."""
from pathlib import Path

SCHEMA_DIR = Path(__file__).resolve().parents[2] / "schema"


def canon_text() -> str:
    return "\n\n".join(
        (SCHEMA_DIR / name).read_text(encoding="utf-8")
        for name in ("rules.md", "rules_mapping.md")
    )


def query_prompt() -> str:
    from backend.admin.prompts import get_prompt
    return get_prompt("wiki_query") + "\n\n" + canon_text()
