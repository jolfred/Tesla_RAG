import json
import uuid
from fastapi import APIRouter, HTTPException, UploadFile, File, Form
from backend.config import DOCUMENTS_DIR
from backend.api.schemas.documents import DocumentUploadResponse
from backend.utils.logger import setup_logger

logger = setup_logger("documents_route")

router = APIRouter()


@router.post("/api/v1/documents/upload", response_model=DocumentUploadResponse)
async def upload_document(file: UploadFile = File(...), title: str = Form(None)):
    DOCUMENTS_DIR.mkdir(parents=True, exist_ok=True)

    content = await file.read()
    fname = file.filename or "untitled"
    ext = fname.rsplit(".", 1)[-1].lower() if "." in fname else ""

    if ext not in ("pdf", "docx", "txt", "json"):
        raise HTTPException(status_code=400, detail=f"Unsupported format: .{ext}")

    doc_id = str(uuid.uuid4())
    save_name = f"{doc_id}.{ext}"
    save_path = DOCUMENTS_DIR / save_name

    with open(save_path, "wb") as f:
        f.write(content)

    doc_title = title or fname

    # Parse JSON metadata for title
    if ext == "json":
        try:
            data = json.loads(content)
            doc_title = data.get("title") or data.get("id") or doc_title
        except Exception:
            pass

    logger.info(f"Uploaded {save_name} ({len(content)} bytes)")

    return DocumentUploadResponse(id=doc_id, title=doc_title, status="uploaded")
