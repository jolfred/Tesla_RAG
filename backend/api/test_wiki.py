"""Тесты публичного Wiki API: каталог, поиск, чтение, граф (только локальные .md)."""
from fastapi.testclient import TestClient

from backend.main import app

client = TestClient(app)


def test_pages_lists_yunost_with_title():
    r = client.get("/api/v1/wiki/pages")
    assert r.status_code == 200
    pages = r.json()["pages"]
    assert len(pages) >= 100
    yunost = next(p for p in pages if p["slug"] == "lso/spo_yunost")
    assert "Юность" in yunost["title"]


def test_search_finds_yunost():
    r = client.get("/api/v1/wiki/search", params={"q": "Юность командир 2024"})
    assert r.status_code == 200
    body = r.json()
    assert body["status"] == "success"
    assert any("yunost" in i["slug"] for i in body["items"])


def test_page_read_ok_and_bad_slug_404():
    r = client.get("/api/v1/wiki/page", params={"slug": "lso/spo_yunost"})
    assert r.status_code == 200
    body = r.json()
    assert body["status"] == "success" and "Юность" in body["markdown"]
    assert body["links"]
    assert client.get("/api/v1/wiki/page", params={"slug": "../backend/config"}).status_code == 404
    assert client.get("/api/v1/wiki/page", params={"slug": "no/such_page"}).status_code == 404


def test_graph_nodes_edges_consistent():
    r = client.get("/api/v1/wiki/graph")
    assert r.status_code == 200
    body = r.json()
    slugs = {n["slug"] for n in body["nodes"]}
    assert len(slugs) >= 100
    assert body["edges"]
    for e in body["edges"]:
        assert e["source"] in slugs and e["target"] in slugs
