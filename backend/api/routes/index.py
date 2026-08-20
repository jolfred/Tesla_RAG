from fastapi import APIRouter
from backend.api.schemas.common import IndexResponse
from backend.rag.pipeline import process_all_documents
from backend.utils.logger import setup_logger

logger = setup_logger("index_route")

router = APIRouter()


@router.post("/api/v1/index/rebuild", response_model=IndexResponse)
async def rebuild_index():
    try:
        result = process_all_documents()
        return IndexResponse(
            status="ok",
            processed=result["processed"],
            errors=result["errors"],
            total_processed=result["total_processed"],
            total_errors=result["total_errors"],
        )
    except Exception as e:
        logger.error(f"Index rebuild failed: {e}")
        return IndexResponse(
            status="error",
            errors=[{"error": str(e)}],
        )
