from datetime import datetime, timezone
from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest

from scraper.orchestrator.parser_orchestrator import ParserOrchestrator

from .factories import build_vk_post


@pytest.fixture
def tmp_output(tmp_path: Path) -> str:
    return str(tmp_path / "posts")


class TestParserOrchestrator:
    def test_full_pipeline(self, tmp_output):
        orchestrator = ParserOrchestrator(output_dir=tmp_output)

        mock_extractor = MagicMock()
        mock_extractor.last_timestamp = None
        mock_extractor.resolve_group.return_value = {
            "owner_id": -12345,
            "group_id": 12345,
            "group_name": "Test Group",
            "group_domain": "test_group",
        }
        mock_extractor.fetch_posts.return_value = [
            {
                "post_id": "1",
                "source_platform": "vk",
                "group_id": "12345",
                "group_name": "Test Group",
                "group_domain": "test_group",
                "post_url": "https://vk.com/test_group?w=wall-12345_1",
                "published_at": datetime(2024, 1, 1, 12, 0, tzinfo=timezone.utc).isoformat(),
                "text_raw": "Привет 😊! #тест [id1|Пользователь]",
                "text_clean": "",
                "hashtags": [],
                "mentions": [],
                "attachments": {
                    "photos": ["https://photo.url"],
                    "links": [],
                    "docs": [],
                },
            },
        ]

        with patch("scraper.orchestrator.parser_orchestrator.VkApiExtractor", return_value=mock_extractor):
            saved = orchestrator.run(
                platform="vk",
                group_url="https://vk.com/test_group",
                limit=10,
                token="fake_token",
            )

        assert saved == 1
        output_file = Path(tmp_output) / "posts_test_group.jsonl"
        assert output_file.exists()
        content = output_file.read_text(encoding="utf-8")
        assert "Привет" in content
        assert "Пользователь" in content
        assert "тест" in content
        import json
        parsed = json.loads(content.strip().split("\n")[0])
        assert "😊" in parsed["text_raw"]
        assert "😊" not in parsed["text_clean"]

    def test_unsupported_platform(self):
        orchestrator = ParserOrchestrator()
        with pytest.raises(ValueError, match="Неподдерживаемая платформа"):
            orchestrator.run(platform="twitter", group_url="x.com", limit=5)

    def test_missing_token_for_vk(self):
        orchestrator = ParserOrchestrator()
        with pytest.raises(ValueError, match="VK_SERVICE_TOKEN"):
            orchestrator.run(platform="vk", group_url="vk.com/test", limit=5)
