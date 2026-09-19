from pydantic import BaseModel


class ChatRequest(BaseModel):
    question: str
    history: list = []
    # Панель «Рентген» (только admin): вернуть секции контекста дословно.
    include_context: bool = False


class SourceInfo(BaseModel):
    title: str = ""
    url: str = ""


class CallWindow(BaseModel):
    """Одно окно панели «Рентген»: полный текст одного вызова модели."""

    title: str = ""
    text: str = ""


class PostPreview(BaseModel):
    """Превью VK-поста для лендинга: группа, дата, выдержка, первое фото."""

    group_name: str = ""
    published_at: str = ""
    text: str = ""
    photo: str = ""
    url: str = ""


class ChatResponse(BaseModel):
    answer: str
    sources: list[SourceInfo] = []
    media: list[str] = []
    preview: PostPreview | None = None
    mode: str = "basic"
    facts_count: int = 0
    posts_used: int = 0
    calls: list[CallWindow] | None = None
    trace_id: str | None = None
