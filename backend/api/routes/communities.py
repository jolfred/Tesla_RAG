from fastapi import APIRouter
from backend.api.schemas.common import IndexResponse
from backend.scripts.build_communities import main as build_communities_main
from backend.utils.logger import setup_logger

logger = setup_logger("communities_route")

router = APIRouter()


@router.post("/api/v1/graph/communities/rebuild", response_model=IndexResponse)
async def rebuild_communities():
    try:
        build_communities_main()
        return IndexResponse(status="ok")
    except Exception as e:
        logger.error(f"Communities rebuild failed: {e}")
        return IndexResponse(status="error", errors=[{"error": str(e)}])