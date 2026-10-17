"""Authenticated manual editing; no provider calls or compiler operations."""
import hashlib
from fastapi import APIRouter, Depends, HTTPException, Query
from pydantic import BaseModel, Field

from backend.api.auth import verify_admin_session
from backend.wiki import loop
from backend.wiki.editorial_store import EditorialConflict, EditorialStore

router = APIRouter(prefix="/api/v1/editorial", dependencies=[Depends(verify_admin_session)])


def _store() -> EditorialStore:
    return EditorialStore(loop.WIKI_DIR)


def _actor(session: dict) -> str:
    if session.get("vk_user_id"):
        return "VK " + str(session["vk_user_id"])
    # A stable session label, without storing a bearer token or accepting a
    # caller-controlled name as the immutable audit identity.
    fingerprint = hashlib.sha256(str(session.get("token", "")).encode()).hexdigest()[:8]
    return "Редактор " + fingerprint


def _call(method: str, *args, **kwargs):
    try:
        return getattr(_store(), method)(*args, **kwargs)
    except EditorialConflict as exc:
        raise HTTPException(status_code=409, detail=str(exc)) from exc
    except KeyError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    except ValueError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc


class DraftBody(BaseModel):
    slug: str = Field(max_length=200)
    markdown: str = Field(max_length=2_000_000)
    expected_revision: str
    expected_draft_revision: str | None = Field(...)
    reason: str = Field(default="", max_length=2000)
    actor: str = Field(default="Редактор", max_length=150)


class PublishBody(BaseModel):
    slug: str = Field(max_length=200)
    markdown: str = Field(max_length=2_000_000)
    expected_revision: str
    reason: str = Field(min_length=1, max_length=2000)
    actor: str = Field(default="Редактор", max_length=150)


class RestoreBody(BaseModel):
    slug: str
    version_id: str
    expected_revision: str
    reason: str = Field(min_length=1, max_length=2000)
    actor: str = Field(default="Редактор", max_length=150)


class DiscussionBody(BaseModel):
    page: str
    title: str = Field(min_length=1, max_length=200)
    text: str = Field(min_length=1, max_length=50000)
    category: str = "editorial_note"
    owner: str = Field(default="", max_length=150)
    actor: str = Field(default="Редактор", max_length=150)


class DiscussionChange(BaseModel):
    status: str | None = None
    category: str | None = None
    owner: str | None = Field(default=None, max_length=150)
    resolution: str | None = Field(default=None, max_length=50000)
    expected_updated_at: str = Field(min_length=1)


class CommentBody(BaseModel):
    text: str = Field(min_length=1, max_length=50000)
    actor: str = Field(default="Редактор", max_length=150)


class ExcerptBody(BaseModel):
    item_id: str
    line_start: int = Field(ge=1)
    line_end: int = Field(ge=1)


@router.get("/articles")
def articles(q: str = Query(default="", max_length=200)):
    return {"articles": _call("articles", q)}


@router.get("/article")
def article(slug: str):
    return _call("article", slug)


@router.put("/draft")
def draft(body: DraftBody, session: dict = Depends(verify_admin_session)):
    return {"ok": True, "draft": _call("save_draft", **body.model_dump(exclude={"actor"}), actor=_actor(session))}


@router.post("/publish")
def publish(body: PublishBody, session: dict = Depends(verify_admin_session)):
    return _call("publish", **body.model_dump(exclude={"actor"}), actor=_actor(session))


@router.get("/history")
def history(slug: str):
    return {"versions": _call("history", slug)}


@router.get("/history/{version_id}")
def version(version_id: str, slug: str):
    return _call("version", slug, version_id)


@router.post("/restore")
def restore(body: RestoreBody, session: dict = Depends(verify_admin_session)):
    return _call("restore", **body.model_dump(exclude={"actor"}), actor=_actor(session))


@router.get("/discussions")
def discussions(slug: str = "", status: str = ""):
    return {"discussions": _call("discussions", slug, status)}


@router.post("/discussions", status_code=201)
def add_discussion(body: DiscussionBody, session: dict = Depends(verify_admin_session)):
    return {"discussion": _call("add_discussion", **body.model_dump(exclude={"actor"}), actor=_actor(session))}


@router.patch("/discussions/{discussion_id}")
def update_discussion(discussion_id: str, body: DiscussionChange, session: dict = Depends(verify_admin_session)):
    return {"discussion": _call("update_discussion", discussion_id, body.model_dump(exclude_none=True), actor=_actor(session))}


@router.post("/discussions/{discussion_id}/comments", status_code=201)
def add_comment(discussion_id: str, body: CommentBody, session: dict = Depends(verify_admin_session)):
    return {"discussion": _call("comment", discussion_id, **body.model_dump(exclude={"actor"}), actor=_actor(session))}


@router.post("/source-excerpts", status_code=201)
def publish_source_excerpt(body: ExcerptBody, session: dict = Depends(verify_admin_session)):
    from backend.admin.operations import get_inbox_item
    item = get_inbox_item(body.item_id)
    if item is None:
        raise HTTPException(status_code=404, detail="Материал не найден")
    return _call("source_excerpt", item, body.line_start, body.line_end, _actor(session))
