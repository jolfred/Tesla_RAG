"""Admin source intake, collection jobs, inbox, and opt-in daily schedule."""
from __future__ import annotations

from fastapi import APIRouter, Depends, File, Form, HTTPException, Query, UploadFile

from backend.admin import operations as ops
from backend.api.auth import verify_admin_session

router = APIRouter(prefix="/api/v1/admin/operations", tags=["admin-operations"])


@router.get("/status")
async def operations_status(_: dict = Depends(verify_admin_session)) -> dict:
    return ops.status()


@router.get("/sources")
async def operations_sources(_: dict = Depends(verify_admin_session)) -> dict:
    return {"sources": ops.list_sources()}


@router.post("/sources/vk", status_code=201)
async def add_vk_source(body: dict, _: dict = Depends(verify_admin_session)) -> dict:
    try: return ops.add_vk_source(str(body.get("url") or ""))
    except ValueError as exc: raise HTTPException(status_code=400, detail=str(exc))


@router.post("/sources/vk-post", status_code=202)
async def add_vk_post_source(body: dict, _: dict = Depends(verify_admin_session)) -> dict:
    try:
        source, job = ops.create_vk_post_source(str(body.get("url") or ""))
        return {"source": source, "job": job}
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc))


@router.post("/documents/{doc_id}/prepare", status_code=201)
async def prepare_document(doc_id: str, _: dict = Depends(verify_admin_session)) -> dict:
    try: return ops.prepare_document(doc_id)
    except FileNotFoundError as exc: raise HTTPException(status_code=404, detail=str(exc))
    except ValueError as exc:
        status = 413 if "превышает лимит" in str(exc) else 422
        raise HTTPException(status_code=status, detail=str(exc))
    except Exception as exc:
        # Parser import/format errors are actionable source-processing failures.
        message = str(exc).replace(str(ops.DOCUMENTS_DIR), "[documents]").strip()
        detail = f"Не удалось извлечь текст ({type(exc).__name__})"
        if message:
            detail += f": {message[:300]}"
        raise HTTPException(status_code=422, detail=detail)


@router.post("/documents/upload", status_code=201)
async def upload_operations_document(file: UploadFile = File(...), title: str | None = Form(None),
                                    _: dict = Depends(verify_admin_session)) -> dict:
    try:
        # Read at most one byte beyond the documented limit, so a large upload
        # is rejected without buffering an unbounded request in memory.
        content = await file.read(ops.MAX_DOCUMENT_BYTES + 1)
        return ops.save_document_upload(file.filename or "untitled", content, title=title)
    except ValueError as exc:
        status = 413 if "превышает лимит" in str(exc) else 400
        raise HTTPException(status_code=status, detail=str(exc))


@router.get("/inbox")
async def operations_inbox(state: str | None = None, limit: int = Query(50, ge=1, le=200),
                           _: dict = Depends(verify_admin_session)) -> dict:
    try: return {"items": ops.list_inbox(state, limit)}
    except ValueError as exc: raise HTTPException(status_code=400, detail=str(exc))


@router.get("/inbox/{item_id}")
async def operations_inbox_item(item_id: str, _: dict = Depends(verify_admin_session)) -> dict:
    item = ops.get_inbox_item(item_id)
    if item is None: raise HTTPException(status_code=404, detail="inbox item not found")
    return item


@router.patch("/inbox/{item_id}")
async def update_inbox_item(item_id: str, body: dict, _: dict = Depends(verify_admin_session)) -> dict:
    try: item = ops.update_inbox_state(item_id, str(body.get("state") or ""))
    except ValueError as exc: raise HTTPException(status_code=400, detail=str(exc))
    if item is None: raise HTTPException(status_code=404, detail="inbox item not found")
    return item


@router.post("/jobs/vk-fetch", status_code=202)
async def enqueue_vk_fetch(body: dict, _: dict = Depends(verify_admin_session)) -> dict:
    try:
        limit = body.get("limit", 0)
        if isinstance(limit, bool) or not isinstance(limit, int): raise ValueError("limit должен быть целым числом")
        return ops.create_vk_job(str(body.get("source_id") or ""), limit)
    except KeyError: raise HTTPException(status_code=404, detail="VK source not found")
    except ValueError as exc: raise HTTPException(status_code=400, detail=str(exc))


@router.get("/jobs")
async def operations_jobs(limit: int = Query(50, ge=1, le=200), _: dict = Depends(verify_admin_session)) -> dict:
    return {"jobs": ops.list_jobs(limit)}


@router.get("/jobs/{job_id}")
async def operations_job(job_id: str, _: dict = Depends(verify_admin_session)) -> dict:
    job = ops.get_job(job_id)
    if job is None: raise HTTPException(status_code=404, detail="job not found")
    return job


@router.post("/jobs/{job_id}/retry", status_code=202)
async def retry_operations_job(job_id: str, _: dict = Depends(verify_admin_session)) -> dict:
    try: return ops.retry_job(job_id)
    except KeyError: raise HTTPException(status_code=404, detail="job not found")
    except ValueError as exc: raise HTTPException(status_code=409, detail=str(exc))


@router.get("/schedule")
async def operations_schedule(_: dict = Depends(verify_admin_session)) -> dict:
    return ops.get_schedule()


@router.put("/schedule")
async def update_operations_schedule(body: dict, _: dict = Depends(verify_admin_session)) -> dict:
    try:
        if not isinstance(body.get("enabled", False), bool): raise ValueError("enabled должен быть boolean")
        return ops.set_schedule(body.get("enabled", False), str(body.get("local_time", "08:00")),
                                str(body.get("timezone", "Europe/Moscow")), body.get("source_ids", []))
    except ValueError as exc: raise HTTPException(status_code=400, detail=str(exc))
