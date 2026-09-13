"""Извлечение графа через LLMGraphTransformer (онтология v2, GigaChat).

Пайплайн:
  VK-пост -> Document(page_content, metadata) -> transformer.convert_to_graph_documents
  -> GraphDocument -> sanitize (writer-v2) -> Neo4j.

Покрытие provenance (source_post_url/date) НЕ зависит от LLM:
writer-v2 дописывает их из metadata поста.
"""

import inspect

from backend.config import GIGACHAT_MODEL
from backend.indexer.graph_schema_v2 import (
    ALLOWED_NODES,
    ALLOWED_RELATIONSHIPS,
    NODE_PROPERTIES,
    RELATIONSHIP_PROPERTIES,
)
from backend.indexer.logger import setup_indexer_logger
from backend.indexer.posts import build_embedding_text

logger = setup_indexer_logger()

# Промпт с grounding-правилами и антипримерами (лечит "словарные" описания).
# Подставляется в LLMGraphTransformer, если версия это позволяет
# (параметр prompt / additional_instructions — проверяем через inspect).
RCO_INSTRUCTIONS = """You extract a knowledge graph about Russian student labor squads (РСО, Штаб СО КГЭУ «Тесла») from VK posts.

STRICT RULES:
1. Use ONLY the allowed node labels and relationship types. When in doubt about a type, drop the node.
2. NEVER create nodes for: dates, money amounts, seasons (лето/зима), hashtags, generic words (команда, ребята, гости, мероприятие, конкурс).
3. 'description' of a node MUST paraphrase THIS post only. Encyclopedia/world knowledge is FORBIDDEN.
   - BAD: Казанка -> "Река в Казани". GOOD: Казанка -> "место субботника ССО Заряд 12.07" or null.
   - BAD: Person -> "Гость мероприятия". GOOD: drop the node if the post says nothing specific.
   - If there is nothing post-specific to say, return null description, never generic words.
4. Write descriptions in the SAME language as the post (posts are in Russian - answer in Russian).
5. A person squad (отряд: ССО, СПО, СОП, ОСД, ССервО...) is a Squad, NOT a generic Organization.
6. Ranks/roles of people (командир, комиссар, боец) go to HOLDS_ROLE with role_title, not to generic MEMBER_OF.
7. Keep entity names EXACTLY as in the post, with original spacing and quotes. NEVER concatenate words into CamelCase.
8. Every relationship MUST be one of the allowed triples (head type, relation, tail type), e.g. Person-MEMBER_OF->Squad, Squad-PART_OF->Organization, Person-WON_AWARD->Award, Squad-WON_AWARD->Award (a squad as a whole can win an award).
9. Squad is ONLY for student labor squads (отряды: ССО, СПО, СОП, ОСД, ССервО, СМО, ШСО...). Corporate/partner teams, banks, companies (e.g. ЭкоБарсы, Ак Барс Банк) are Organization, NEVER Squad — even if the post calls them "команда".
10. Schools, camps, shifts and gatherings (Школа кандидатов и бойцов/ШКБ, «Погружение», школы актива, смены, слёты, лагеря) are Event, NOT Organization — even when they have a name and a VK group. E.g. 'VI Школа кандидатов и бойцов «Погружение»' -> Event.

Allowed node labels: Person, Squad, Organization, Event, Project, Award, Location, Role, Profession.
Allowed relationships: HOLDS_ROLE, MEMBER_OF, COMMANDED, WON_AWARD, PARTICIPATED_IN, PART_OF, ORGANIZED, HELD_AT, LOCATED_IN, TRAINED_IN, SUPPORTED_BY.
"""


def build_llm(provider: str = "gigachat"):
    """LangChain BaseChatModel под провайдера. temperature=0: экстракция детерминирована."""
    if provider == "gigachat":
        import os

        from langchain_gigachat import GigaChat
        from pydantic import BaseModel

        class TolerantGigaChat(GigaChat):
            """GigaChat, терпимый к схемам без description.

            langchain-neo4j передаёт в with_structured_output внутренний _Graph
            без docstring, а GigaChat API требует description у функции.
            Подставляем дефолтное — сам фреймворк не трогаем.
            """

            _DEFAULT_TOOL_DESC = (
                "Extract knowledge graph nodes and relationships "
                "about student labor squads from the post."
            )

            def with_structured_output(self, schema, **kwargs):
                if (
                    isinstance(schema, type)
                    and issubclass(schema, BaseModel)
                    and not schema.model_json_schema().get("description")
                ):
                    schema = type(
                        schema.__name__,
                        (schema,),
                        {"__doc__": self._DEFAULT_TOOL_DESC},
                    )
                return super().with_structured_output(schema, **kwargs)

        return TolerantGigaChat(
            credentials=os.getenv("GIGACHAT_AUTH_KEY", ""),
            scope="GIGACHAT_API_PERS",
            model=GIGACHAT_MODEL,
            temperature=0.0,
            verify_ssl_certs=False,
            timeout=120,
            max_retries=2,
        )
    # proxyapi: OpenAI-совместимый endpoint через ProxyAPI-ключ.
    import os

    from langchain_openai import ChatOpenAI

    return ChatOpenAI(
        base_url=os.getenv("PROXYAPI_BASE_URL", "https://openai.api.proxyapi.ru/v1"),
        api_key=os.getenv("PROXYAPI_KEY", ""),
        model="openai/gpt-4o-mini",
        temperature=0.0,
    )


def _load_transformer_class():
    for mod, attr in [
        ("langchain_neo4j", "LLMGraphTransformer"),
        ("langchain_experimental.graph_transformers", "LLMGraphTransformer"),
        ("langchain_experimental.graph_transformers.llm", "LLMGraphTransformer"),
    ]:
        try:
            module = __import__(mod, fromlist=[attr])
            return getattr(module, attr)
        except (ImportError, AttributeError):
            continue
    raise ImportError(
        "LLMGraphTransformer not found: install langchain-neo4j or langchain-experimental"
    )


def build_transformer(llm, strict_mode: bool = True):
    """LLMGraphTransformer с онтологией v2. Кастомный промпт — если версия поддерживает."""
    cls = _load_transformer_class()
    params = set(inspect.signature(cls.__init__).parameters)
    kwargs: dict = {
        "llm": llm,
        "allowed_nodes": ALLOWED_NODES,
        "allowed_relationships": list(ALLOWED_RELATIONSHIPS),
        "strict_mode": strict_mode,
        "node_properties": NODE_PROPERTIES,
        "relationship_properties": RELATIONSHIP_PROPERTIES,
    }
    # Версии отличаются именем параметра для доп. инструкций — подхватываем любой.
    for key in ("additional_instructions", "prompt", "system_prompt"):
        if key in params:
            kwargs[key] = RCO_INSTRUCTIONS
            break
    else:
        logger.warning(
            "LLMGraphTransformer has no prompt-override param; "
            "RCO grounding rules NOT injected (%s)",
            sorted(params),
        )
    allowed = {k: v for k, v in kwargs.items() if k in params or k == "llm"}
    return cls(**allowed)


def posts_to_documents(posts: list[dict]):
    """VK-посты -> LangChain Documents с provenance в metadata."""
    from langchain_core.documents import Document

    docs = []
    for post in posts:
        text = post.get("text_clean", "")
        if not text:
            continue
        parts = [build_embedding_text(post)]
        if post.get("hashtags"):
            parts.append("Хэштеги: " + ", ".join(post["hashtags"]))
        mentions = post.get("mentions") or []
        names = [m.get("name", m.get("id", "")) for m in mentions if isinstance(m, dict)]
        if names:
            parts.append("Упоминания: " + ", ".join(names))
        docs.append(
            Document(
                page_content="\n".join(parts),
                metadata={
                    "post_url": post.get("post_url", ""),
                    "published_at": post.get("published_at", ""),
                    "group_name": post.get("group_name", ""),
                    "post_id": str(post.get("post_id", "")),
                },
            )
        )
    return docs


def _node_to_dict(node) -> dict:
    props = getattr(node, "properties", None) or {}
    if not isinstance(props, dict):
        props = {}
    return {
        "id": getattr(node, "id", ""),
        "type": getattr(node, "type", ""),
        "description": props.get("description"),
    }


def _rel_to_dict(rel) -> dict:
    def _endpoint(x):
        return x.id if hasattr(x, "id") else str(x)

    props = getattr(rel, "properties", None) or {}
    if not isinstance(props, dict):
        props = {}
    return {
        "source_id": _endpoint(getattr(rel, "source", "")),
        "target_id": _endpoint(getattr(rel, "target", "")),
        "relation": getattr(rel, "type", ""),
        "description": props.get("description"),
        "role_title": props.get("role_title"),
        "status": props.get("status") or "active",
    }


def extract_from_documents(
    transformer, docs: list, max_retries: int = 2
) -> list[tuple[dict, list[dict], list[dict]]]:
    """convert_to_graph_documents с ретраями (GigaChat рвёт JSON).

    Возвращает [(metadata, nodes, rels)] на каждый Document.
    """
    results = []
    for doc in docs:
        last_error: Exception | None = None
        for attempt in range(max_retries + 1):
            try:
                graph_docs = transformer.convert_to_graph_documents([doc])
                break
            except Exception as e:
                last_error = e
                logger.warning(
                    "Transformer failed for post %s (attempt %d/%d): %s",
                    doc.metadata.get("post_id"),
                    attempt + 1,
                    max_retries + 1,
                    e,
                )
        else:
            logger.exception(
                "Transformer gave up on post %s: %s",
                doc.metadata.get("post_id"),
                last_error,
            )
            results.append((doc.metadata, [], []))
            continue
        nodes, rels = [], []
        for gd in graph_docs:
            nodes.extend(_node_to_dict(n) for n in (gd.nodes or []))
            rels.extend(_rel_to_dict(r) for r in (gd.relationships or []))
        logger.info(
            "Extracted %d nodes, %d rels from post %s",
            len(nodes),
            len(rels),
            doc.metadata.get("post_id"),
        )
        results.append((doc.metadata, nodes, rels))
    return results
