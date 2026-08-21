"""Чистые функции парсинга данных VK (без обращения к API)."""

from datetime import datetime, timezone
from urllib.parse import urlparse


def extract_domain(url_or_domain: str) -> str:
    parsed = urlparse(url_or_domain)
    if parsed.netloc:
        path = parsed.path.strip("/")
        return path.split("/")[0] if path else parsed.netloc.split(".")[0]
    return url_or_domain.split("/")[0].split("?")[0]


def parse_attachments(attachments: list) -> tuple[list[str], list[str], list[str]]:
    photos: list[str] = []
    links: list[str] = []
    docs: list[str] = []

    for att in attachments:
        typ = att.get("type")
        if typ == "photo":
            sizes = att["photo"].get("sizes", [])
            if sizes:
                best = max(sizes, key=lambda s: s.get("width", 0) * s.get("height", 0))
                photos.append(best["url"])
        elif typ == "link":
            url = att["link"].get("url")
            if url:
                links.append(url)
        elif typ == "doc":
            url = att["doc"].get("url")
            if url:
                docs.append(url)

    return photos, links, docs


def post_timestamp(post: dict) -> datetime:
    return datetime.fromtimestamp(post["date"], tz=timezone.utc)


def post_url(domain: str, owner_id: int, post_id) -> str:
    return f"https://vk.com/{domain}?w=wall{owner_id}_{post_id}"


def wall_url(owner_id: int, post_id) -> str:
    return f"https://vk.com/wall{owner_id}_{post_id}"
