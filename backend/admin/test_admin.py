"""Тесты админки (моковые, сервисы не нужны): слаги, namespace, доки, валидация API."""

import pytest
from fastapi.testclient import TestClient

from backend.admin import projects as _projects
from backend.admin.db import get_connection, init_admin_db
from backend.admin.indexing import load_doc_posts, project_collection, project_source_model
from backend.api.sessions import store
from backend.main import app


@pytest.fixture()
def db(tmp_path, monkeypatch):
    import backend.admin.db as dbmod
    import backend.admin.indexing as idxmod
    import backend.admin.jobs as jobsmod
    import backend.api.routes.admin as admmod

    path = tmp_path / "admin.db"
    orig_conn = dbmod.get_connection
    orig_init = dbmod.init_admin_db

    def _conn(*a: object, **k: object) -> object:
        return orig_conn(path)

    def _init(_path: object = None) -> object:
        return orig_init(path)

    for mod in (dbmod, idxmod, jobsmod, admmod):
        monkeypatch.setattr(mod, "get_connection", _conn, raising=False)
        monkeypatch.setattr(mod, "init_admin_db", _init, raising=False)
    monkeypatch.setattr(dbmod, "ADMIN_DB", path)
    init_admin_db(path)
    return path


@pytest.fixture()
def client(db):
    token = store.create("admin")["token"]
    return TestClient(app, headers={"Authorization": f"Bearer {token}"})


def test_slug_validation(db):
    conn = get_connection(db)
    with pytest.raises(ValueError):
        _projects.create_project(conn, "BAD SLUG!", "x", "")
    conn.close()


def test_project_crud_api(client):
    assert client.post("/api/v1/admin/projects", json={"slug": "a"}).status_code == 201
    assert client.post("/api/v1/admin/projects", json={"slug": "a"}).status_code == 400
    assert client.post("/api/v1/admin/projects", json={"slug": "??"}).status_code == 400
    assert client.get("/api/v1/admin/projects/none").status_code == 404
    assert client.delete("/api/v1/admin/projects/a").json() == {"ok": True}


def test_index_validation(client):
    client.post("/api/v1/admin/projects", json={"slug": "p"})
    # пустой проект
    assert client.post("/api/v1/admin/projects/p/index", json={}).status_code == 400
    # нет проекта
    assert client.post("/api/v1/admin/projects/none/index", json={}).status_code == 404
    client.post(
        "/api/v1/admin/projects/p/items",
        json={"item_type": "vk_group", "item_id": "rso_tesla"},
    )
    assert client.post("/api/v1/admin/projects/p/index", json={"model": "x"}).status_code == 400


def test_namespace_names():
    assert project_source_model("shtab") == "proj_shtab"
    assert project_collection("shtab") == "posts_proj_shtab"


def test_load_doc_posts(tmp_path, monkeypatch):
    import backend.admin.indexing as idxmod

    d = tmp_path / "docs"
    d.mkdir()
    (d / "a1.txt").write_text("текст документа " * 100, encoding="utf-8")
    (d / "b2.pdf").write_bytes(b"%PDF")
    monkeypatch.setattr(idxmod, "DOCUMENTS_DIR", d)
    posts = load_doc_posts(["a1", "b2", "missing"])
    assert len(posts) == 1
    assert posts[0]["post_url"] == "doc://a1"
    assert posts[0]["published_at"]
