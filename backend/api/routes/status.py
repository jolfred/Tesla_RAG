from fastapi import APIRouter
from backend.config import DOCUMENTS_DIR
from backend.api.schemas.common import StatusResponse
from backend.wiki import loop
from backend.wiki.prompts import canon_text

router = APIRouter()


@router.get("/api/v1/status", response_model=StatusResponse)
def status():
    errors = []
    try:
        pages_count = len(loop._pages())
        canon_text()
        if not pages_count:
            errors.append("Архив Летописи пока пуст.")
    except Exception as e:
        pages_count = 0
        errors.append(f"Wiki: {e}")
    doc_count = sum(1 for p in DOCUMENTS_DIR.iterdir() if p.is_file() and not p.name.startswith(".")) if DOCUMENTS_DIR.exists() else 0
    return StatusResponse(
        status="ok" if not errors else "degraded",
        mode="wiki",
        wiki_pages=pages_count,
        documents_count=doc_count,
        errors=errors,
    )
