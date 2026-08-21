import json
import logging
from datetime import datetime, timezone
from unittest.mock import MagicMock, patch

import pytest
from pydantic import ValidationError

from backend.indexer.extractors import extract_graph_from_post
from backend.indexer.neo4j_writer import save_to_neo4j
from backend.indexer.posts import build_embedding_text, filter_posts
from backend.indexer.prompts import build_post_prompt
from backend.indexer.schemas import (
    Entity,
    EntityType,
    GraphExtractionResult,
    RelationType,
    Relationship,
)


class TestFilterPosts:
    def test_filters_out_old_posts(self):
        posts = [
            {"published_at": "2025-12-31T23:59:59Z", "post_id": "1"},
            {"published_at": "2026-01-01T00:00:00Z", "post_id": "2"},
            {"published_at": "2026-06-15T10:00:00Z", "post_id": "3"},
        ]
        result = filter_posts(posts, min_date="2026-01-01")
        assert len(result) == 2
        assert [p["post_id"] for p in result] == ["2", "3"]

    def test_excludes_old_posts(self):
        posts = [
            {"published_at": "2025-06-01T00:00:00Z", "post_id": "old1"},
            {"published_at": "2025-12-31T23:59:59Z", "post_id": "old2"},
        ]
        result = filter_posts(posts, min_date="2026-01-01")
        assert result == []

    def test_handles_missing_published_at(self):
        posts = [
            {"post_id": "1"},
            {"published_at": "2026-03-01T00:00:00Z", "post_id": "2"},
        ]
        result = filter_posts(posts, min_date="2026-01-01")
        assert len(result) == 1
        assert result[0]["post_id"] == "2"

    def test_boundary_date_inclusive(self):
        posts = [
            {"published_at": "2026-01-01T00:00:00Z", "post_id": "edge"},
        ]
        result = filter_posts(posts, min_date="2026-01-01")
        assert len(result) == 1


class TestPydanticSchemaValidation:
    def test_valid_graph_extraction_result(self):
        data = {
            "entities": [
                {"id": "Иван Иванов", "type": "Person", "description": "Командир"},
                {
                    "id": "Штаб Тесла",
                    "type": "Organization",
                    "org_type": "hq",
                    "description": "Штаб СО КГЭУ",
                },
            ],
            "relationships": [
                {
                    "source_id": "Иван Иванов",
                    "target_id": "Штаб Тесла",
                    "relation": "MEMBER_OF",
                    "status": "active",
                }
            ],
        }
        result = GraphExtractionResult.model_validate(data)
        assert len(result.entities) == 2
        assert result.entities[0].type == EntityType.Person
        assert result.entities[1].org_type.value == "hq"
        assert result.relationships[0].relation == RelationType.MEMBER_OF

    def test_invalid_relation_type_raises_error(self):
        data = {
            "entities": [{"id": "X", "type": "Person"}],
            "relationships": [
                {
                    "source_id": "X",
                    "target_id": "Y",
                    "relation": "INVALID_RELATION",
                }
            ],
        }
        with pytest.raises(ValidationError):
            GraphExtractionResult.model_validate(data)

    def test_invalid_entity_type_raises_error(self):
        data = {
            "entities": [{"id": "X", "type": "Alien"}],
            "relationships": [],
        }
        with pytest.raises(ValidationError):
            GraphExtractionResult.model_validate(data)

    def test_empty_result_is_valid(self):
        result = GraphExtractionResult()
        assert result.entities == []
        assert result.relationships == []


class TestSaveToNeo4jMock:
    def test_save_entities_and_relationships(self):
        mock_driver = MagicMock()
        mock_session = MagicMock()
        mock_driver.session.return_value.__enter__.return_value = mock_session

        result = GraphExtractionResult(
            entities=[
                Entity(id="Alice", type=EntityType.Person),
                Entity(
                    id="Org",
                    type=EntityType.Organization,
                    org_type="hq",
                ),
            ],
            relationships=[
                Relationship(
                    source_id="Alice",
                    target_id="Org",
                    relation=RelationType.MEMBER_OF,
                    role_title="Командир",
                )
            ],
        )

        save_to_neo4j(mock_driver, result, source_model="gigachat")

        assert mock_session.run.call_count == 3

        entity_calls = mock_session.run.call_args_list[0:2]
        assert all("MERGE (n:Entity {merge_key: $merge_key})" in c[0][0] for c in entity_calls)
        assert entity_calls[0][1]["merge_key"] == "gigachat::Alice"
        assert entity_calls[1][1]["merge_key"] == "gigachat::Org"

        rel_call = mock_session.run.call_args_list[2]
        assert "MERGE (a)-[r:RELATES {type: $rel, source_model: $model}]->(b)" in rel_call[0][0]
        assert rel_call[1]["src_key"] == "gigachat::Alice"
        assert rel_call[1]["tgt_key"] == "gigachat::Org"
        # verify props include role_title
        props = rel_call[1]["props"]
        assert props["role_title"] == "Командир"
        assert props["status"] == "active"


class TestExtractGraphErrorHandling:
    @patch("backend.indexer.extractors.logger")
    def test_api_error_returns_empty_result(self, mock_logger):
        mock_client = MagicMock()
        mock_client.chat.completions.create.side_effect = Exception("API Error")

        post = {
            "post_id": "42",
            "text_clean": "Some post text about event",
        }

        result = extract_graph_from_post(post, mock_client)

        assert isinstance(result, GraphExtractionResult)
        assert result.entities == []
        assert result.relationships == []
        mock_logger.exception.assert_called_once()

    @patch("backend.indexer.extractors.logger")
    def test_empty_text_returns_empty_result(self, mock_logger):
        mock_client = MagicMock()
        post = {"post_id": "42", "text_clean": ""}

        result = extract_graph_from_post(post, mock_client)

        assert result.entities == []
        assert result.relationships == []
        mock_client.chat.completions.create.assert_not_called()

    @patch("backend.indexer.extractors.logger")
    def test_malformed_json_response_handled(self, mock_logger):
        mock_client = MagicMock()
        mock_response = MagicMock()
        mock_response.choices[0].message.content = "{invalid json}"
        mock_client.chat.completions.create.return_value = mock_response

        post = {
            "post_id": "99",
            "text_clean": "Valid text here",
        }

        result = extract_graph_from_post(post, mock_client)

        assert isinstance(result, GraphExtractionResult)
        assert result.entities == []
        mock_logger.exception.assert_called_once()


class TestBuildPostPrompt:
    def test_includes_all_metadata(self):
        post = {
            "post_id": "1",
            "group_name": "Тесла",
            "published_at": "2026-06-01T10:00:00Z",
            "post_url": "https://vk.com/test",
            "hashtags": ["РСО", "ТеслаTeam"],
            "mentions": [
                {"id": "id123", "name": "Иван", "raw": "[id123|Иван]"}
            ],
            "text_clean": "Отличный день!",
        }
        prompt = build_post_prompt(post)
        assert "Group: Тесла" in prompt
        assert "Published: 2026-06-01T10:00:00Z" in prompt
        assert "URL: https://vk.com/test" in prompt
        assert "Hashtags: РСО, ТеслаTeam" in prompt
        assert "Mentions: Иван" in prompt
        assert "Отличный день!" in prompt

    def test_missing_fields_omitted(self):
        post = {"post_id": "2", "text_clean": "Просто текст"}
        prompt = build_post_prompt(post)
        assert "--- POST METADATA ---" in prompt
        assert "Group:" not in prompt
        assert "Mentions:" not in prompt
        assert "Просто текст" in prompt

    def test_empty_mentions_omitted(self):
        post = {
            "post_id": "3",
            "mentions": [],
            "text_clean": "Без упоминаний",
        }
        prompt = build_post_prompt(post)
        assert "Mentions:" not in prompt

    @patch("backend.indexer.extractors.logger")
    def test_llm_receives_enriched_prompt(self, mock_logger):
        mock_extractor = MagicMock()
        mock_extractor.extract_json.return_value = {
            "entities": [],
            "relationships": [],
        }
        mock_extractor._model = None

        post = {
            "post_id": "42",
            "group_name": "Тесла",
            "published_at": "2026-06-15T10:00:00Z",
            "post_url": "https://vk.com/test",
            "text_clean": "Пост про мероприятие",
        }
        extract_graph_from_post(post, mock_extractor)

        call_args = mock_extractor.extract_json.call_args
        user_msg = call_args[0][1]
        assert "Group: Тесла" in user_msg
        assert "URL: https://vk.com/test" in user_msg
        assert "Пост про мероприятие" in user_msg


class TestBuildEmbeddingText:
    def test_includes_group_name(self):
        post = {
            "group_name": "Студенческие отряды КГЭУ «Тесла»",
            "text_clean": "Всем привет!",
        }
        result = build_embedding_text(post)
        assert result == "Студенческие отряды КГЭУ «Тесла»: Всем привет!"

    def test_no_group_fallback(self):
        post = {"text_clean": "Только текст"}
        result = build_embedding_text(post)
        assert result == "Только текст"

    def test_empty_text(self):
        post = {"group_name": "Группа", "text_clean": ""}
        result = build_embedding_text(post)
        assert result == "Группа: "
