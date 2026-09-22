"""Публичный Wiki API Летописи: каталог, поиск, чтение, граф связей (только .md)."""
from fastapi import APIRouter, HTTPException, Query

from backend.wiki import loop

router = APIRouter()


@router.get("/api/v1/wiki/pages")
def pages():
    return {"pages": loop.wiki_graph()["nodes"]}


@router.get("/api/v1/wiki/search")
def search(q: str = Query(min_length=2), top_k: int = 5):
    return loop.wiki_search(q, max(1, min(top_k, 20)))


@router.get("/api/v1/wiki/page")
def page(slug: str, section: str = ""):
    r = loop.wiki_read(slug, section)
    if r.get("status") != "success":
        raise HTTPException(status_code=404, detail="page not found")
    return r


@router.get("/api/v1/wiki/graph")
def graph():
    return loop.wiki_graph()
