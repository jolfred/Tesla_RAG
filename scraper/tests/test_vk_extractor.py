from datetime import datetime, timezone
from unittest.mock import MagicMock, patch

import pytest

from scraper.extractors.vk import VkApiExtractor, VkRateLimitError

from .factories import build_vk_post


class TestResolveGroup:
    def test_resolves_group_by_domain(self):
        extractor = VkApiExtractor(token="fake_token")

        mock_api = MagicMock()
        mock_api.utils.resolveScreenName.return_value = {
            "type": "group",
            "object_id": 12345,
        }
        mock_api.groups.getById.return_value = [
            {"id": 12345, "name": "Test Group", "screen_name": "test_group"}
        ]

        with patch.object(extractor, "api", mock_api):
            info = extractor.resolve_group("test_group")

        assert info["group_id"] == 12345
        assert info["group_name"] == "Test Group"
        assert info["group_domain"] == "test_group"
        assert info["owner_id"] == -12345

    def test_resolves_from_full_url(self):
        extractor = VkApiExtractor(token="fake_token")
        mock_api = MagicMock()
        mock_api.utils.resolveScreenName.return_value = {
            "type": "group",
            "object_id": 999,
        }
        mock_api.groups.getById.return_value = [
            {"id": 999, "name": "Some Group", "screen_name": "some_group"}
        ]

        with patch.object(extractor, "api", mock_api):
            info = extractor.resolve_group("https://vk.com/some_group")

        assert info["group_id"] == 999

    def test_resolve_nonexistent_group(self):
        extractor = VkApiExtractor(token="fake_token")
        mock_api = MagicMock()
        mock_api.utils.resolveScreenName.return_value = None

        with patch.object(extractor, "api", mock_api):
            with pytest.raises(ValueError, match="не найдена"):
                extractor.resolve_group("unknown")

    def test_fetch_posts_without_resolve_raises(self):
        extractor = VkApiExtractor(token="fake_token")
        with pytest.raises(RuntimeError, match="resolve_group"):
            list(extractor.fetch_posts(10))


class TestFetchPosts:
    def test_yields_posts_with_text(self):
        extractor = VkApiExtractor(token="fake_token")
        extractor._group_info = {
            "owner_id": -12345,
            "group_id": 12345,
            "group_name": "Test",
            "group_domain": "test_group",
        }

        mock_api = MagicMock()
        mock_api.wall.get.return_value = {
            "items": [
                build_vk_post(id=1, text="Post with text", owner_id=-12345, date=1704067200),
                build_vk_post(id=2, text="Another post", owner_id=-12345, date=1704067200),
            ],
        }

        with patch.object(extractor, "api", mock_api):
            posts = list(extractor.fetch_posts(10))

        assert len(posts) == 2
        assert posts[0]["post_id"] == "1"
        assert posts[0]["text_raw"] == "Post with text"
        assert posts[0]["source_platform"] == "vk"

    def test_filters_posts_without_text(self):
        extractor = VkApiExtractor(token="fake_token")
        extractor._group_info = {
            "owner_id": -12345,
            "group_id": 12345,
            "group_name": "Test",
            "group_domain": "test_group",
        }

        mock_api = MagicMock()
        mock_api.wall.get.return_value = {
            "items": [
                build_vk_post(id=1, text="", owner_id=-12345, date=1704067200),
                build_vk_post(id=2, text="   ", owner_id=-12345, date=1704067200),
                build_vk_post(id=3, text="Valid", owner_id=-12345, date=1704067200),
            ],
        }

        with patch.object(extractor, "api", mock_api):
            posts = list(extractor.fetch_posts(10))

        assert len(posts) == 1
        assert posts[0]["post_id"] == "3"

    def test_pagination(self):
        extractor = VkApiExtractor(token="fake_token")
        extractor._group_info = {
            "owner_id": -12345,
            "group_id": 12345,
            "group_name": "Test",
            "group_domain": "test_group",
        }

        mock_api = MagicMock()
        # Return different posts on each call
        mock_api.wall.get.side_effect = [
            {"items": [build_vk_post(id=i, text=f"Post {i}", owner_id=-12345, date=1704067200) for i in range(1, 101)]},
            {"items": [build_vk_post(id=i, text=f"Post {i}", owner_id=-12345, date=1704067200) for i in range(101, 151)]},
        ]

        with patch.object(extractor, "api", mock_api):
            posts = list(extractor.fetch_posts(150))

        assert len(posts) == 150
        assert mock_api.wall.get.call_count == 2
        # First call offset=0, second offset=100
        assert mock_api.wall.get.call_args_list[1][1]["offset"] == 100

    def test_photo_attachment_parsing(self):
        extractor = VkApiExtractor(token="fake_token")
        extractor._group_info = {
            "owner_id": -1,
            "group_id": 1,
            "group_name": "G",
            "group_domain": "g",
        }

        post = build_vk_post(id=1, text="with photo", owner_id=-1, date=1704067200)
        post["attachments"] = [
            {
                "type": "photo",
                "photo": {
                    "sizes": [
                        {"width": 100, "height": 100, "url": "https://small.url"},
                        {"width": 800, "height": 600, "url": "https://large.url"},
                    ],
                },
            },
        ]

        mock_api = MagicMock()
        mock_api.wall.get.return_value = {"items": [post]}

        with patch.object(extractor, "api", mock_api):
            posts = list(extractor.fetch_posts(10))

        assert posts[0]["attachments"]["photos"] == ["https://large.url"]

    def test_link_and_doc_attachment_parsing(self):
        extractor = VkApiExtractor(token="fake_token")
        extractor._group_info = {"owner_id": -1, "group_id": 1, "group_name": "G", "group_domain": "g"}

        post = build_vk_post(id=1, text="attachments", owner_id=-1, date=1704067200)
        post["attachments"] = [
            {"type": "link", "link": {"url": "https://example.com"}},
            {"type": "doc", "doc": {"url": "https://doc.example.com/file.pdf"}},
        ]

        mock_api = MagicMock()
        mock_api.wall.get.return_value = {"items": [post]}

        with patch.object(extractor, "api", mock_api):
            posts = list(extractor.fetch_posts(10))

        assert posts[0]["attachments"]["links"] == ["https://example.com"]
        assert posts[0]["attachments"]["docs"] == ["https://doc.example.com/file.pdf"]


class TestRetryLogic:
    def test_retry_on_rate_limit(self):
        extractor = VkApiExtractor(token="fake_token")
        extractor._group_info = {"owner_id": -1, "group_id": 1, "group_name": "G", "group_domain": "g"}

        mock_api = MagicMock()
        wall_mock = mock_api.wall.get

        vk_error = MagicMock()
        vk_error.code = 6  # too many requests
        # type() the old-school way
        import vk_api.exceptions
        error_instance = vk_api.exceptions.VkApiError(None, "rate limit")
        error_instance.code = 6
        error_instance.error = None

        wall_mock.side_effect = [
            error_instance,
            {"items": [build_vk_post(id=1, text="ok", owner_id=-1, date=1704067200)]},
        ]

        with patch.object(extractor, "api", mock_api):
            posts = list(extractor.fetch_posts(10))

        assert len(posts) == 1
        assert wall_mock.call_count == 2

    def test_no_retry_on_auth_error(self):
        extractor = VkApiExtractor(token="fake_token")
        extractor._group_info = {"owner_id": -1, "group_id": 1, "group_name": "G", "group_domain": "g"}

        mock_api = MagicMock()
        import vk_api.exceptions
        auth_error = vk_api.exceptions.VkApiError(None, "auth failed")
        auth_error.code = 5
        auth_error.error = None
        mock_api.wall.get.side_effect = auth_error

        with patch.object(extractor, "api", mock_api):
            with pytest.raises(vk_api.exceptions.VkApiError):
                list(extractor.fetch_posts(10))
