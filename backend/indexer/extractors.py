from openai import OpenAI

from backend.indexer.logger import setup_indexer_logger
from backend.indexer.prompts import SYSTEM_PROMPT, build_post_prompt
from backend.indexer.schemas import GraphExtractionResult
from backend.utils.gemma_client import GemmaClient
from backend.utils.gigachat_client import GigaChatClient

logger = setup_indexer_logger()


class OpenAIExtractor:
    def __init__(self, client: OpenAI, model: str = "openai/gpt-4o-mini"):
        self._client = client
        self._model = model

    def extract_json(self, system_prompt: str, text: str, **kwargs) -> dict:
        response = self._client.chat.completions.create(
            model=self._model,
            messages=[
                {"role": "system", "content": system_prompt},
                {"role": "user", "content": text},
            ],
            response_format={"type": "json_object"},
            temperature=0.1,
            max_tokens=4096,
        )
        raw = response.choices[0].message.content.strip()
        return GraphExtractionResult.model_validate_json(raw).model_dump()


def build_extractor(provider: str, openai_client: OpenAI):
    if provider == "gigachat":
        return GigaChatClient()
    if provider == "gemma":
        return GemmaClient()
    return OpenAIExtractor(openai_client)


def extract_graph_from_post(
    post: dict, extractor
) -> GraphExtractionResult:
    text = post.get("text_clean", "")
    if not text:
        logger.warning("Post %s has empty text_clean, skipping extraction", post.get("post_id"))
        return GraphExtractionResult()

    try:
        data = extractor.extract_json(
            SYSTEM_PROMPT, build_post_prompt(post), model=getattr(extractor, "_model", None) or None
        )
        result = GraphExtractionResult.model_validate(data)
        logger.info(
            "Extracted %d entities and %d relationships from post %s",
            len(result.entities),
            len(result.relationships),
            post.get("post_id"),
        )
        return result
    except Exception:
        logger.exception("Failed to extract graph from post %s", post.get("post_id"))
        return GraphExtractionResult()
