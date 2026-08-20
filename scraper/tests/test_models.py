from datetime import datetime, timezone

import pytest
from pydantic import ValidationError

from scraper.models import Attachments, Mention, SocialMediaPost


class TestSocialMediaPost:
    def test_minimal_post(self):
        post = SocialMediaPost(
            post_id="123",
            source_platform="vk",
            group_id="456",
            group_name="Test Group",
            post_url="https://vk.com/test?w=wall-456_123",
            published_at=datetime(2024, 1, 1, 12, 0, tzinfo=timezone.utc),
            text_raw="Hello world",
            text_clean="Hello world",
        )
        assert post.post_id == "123"
        assert post.source_platform == "vk"
        assert post.hashtags == []
        assert post.mentions == []
        assert post.attachments.photos == []

    def test_full_post(self):
        post = SocialMediaPost(
            post_id=789,
            source_platform="telegram",
            group_id="g123",
            group_name="Channel",
            group_domain="channel_domain",
            post_url="https://t.me/channel/789",
            published_at=datetime(2024, 6, 15, 10, 30, tzinfo=timezone.utc),
            text_raw="Post with #tag and @mention",
            text_clean="Post with and",
            hashtags=["tag"],
            mentions=[Mention(id="id1", name="User", raw="[id1|User]")],
            attachments=Attachments(
                photos=["https://photo.url"],
                links=["https://link.url"],
                docs=["https://doc.url"],
            ),
        )
        assert post.post_id == 789
        assert post.source_platform == "telegram"
        assert len(post.hashtags) == 1
        assert len(post.attachments.photos) == 1

    def test_invalid_platform(self):
        with pytest.raises(ValidationError):
            SocialMediaPost(
                post_id="1",
                source_platform="twitter",
                group_id="1",
                group_name="G",
                post_url="https://x.com",
                published_at=datetime(2024, 1, 1, tzinfo=timezone.utc),
                text_raw="x",
                text_clean="x",
            )

    def test_missing_required_field(self):
        with pytest.raises(ValidationError):
            SocialMediaPost(
                post_id="1",
                source_platform="vk",
                group_id="1",
                group_name="G",
                published_at=datetime(2024, 1, 1, tzinfo=timezone.utc),
                text_raw="x",
                text_clean="x",
            )

    def test_serialization_roundtrip(self):
        post = SocialMediaPost(
            post_id="42",
            source_platform="vk",
            group_id="g99",
            group_name="Group Name",
            post_url="https://vk.com/g99?w=wall-99_42",
            published_at=datetime(2024, 12, 25, 8, 0, tzinfo=timezone.utc),
            text_raw="#hello мир",
            text_clean="мир",
            hashtags=["hello"],
            mentions=[
                Mention(id="id123", name="Иван", raw="[id123|Иван]"),
            ],
            attachments=Attachments(photos=["https://photo.xyz"]),
        )
        dumped = post.model_dump_json(ensure_ascii=False, by_alias=False)
        restored = SocialMediaPost.model_validate_json(dumped)
        assert restored == post
        assert restored.mentions[0].name == "Иван"
