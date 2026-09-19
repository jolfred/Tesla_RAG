"""Бэкфилл фото постов из JSONL в Qdrant-payload (коллекция `posts`).

Индексатор исторически писал только post_url/published_at/group_name/text_clean,
поэтому у RAG-ответов не было картинок. Скрипт идёт по storage/posts/*.jsonl,
собирает attachments.photos и дописывает их в payload существующих точек
(set_payload по uuid5(post_url) — идемпотентно, векторы не трогает).

Запуск:
    .venv/bin/python -m backend.scripts.backfill_photos [--dry-run]
"""

import argparse
import glob
import json
import sys
import uuid

sys.path.insert(0, ".")

from backend.config import QDRANT_HOST, QDRANT_PORT  # noqa: E402
from backend.utils.logger import setup_logger  # noqa: E402
from qdrant_client import QdrantClient  # noqa: E402

logger = setup_logger("backfill_photos")

MAX_PHOTOS_PER_POST = 10


def load_photos(pattern: str = "storage/posts/posts_*.jsonl") -> dict[str, list[str]]:
    """post_url -> список фото-URL (с капой на пост)."""
    result: dict[str, list[str]] = {}
    files = sorted(glob.glob(pattern))
    for path in files:
        with open(path, encoding="utf-8") as f:
            for line in f:
                line = line.strip()
                if not line:
                    continue
                try:
                    row = json.loads(line)
                except json.JSONDecodeError:
                    continue
                url = row.get("post_url") or ""
                photos = ((row.get("attachments") or {}).get("photos") or [])
                clean = [p for p in photos
                         if isinstance(p, str) and p.startswith("http")]
                if url and clean:
                    result[url] = clean[:MAX_PHOTOS_PER_POST]
    return result


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--dry-run", action="store_true")
    args = ap.parse_args()

    url_photos = load_photos()
    logger.info("JSONL: %d постов с фото", len(url_photos))

    # gRPC-транспорт: HTTP-скроллы рвутся (Qdrant unhealthy, Errno 104).
    client = QdrantClient(host=QDRANT_HOST, port=6334, prefer_grpc=True,
                          timeout=120)
    names = [c.name for c in client.get_collections().collections]
    if "posts" not in names:
        logger.error("Коллекция 'posts' не найдена")
        return 1

    updated = missing = 0
    offset = None
    while True:
        for attempt in range(5):
            try:
                # Лёгкий скролл: нужен только post_url (полный payload рвёт соединение).
                points, offset = client.scroll(
                    collection_name="posts", limit=200, offset=offset,
                    with_payload=["post_url"], with_vectors=False,
                )
                break
            except Exception as e:
                logger.warning("Scroll retry %d/5: %s", attempt + 1, e)
        else:
            logger.error("Scroll не удался после 5 попыток")
            return 1
        for p in points:
            pay = p.payload or {}
            url = pay.get("post_url") or ""
            photos = url_photos.get(url)
            if not photos:
                missing += 1
                continue
            if not args.dry_run:
                for attempt in range(3):
                    try:
                        client.set_payload(
                            collection_name="posts",
                            payload={"photos": photos},
                            points=[p.id],
                        )
                        break
                    except Exception as e:
                        logger.warning("set_payload retry %d/3: %s", attempt + 1, e)
                else:
                    logger.error("set_payload не удался для %s", url)
                    continue
            updated += 1
        if offset is None:
            break
    logger.info("Готово: обновлено=%d без фото в JSONL=%d", updated, missing)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
