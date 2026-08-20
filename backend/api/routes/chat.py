from fastapi import APIRouter, HTTPException
from backend.api.schemas.chat import ChatRequest, ChatResponse, SourceInfo
from backend.rag.searcher import GraphRAGSearcher
from backend.utils.logger import setup_logger

logger = setup_logger("chat_route")

router = APIRouter()
_searcher = None


def _get_searcher():
    global _searcher
    if _searcher is None:
        _searcher = GraphRAGSearcher()
    return _searcher


@router.post("/api/v1/chat", response_model=ChatResponse)
async def chat(body: ChatRequest):
    searcher = _get_searcher()
    try:
        result = searcher.search(body.question)
        return ChatResponse(
            answer=result["answer"],
            sources=[SourceInfo(**s) for s in result["sources"]],
            media=result.get("media", []),
            mode=result.get("mode", "basic"),
            facts_count=result.get("facts_count", 0),
            posts_used=result.get("posts_used", 0),
        )
    except Exception as e:
        logger.error(f"Chat error: {e}")
        raise HTTPException(status_code=500, detail="Internal server error")
