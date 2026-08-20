import json
from pathlib import Path


def read_publication_json(file_path: str) -> str | None:
    try:
        with open(file_path, 'r', encoding='utf-8') as f:
            data = json.load(f)
        text = data.get("text", "") or ""
        title = data.get("title", "")
        if title and not text.startswith(title):
            text = f"{title}\n\n{text}"
        return text.strip() or None
    except Exception:
        return None


def parse_publication_meta(file_path: str) -> dict | None:
    try:
        with open(file_path, 'r', encoding='utf-8') as f:
            return json.load(f)
    except Exception:
        return None
