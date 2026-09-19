from fastapi import APIRouter, Depends, HTTPException
from backend.api.auth import verify_admin_session_optional, verify_user_any
from backend.api.schemas.chat import CallWindow, ChatRequest, ChatResponse, PostPreview, SourceInfo
from backend.rag.searcher import GraphRAGSearcher
from backend.utils.logger import setup_logger

logger = setup_logger("chat_route")

router = APIRouter(dependencies=[Depends(verify_user_any)])
_searcher = None


def _get_searcher():
    global _searcher
    if _searcher is None:
        _searcher = GraphRAGSearcher()
    return _searcher


@router.post("/api/v1/chat", response_model=ChatResponse)
async def chat(
    body: ChatRequest,
    role: str = Depends(verify_user_any),
    admin: dict | None = Depends(verify_admin_session_optional),
):
    searcher = _get_searcher()
    # Панель «Рентген»: контекст только админу и только по запросу.
    # (Пока TESLA_ALL_ADMIN=1 все сессии админские — см. TEMP-метку.)
    want_context = bool(body.include_context and admin is not None)
    try:
        result = searcher.search(body.question, include_context=want_context)
        return ChatResponse(
            answer=result["answer"],
            sources=[SourceInfo(**s) for s in result["sources"]],
            media=result.get("media", []),
            previews=[PostPreview(**p) for p in (result.get("previews") or [])],
            mode=result.get("mode", "basic"),
            facts_count=result.get("facts_count", 0),
            posts_used=result.get("posts_used", 0),
            calls=[CallWindow(**c) for c in (result.get("calls") or [])]
            if want_context
            else None,
            trace_id=result.get("trace_id"),
        )
    except Exception as e:
        logger.error(f"Chat error: {e}")
        raise HTTPException(status_code=500, detail="Internal server error")
