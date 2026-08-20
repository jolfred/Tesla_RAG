import pytest

from scraper.cleaners.text_cleaner import (
    clean_text,
    extract_hashtags,
    normalize_whitespace,
    process_mentions,
    remove_emojis,
)


class TestRemoveEmojis:
    def test_removes_simple_emoji(self):
        assert remove_emojis("Привет 😊") == "Привет "

    def test_removes_multiple_emojis(self):
        assert remove_emojis("🔥🚀 тест 🎉") == " тест "

    def test_no_emoji(self):
        assert remove_emojis("Просто текст") == "Просто текст"

    def test_empty_string(self):
        assert remove_emojis("") == ""


class TestExtractHashtags:
    def test_single_hashtag(self):
        cleaned, tags = extract_hashtags("#привет мир")
        assert tags == ["привет"]
        assert "привет" not in cleaned

    def test_multiple_hashtags(self):
        cleaned, tags = extract_hashtags("#foo bar #baz qux")
        assert tags == ["foo", "baz"]
        assert cleaned == "bar  qux"

    def test_no_hashtags(self):
        cleaned, tags = extract_hashtags("просто текст")
        assert tags == []
        assert cleaned == "просто текст"

    def test_hashtag_with_underscore(self):
        cleaned, tags = extract_hashtags("#hello_world text")
        assert tags == ["hello_world"]

    def test_hashtag_at_start(self):
        cleaned, tags = extract_hashtags("#start text")
        assert tags == ["start"]
        assert cleaned == "text"


class TestProcessMentions:
    def test_single_mention(self):
        cleaned, mentions = process_mentions("[id123|Иван] привет")
        assert len(mentions) == 1
        assert mentions[0]["id"] == "id123"
        assert mentions[0]["name"] == "Иван"
        assert mentions[0]["raw"] == "[id123|Иван]"
        assert cleaned == "Иван привет"

    def test_club_mention(self):
        cleaned, mentions = process_mentions("[club456|Название] пост")
        assert mentions[0]["id"] == "club456"
        assert mentions[0]["name"] == "Название"
        assert cleaned == "Название пост"

    def test_multiple_mentions(self):
        cleaned, mentions = process_mentions("[id1|A] и [club2|B] вместе")
        assert len(mentions) == 2
        assert "A и B вместе" == cleaned

    def test_no_mentions(self):
        cleaned, mentions = process_mentions("просто текст")
        assert mentions == []
        assert cleaned == "просто текст"

    def test_mention_with_spaces_in_name(self):
        cleaned, mentions = process_mentions("[id5|Иван Иванов] текст")
        assert mentions[0]["name"] == "Иван Иванов"
        assert cleaned == "Иван Иванов текст"


class TestNormalizeWhitespace:
    def test_multiple_spaces(self):
        assert normalize_whitespace("a   b") == "a b"

    def test_tabs_and_newlines(self):
        assert normalize_whitespace("a\nb\tc") == "a b c"

    def test_trim(self):
        assert normalize_whitespace("  hello  ") == "hello"

    def test_empty(self):
        assert normalize_whitespace("") == ""


class TestCleanText:
    def test_full_pipeline(self):
        text = "Привет 😊! #тест [id1|Пользователь] написал пост #пример"
        cleaned, hashtags, mentions = clean_text(text)
        assert "😊" not in cleaned
        assert hashtags == ["тест", "пример"]
        assert mentions[0]["name"] == "Пользователь"
        assert "😊" not in cleaned
        assert "Пользователь" in cleaned
        assert cleaned == "Привет ! Пользователь написал пост"

    def test_only_emoji(self):
        cleaned, hashtags, mentions = clean_text("🎉🎊")
        assert cleaned == ""
        assert hashtags == []
        assert mentions == []

    def test_only_hashtags(self):
        cleaned, hashtags, mentions = clean_text("#a #b #c")
        assert cleaned == ""
        assert hashtags == ["a", "b", "c"]

    def test_empty_input(self):
        cleaned, hashtags, mentions = clean_text("")
        assert cleaned == ""
        assert hashtags == []
        assert mentions == []
