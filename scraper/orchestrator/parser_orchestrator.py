import json
import logging
from datetime import datetime
from pathlib import Path

from scraper.cleaners.text_cleaner import clean_text
from scraper.extractors.base import BaseExtractor
from scraper.extractors.vk import VkApiExtractor
from scraper.models import Mention, SocialMediaPost
from scraper.storage.writer import write_post


logger = logging.getLogger("scraper.orchestrator")


def _read_last_timestamp(filepath: Path) -> datetime | None:
    if not filepath.exists() or filepath.stat().st_size == 0:
        return None
    try:
        with filepath.open("rb") as f:
            f.seek(-2, 2)
            while f.read(1) != b"\n":
                f.seek(-2, 1)
                if f.tell() <= 1:
                    f.seek(0)
                    break
            last_line = f.readline().decode("utf-8").strip()
        data = json.loads(last_line)
        return datetime.fromisoformat(data["published_at"])
    except (OSError, json.JSONDecodeError, KeyError, ValueError):
        return None


def _load_existing_ids(filepath: Path) -> set[str]:
    if not filepath.exists():
        return set()
    ids: set[str] = set()
    with filepath.open(encoding="utf-8") as f:
        for line in f:
            line = line.strip()
            if not line:
                continue
            try:
                ids.add(str(json.loads(line)["post_id"]))
            except (json.JSONDecodeError, KeyError):
                continue
    return ids


class ParserOrchestrator:
    def __init__(self, output_dir: str = "storage/posts"):
        self.output_dir = Path(output_dir)

    def run(self, platform: str, group_url: str, limit: int, **kwargs) -> int:
        extractor = self._build_extractor(platform, kwargs)
        group_info = extractor.resolve_group(group_url)
        domain = group_info["group_domain"]
        output_path = self.output_dir / f"posts_{domain}.jsonl"
        logger.info("Целевой файл: %s", output_path)

        last_timestamp = _read_last_timestamp(output_path)
        if last_timestamp:
            logger.info("Предыдущая загрузка: последний пост от %s, собираем только новые", last_timestamp.isoformat())

        saved = 0
        for raw in extractor.fetch_posts(limit, last_timestamp=last_timestamp):

            text_clean, hashtags, mentions_raw = clean_text(raw["text_raw"])
            mentions = [Mention(**m) for m in mentions_raw]

            post = SocialMediaPost(
                post_id=raw["post_id"],
                source_platform=raw["source_platform"],
                group_id=raw["group_id"],
                group_name=raw["group_name"],
                group_domain=raw["group_domain"],
                post_url=raw["post_url"],
                published_at=raw["published_at"],
                text_raw=raw["text_raw"],
                text_clean=text_clean,
                hashtags=hashtags,
                mentions=mentions,
                attachments=raw["attachments"],
            )
            write_post(post, output_path)
            saved += 1
            logger.debug(
                "Пост %s: %d символов, %d хэштегов, %d mentions, %d фото",
                raw["post_id"], len(text_clean), len(hashtags), len(mentions),
                len(raw["attachments"].get("photos", [])),
            )

        logger.info("Группа %s: сохранено %d постов", domain, saved)
        return saved

    @staticmethod
    def _build_extractor(platform: str, kwargs: dict) -> BaseExtractor:
        if platform == "vk":
            token = kwargs.get("token")
            if not token:
                raise ValueError("VK_SERVICE_TOKEN обязателен для VkApiExtractor")
            return VkApiExtractor(token)
        raise ValueError(f"Неподдерживаемая платформа: {platform}")
