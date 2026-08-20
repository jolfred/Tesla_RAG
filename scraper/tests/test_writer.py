import json
from datetime import datetime, timezone
from pathlib import Path

import pytest

from scraper.models import SocialMediaPost
from scraper.storage.writer import write_post


@pytest.fixture
def post():
    return SocialMediaPost(
        post_id="1",
        source_platform="vk",
        group_id="123",
        group_name="Test",
        group_domain="test_group",
        post_url="https://vk.com/test_group?w=wall-123_1",
        published_at=datetime(2024, 1, 1, 12, 0, tzinfo=timezone.utc),
        text_raw="raw text",
        text_clean="clean text",
    )


@pytest.fixture
def tmp_path(tmp_path: Path) -> Path:
    return tmp_path


class TestWritePost:
    def test_writes_single_post(self, post, tmp_path):
        filepath = tmp_path / "out.jsonl"
        write_post(post, filepath)
        lines = filepath.read_text(encoding="utf-8").strip().split("\n")
        assert len(lines) == 1
        data = json.loads(lines[0])
        assert data["post_id"] == "1"
        assert data["text_clean"] == "clean text"

    def test_append_mode(self, post, tmp_path):
        filepath = tmp_path / "append_test.jsonl"
        write_post(post, filepath)
        write_post(post, filepath)
        lines = filepath.read_text(encoding="utf-8").strip().split("\n")
        assert len(lines) == 2

    def test_creates_directory(self, post, tmp_path):
        deep_path = tmp_path / "a" / "b" / "c" / "deep.jsonl"
        write_post(post, deep_path)
        assert deep_path.exists()

    def test_serialization_is_valid_jsonl(self, post, tmp_path):
        filepath = tmp_path / "valid.jsonl"
        write_post(post, filepath)
        for line in filepath.read_text(encoding="utf-8").strip().split("\n"):
            data = json.loads(line)
            assert "post_id" in data
            assert "text_raw" in data
            assert "published_at" in data
