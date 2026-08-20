from pydantic import BaseModel


class ChatRequest(BaseModel):
    question: str
    history: list = []


class SourceInfo(BaseModel):
    title: str = ""
    url: str = ""


class ChatResponse(BaseModel):
    answer: str
    sources: list[SourceInfo] = []
    media: list[str] = []
    mode: str = "basic"
    facts_count: int = 0
    posts_used: int = 0
