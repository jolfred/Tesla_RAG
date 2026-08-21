"""Загрузка и разбор метаданных VK-групп."""

import glob
import json
import re
from datetime import datetime, timezone
from pathlib import Path

from backend.indexer.logger import setup_indexer_logger

logger = setup_indexer_logger()

GROUPS_DIR = Path(__file__).resolve().parent.parent.parent / "storage" / "groups"
GROUP_SOURCE_PREFIX = "group://"

_FROM_DESC_RE = re.compile(r"\[(club\d+|[^|\]]+)\|([^|\]]+)\]")


def today() -> str:
    return datetime.now(timezone.utc).date().isoformat() + "T00:00:00Z"


def load_group_files() -> list[dict]:
    metas = []
    for path_str in sorted(glob.glob(str(GROUPS_DIR / "groups_*.json"))):
        path = Path(path_str)
        try:
            with path.open(encoding="utf-8") as f:
                metas.append(json.load(f))
        except (json.JSONDecodeError, OSError) as e:
            logger.warning("Cannot load %s: %s", path, e)
    return metas


def parse_units_from_description(description: str) -> list[tuple[str, str]]:
    """Из описания: [club144172595|«Монолит»] → (club_id_or_url, name)."""
    return [(clean, name) for clean, name in _FROM_DESC_RE.findall(description)]


def clean_entity_name(name: str) -> str:
    return name.strip().strip('«»"').strip()


def group_card_text(meta: dict) -> str:
    parts = [f"Группа: {meta.get('name', '')}"]
    if meta.get("status"):
        parts.append(f"Статус: {meta['status']}")
    if meta.get("members_count"):
        parts.append(f"Участников: {meta['members_count']}")
    if meta.get("description"):
        parts.append(f"Описание: {meta['description']}")
    if meta.get("contacts"):
        contacts = "; ".join(
            f"{c.get('name', '')} — {c.get('role_title', '')}"
            for c in meta["contacts"]
        )
        parts.append(f"Контакты: {contacts}")
    if meta.get("links"):
        links = ", ".join(link.get("name", "") for link in meta["links"])
        parts.append(f"Связанные сообщества: {links}")
    return "\n".join(parts)
