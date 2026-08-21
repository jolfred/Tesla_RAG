import glob as globlib
import json
from datetime import datetime, timezone
from pathlib import Path

from backend.indexer.logger import setup_indexer_logger

logger = setup_indexer_logger()


def parse_dt(value: str) -> datetime:
    dt = datetime.fromisoformat(value.replace("Z", "+00:00"))
    if dt.tzinfo is None:
        dt = dt.replace(tzinfo=timezone.utc)
    return dt


def filter_posts(posts: list[dict], min_date: str = "2026-01-01") -> list[dict]:
    if not min_date:
        return posts
    min_dt = parse_dt(min_date)
    result = []
    for post in posts:
        published_str = post.get("published_at")
        if not published_str:
            continue
        try:
            published_dt = parse_dt(published_str)
        except (ValueError, TypeError):
            continue
        if published_dt >= min_dt:
            result.append(post)
    return result


def build_embedding_text(post: dict) -> str:
    group = post.get("group_name", "")
    text = post.get("text_clean", "")
    if group:
        return f"{group}: {text}"
    return text


def load_posts(jsonl_paths: list[str]) -> tuple[list[dict], list[str]]:
    posts_raw = []
    for pattern in jsonl_paths:
        if "*" in pattern or "?" in pattern:
            paths = sorted(globlib.glob(pattern))
        else:
            paths = [pattern]
        for path_str in paths:
            path = Path(path_str)
            if not path.exists():
                logger.warning("JSONL file not found: %s", path)
                continue
            with path.open(encoding="utf-8") as f:
                for line_num, line in enumerate(f, 1):
                    line = line.strip()
                    if not line:
                        continue
                    try:
                        posts_raw.append(json.loads(line))
                    except json.JSONDecodeError as e:
                        logger.warning(
                            "Skipping invalid JSON at line %d in %s: %s",
                            line_num,
                            path,
                            e,
                        )

    seen_urls: dict[str, dict] = {}
    for post in posts_raw:
        url = post.get("post_url", "")
        if url and url not in seen_urls:
            seen_urls[url] = post
    return list(seen_urls.values()), posts_raw
