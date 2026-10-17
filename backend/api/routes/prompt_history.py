"""Admin API for effective Wiki prompts and revision history."""
from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException

from backend.admin import prompts
from backend.admin.prompts import PromptRevisionConflict
from backend.api.auth import verify_admin_session

router = APIRouter()


def _one(key: str) -> dict:
    try:
        result = prompts.effective_prompt(key)
        result["history"] = prompts.prompt_history(key)
        return result
    except ValueError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc


@router.get("/api/v1/admin/prompt-history")
async def list_prompt_history(_: dict = Depends(verify_admin_session)) -> dict:
    return {"prompts": [_one(key) for key in prompts.KEYS]}


@router.get("/api/v1/admin/prompt-history/{key}")
async def get_prompt_history(key: str, _: dict = Depends(verify_admin_session)) -> dict:
    return _one(key)


@router.put("/api/v1/admin/prompt-history/{key}")
async def update_prompt_history(key: str, body: dict, _: dict = Depends(verify_admin_session)) -> dict:
    try:
        item = prompts.save_prompt(key, body.get("text", ""), body.get("expected_revision", ""), body.get("reason", ""))
        item["history"] = prompts.prompt_history(key)
        return item
    except PromptRevisionConflict as exc:
        raise HTTPException(status_code=409, detail={"message": "prompt revision conflict", "current_revision": exc.current_revision}) from exc
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc


@router.post("/api/v1/admin/prompt-history/{key}/restore")
async def restore_prompt_history(key: str, body: dict, _: dict = Depends(verify_admin_session)) -> dict:
    try:
        item = prompts.restore_prompt(key, int(body.get("history_id", 0)), body.get("expected_revision", ""), body.get("reason", ""))
        item["history"] = prompts.prompt_history(key)
        return item
    except PromptRevisionConflict as exc:
        raise HTTPException(status_code=409, detail={"message": "prompt revision conflict", "current_revision": exc.current_revision}) from exc
    except KeyError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    except (ValueError, TypeError) as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
