from pydantic import BaseModel


class ChatRequest(BaseModel):
    question: str
    history: list = []
    # Панель «Рентген» (только admin): вернуть секции контекста дословно.
    include_context: bool = False


class SourceInfo(BaseModel):
    title: str = ""
    url: str = ""


class ContextBlocks(BaseModel):
    """Секции контекста дословно как ушли в LLM (ключи — только непустые)."""

    graph: str | None = None
    source_posts: str | None = None
    posts: str | None = None
    communities: str | None = None


class ChatResponse(BaseModel):
    answer: str
    sources: list[SourceInfo] = []
    media: list[str] = []
    mode: str = "basic"
    facts_count: int = 0
    posts_used: int = 0
    context: ContextBlocks | None = None
