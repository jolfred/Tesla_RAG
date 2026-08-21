import logging
import time
from collections.abc import Iterable
from datetime import datetime

import vk_api
from vk_api.exceptions import VkApiError

from scraper.extractors.base import BaseExtractor
from scraper.extractors.vk_parsers import extract_domain, parse_attachments, post_timestamp, post_url, wall_url
from scraper.extractors.vk_retry import VkRateLimitError, raise_if_retryable, vk_retry


logger = logging.getLogger("scraper.extractors.vk")


class VkApiExtractor(BaseExtractor):
    def __init__(self, token: str):
        self.vk_session = vk_api.VkApi(token=token)
        self.api = self.vk_session.get_api()
        self._group_info: dict | None = None
        self.last_timestamp: datetime | None = None

    def resolve_group(self, url_or_domain: str) -> dict:
        domain = extract_domain(url_or_domain)
        resolved = self.api.utils.resolveScreenName(screen_name=domain)
        if resolved is None:
            raise ValueError(f"Группа с доменом '{domain}' не найдена")

        obj_type = resolved["type"]
        obj_id = resolved["object_id"]

        if obj_type == "group":
            owner_id = -obj_id
            group_data = self.api.groups.getById(group_ids=obj_id)[0]
            group_name: str = group_data.get("name", "")
        elif obj_type == "user":
            owner_id = obj_id
            user_data = self.api.users.get(user_ids=obj_id)[0]
            group_name = f"{user_data.get('first_name', '')} {user_data.get('last_name', '')}".strip()
        else:
            raise ValueError(f"Неизвестный тип объекта: {obj_type}")

        self._group_info = {
            "owner_id": owner_id,
            "group_id": obj_id,
            "group_name": group_name,
            "group_domain": domain,
        }
        logger.info("Домен %s → owner_id=%d, группа \"%s\"", domain, owner_id, group_name)
        return dict(self._group_info)

    def fetch_posts(self, limit: int, **kwargs) -> Iterable[dict]:
        if self._group_info is None:
            raise RuntimeError("Сначала вызовите resolve_group()")

        last_timestamp: datetime | None = kwargs.get("last_timestamp")
        owner_id = self._group_info["owner_id"]
        domain = self._group_info["group_domain"]
        step = 100
        self.last_timestamp = None

        total_available: int | None = None
        offset = 0
        fetched = 0

        if limit == 0:
            first = self._get_wall(owner_id=owner_id, offset=0, count=1)
            total_available = first.get("count", 0)
            limit = total_available if total_available else 1000
            logger.info("Доступно постов: %d, заберём: %d", total_available, limit)
            for post in first.get("items", []):
                ok = self._process_post(post, domain, last_timestamp)
                if ok is None:
                    break
                if ok:
                    yield self._parse_post(post, domain)
                    fetched += 1
            offset = fetched

        while offset < limit:
            batch = min(step, limit - offset)
            logger.debug("Запрос wall.get: owner_id=%d, offset=%d, count=%d", owner_id, offset, batch)
            response = self._get_wall(owner_id=owner_id, offset=offset, count=batch)
            items = response.get("items", [])
            logger.debug("Получено %d постов (offset=%d)", len(items), offset)
            if not items:
                break
            for post in items:
                ok = self._process_post(post, domain, last_timestamp)
                if ok is None:
                    break
                if ok:
                    yield self._parse_post(post, domain)
                    fetched += 1
            else:
                offset += batch
                time.sleep(0.35)
                continue
            break

        if last_timestamp and self.last_timestamp is None:
            logger.info("Новых постов нет")
        elif fetched < limit:
            logger.warning("Получено %d из %d запрошенных — часть постов недоступна", fetched, limit)
        logger.info("Парсинг завершён: %d постов", fetched)

    def _process_post(self, post: dict, domain: str, last_timestamp: datetime | None) -> bool | None:
        post_date = post_timestamp(post)
        if last_timestamp and post_date <= last_timestamp:
            return None
        text = (post.get("text") or "").strip()
        if not text:
            copy_history = post.get("copy_history")
            if copy_history:
                original = copy_history[0]
                orig_text = (original.get("text") or "").strip()
                if orig_text:
                    orig_owner = original.get("owner_id", 0)
                    orig_id = original.get("id", 0)
                    logger.info("Репост из: %s", wall_url(orig_owner, orig_id))
                    if self.last_timestamp is None or post_date < self.last_timestamp:
                        self.last_timestamp = post_date
                    return True
            assert self._group_info is not None
            owner_id = post.get("owner_id", self._group_info["owner_id"])
            logger.warning("Пропущен пустой пост: %s", post_url(domain, owner_id, post["id"]))
            return False
        if self.last_timestamp is None or post_date < self.last_timestamp:
            self.last_timestamp = post_date
        return True

    @vk_retry
    def fetch_group_meta(self) -> dict:
        if self._group_info is None:
            raise RuntimeError("Сначала вызовите resolve_group()")

        obj_id = self._group_info["group_id"]
        if obj_id < 0:
            raise RuntimeError("fetch_group_meta поддерживает только группы")

        fields = "description,status,contacts,links,members_count,screen_name,site,verified"
        group_data = self.api.groups.getById(group_ids=obj_id, fields=fields)[0]

        contacts = []
        raw_contacts = group_data.get("contacts") or []
        user_ids = [c["user_id"] for c in raw_contacts if c.get("user_id")]
        user_names = {}
        if user_ids:
            try:
                users = self.api.users.get(user_ids=user_ids)
                user_names = {u["id"]: f"{u['first_name']} {u['last_name']}" for u in users}
            except Exception as e:
                logger.warning("Не удалось получить имена контактов: %s", e)

        for c in raw_contacts:
            uid = c.get("user_id")
            contacts.append({
                "user_id": uid,
                "name": user_names.get(uid, ""),
                "role_title": c.get("desc", ""),
                "profile_url": f"https://vk.com/id{uid}" if uid else "",
            })

        links = []
        for ln in group_data.get("links") or []:
            url = ln.get("url", "")
            if url:
                links.append({"name": ln.get("name", ""), "url": url})

        meta = {
            "domain": self._group_info["group_domain"],
            "group_id": obj_id,
            "name": group_data.get("name", self._group_info["group_name"]),
            "description": group_data.get("description", ""),
            "status": group_data.get("status", ""),
            "members_count": int(group_data.get("members_count", 0) or 0),
            "site": group_data.get("site", ""),
            "verified": bool(group_data.get("verified", 0)),
            "contacts": contacts,
            "links": links,
        }
        logger.info(
            "Метаданные %s: %d контактов, %d ссылок, участников: %d",
            meta["domain"], len(contacts), len(links), meta["members_count"],
        )
        return meta

    @vk_retry
    def _get_wall(self, owner_id: int, offset: int, count: int) -> dict:
        try:
            return self.api.wall.get(owner_id=owner_id, offset=offset, count=count)
        except VkApiError as e:
            raise_if_retryable(e)
            raise

    def _parse_post(self, post: dict, domain: str) -> dict:
        assert self._group_info is not None
        post_id = post["id"]
        owner_id = post.get("owner_id", self._group_info["owner_id"])
        published = post_timestamp(post)

        text = post.get("text") or ""
        attachments = list(post.get("attachments", []))

        copy_history = post.get("copy_history")
        if copy_history and not text.strip():
            original = copy_history[0]
            text = original.get("text") or ""
            orig_attachments = original.get("attachments", [])
            attachments.extend(orig_attachments)

        photos, links, docs = parse_attachments(attachments)

        return {
            "post_id": str(post_id),
            "source_platform": "vk",
            "group_id": str(self._group_info["group_id"]),
            "group_name": self._group_info["group_name"],
            "group_domain": self._group_info["group_domain"],
            "post_url": post_url(domain, owner_id, post_id),
            "published_at": published.isoformat(),
            "text_raw": text,
            "text_clean": "",
            "hashtags": [],
            "mentions": [],
            "attachments": {
                "photos": photos,
                "links": links,
                "docs": docs,
            },
        }
