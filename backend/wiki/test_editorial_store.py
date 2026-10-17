"""Editorial guarantees: source preservation, private drafts, CAS and recovery."""
import json
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from backend.wiki.editorial_store import EditorialConflict, EditorialStore


@pytest.fixture
def wiki(tmp_path):
    root = tmp_path / "wiki"
    (root / "hq").mkdir(parents=True)
    (root / "hq/tesla.md").write_text('# Тесла\n\nИсходный факт. [Источник](https://example.org/source)\n', encoding="utf-8")
    (root / "_sources.json").write_text("{}", encoding="utf-8")
    return root


def test_draft_is_private_and_preserves_published_file(wiki):
    store = EditorialStore(wiki)
    original = store.article("hq/tesla")
    draft = store.save_draft("hq/tesla", "# Тесла\n\nТолько в черновике", original["revision"], None)
    assert (wiki / "hq/tesla.md").read_text() == original["markdown"]
    assert store.article("hq/tesla")["draft"]["revision"] == draft["revision"]
    assert store.articles()[0]["has_draft"] is True
    from backend.wiki import loop
    saved = loop.WIKI_DIR
    try:
        loop.WIKI_DIR = wiki
        assert "Только в черновике" not in json.dumps(loop.wiki_search("Только черновике"), ensure_ascii=False)
    finally:
        loop.WIKI_DIR = saved
    assert store.db.stat().st_mode & 0o777 == 0o600
    assert store.private.stat().st_mode & 0o777 == 0o700


def test_publish_and_restore_keep_every_version(wiki):
    store = EditorialStore(wiki)
    initial = store.article("hq/tesla")
    text = "# Тесла\n\nНовая проверенная редакция."
    store.save_draft("hq/tesla", text, initial["revision"], None)
    published = store.publish("hq/tesla", text, initial["revision"], "Проверены источники", "Автор")
    assert store.article("hq/tesla")["draft"] is None
    history = store.history("hq/tesla")
    assert len(history) == 2
    assert history[0]["actor"] == "Автор" and history[0]["is_current"]
    before = next(v for v in history if v["sha256"] == initial["revision"])
    store.restore("hq/tesla", before["id"], published["revision"], "Возврат исходного текста", "Редактор")
    assert (wiki / "hq/tesla.md").read_text() == initial["markdown"]
    assert len(store.history("hq/tesla")) == 3
    assert store.history("hq/tesla")[0]["kind"] == "restore"
    assert sum(v["is_current"] for v in store.history("hq/tesla")) == 1


def test_stale_page_and_stale_draft_cannot_overwrite(wiki):
    store = EditorialStore(wiki)
    article = store.article("hq/tesla")
    first = store.save_draft("hq/tesla", "# Тесла\n\nПервый черновик", article["revision"], None)
    with pytest.raises(EditorialConflict):
        store.save_draft("hq/tesla", "# Тесла\n\nВторая вкладка", article["revision"], None)
    store.publish("hq/tesla", "# Тесла\n\nНовая версия", article["revision"], "Уточнение")
    with pytest.raises(EditorialConflict):
        store.publish("hq/tesla", "# Тесла\n\nЗатереть новую версию", article["revision"], "Устаревшая вкладка")
    assert store.article("hq/tesla")["draft"]["revision"] == first["revision"]


def test_failed_write_preserves_original_and_backup(wiki, monkeypatch):
    import backend.wiki.editorial_store as module
    store = EditorialStore(wiki)
    before = store.article("hq/tesla")
    write = module._atomic_write
    def fail(*_args):
        raise OSError("disk full")
    monkeypatch.setattr(module, "_atomic_write", fail)
    with pytest.raises(OSError):
        store.publish("hq/tesla", "# Тесла\n\nНовое", before["revision"], "Изменение")
    assert store.article("hq/tesla")["markdown"] == before["markdown"]
    pending = next(v for v in store.history("hq/tesla") if v["publication_state"] == "pending")
    assert pending["is_current"] is False
    candidate = store.version("hq/tesla", pending["id"])
    assert candidate["markdown"].endswith("# Тесла\n\nНовое\n")
    assert candidate["publication_state"] == "pending"

    monkeypatch.setattr(module, "_atomic_write", write)
    restored = store.restore("hq/tesla", pending["id"], before["revision"], "Повтор публикации", "Автор")
    assert store.article("hq/tesla")["revision"] == restored["revision"]
    assert "Новое" in store.article("hq/tesla")["markdown"]


def test_failed_new_article_is_listed_with_pending_history_for_recovery(wiki, monkeypatch):
    import backend.wiki.editorial_store as module
    store = EditorialStore(wiki)
    markdown = "# Новое событие\n\nПодтверждённое описание. [Источник](https://example.org/event)"
    write = module._atomic_write
    def fail(*_args):
        raise OSError("disk full")
    monkeypatch.setattr(module, "_atomic_write", fail)
    with pytest.raises(OSError):
        store.publish("events/new_event", markdown, "", "Создание")

    listed = next(item for item in store.articles() if item["slug"] == "events/new_event")
    assert listed["status"] == "pending"
    assert listed["revision"] == ""
    assert listed["has_pending"] is True
    article = store.article("events/new_event")
    assert article["markdown"] == ""
    assert article["revision"] == ""
    assert article["sources"] == []
    assert article["title"] == "Новое событие"
    pending = store.history("events/new_event")[0]
    assert pending["publication_state"] == "pending"
    assert pending["is_current"] is False
    assert store.version("events/new_event", pending["id"])["markdown"].endswith(
        "# Новое событие\n\nПодтверждённое описание. [Источник](https://example.org/event)\n"
    )

    monkeypatch.setattr(module, "_atomic_write", write)
    store.restore("events/new_event", pending["id"], "", "Повтор публикации", "Автор")
    assert store.article("events/new_event")["markdown"]


def test_external_edit_is_captured_in_history(wiki):
    store = EditorialStore(wiki)
    original = store.article("hq/tesla")
    external = "# Тесла\n\nПравка вне кабинета\n"
    (wiki / "hq/tesla.md").write_text(external)
    with pytest.raises(EditorialConflict):
        store.publish("hq/tesla", "# Тесла\n\nУстаревшая правка", original["revision"], "Правка")
    current = store.article("hq/tesla")
    store.publish("hq/tesla", "# Тесла\n\nСогласованная правка", current["revision"], "Проверка внешнего изменения")
    assert any(store.version("hq/tesla", v["id"])["markdown"] == external for v in store.history("hq/tesla"))


@pytest.mark.parametrize("slug", ["../outside", "_editorial/private", "hq/../../secret", "hq/log", "hq/agents", "/etc/passwd", "hq//tesla"])
def test_private_and_outside_paths_are_rejected(wiki, slug):
    with pytest.raises(ValueError):
        EditorialStore(wiki).article(slug)


def test_symlink_escape_is_rejected(wiki, tmp_path):
    outside = tmp_path / "outside.md"
    outside.write_text("# Secret")
    (wiki / "hq/escape.md").symlink_to(outside)
    with pytest.raises(ValueError):
        EditorialStore(wiki).article("hq/escape")


def test_new_draft_and_invalid_links(wiki):
    store = EditorialStore(wiki)
    store.save_draft("events/new_event", "# Событие\n\n[[hq/tesla|Штаб]]", "", None)
    assert store.article("events/new_event")["revision"] == ""
    assert any(p["slug"] == "events/new_event" for p in store.articles())
    with pytest.raises(ValueError, match="Нет связанных статей"):
        store.publish("events/new_event", "# Событие\n\n[[persons/missing]]", "", "Публикация")
    store.publish("events/new_event", "# Событие\n\n[[hq/tesla|Штаб]]", "", "Проверена связь")
    assert store.article("events/new_event")["markdown"].startswith("---\nslug: events/new_event")


def test_legacy_discussions_import_without_turning_everything_into_questions(wiki):
    private = wiki / "_editorial"
    private.mkdir()
    entries = [{"id": "a", "page": "hq/tesla", "original_text": "Данных о фамилии нет", "status": "review"},
               {"id": "b", "page": "hq/tesla", "original_text": "Противоречие дат в двух источниках", "status": "review"}]
    (private / "issues.json").write_text(json.dumps(entries))
    store = EditorialStore(wiki)
    items = {r["id"]: r for r in store.discussions()}
    assert items["a"]["category"] == "editorial_note"
    assert items["b"]["category"] == "source_conflict"
    assert all(r["status"] == "waiting_editor" for r in items.values())
    assert len(store.discussions()) == 2


def test_discussion_decision_is_persisted_and_cas_protected(wiki):
    store = EditorialStore(wiki)
    issue = store.add_discussion("hq/tesla", "Переименование", "Какой год?", "curator_question")
    comment = store.comment(issue["id"], "Год уточняется", "Хранитель")
    with pytest.raises(EditorialConflict):
        store.update_discussion(issue["id"], {"expected_updated_at": issue["updated_at"], "resolution": "Рано"})
    with pytest.raises(ValueError):
        store.update_discussion(issue["id"], {"status": "resolved", "resolution": ""})
    result = store.update_discussion(issue["id"], {"expected_updated_at": comment["updated_at"], "status": "resolved", "resolution": "Есть первоисточник"}, "Хранитель")
    again = EditorialStore(wiki).discussions()[0]
    assert result["status"] == again["status"] == "resolved"
    assert again["comments"][-1]["actor"] == "Хранитель"
    assert "Есть первоисточник" not in (wiki / "hq/tesla.md").read_text()


@pytest.fixture
def client(wiki, tmp_path, monkeypatch):
    from backend.api import auth
    from backend.api.sessions import SessionStore
    from backend.main import app
    from backend.wiki import loop
    sessions = SessionStore(str(tmp_path / "sessions.db"))
    monkeypatch.setattr(auth, "store", sessions)
    monkeypatch.setattr(loop, "WIKI_DIR", wiki)
    token = sessions.create("admin")["token"]
    with TestClient(app) as http:
        http.headers["Authorization"] = "Bearer " + token
        yield http
    sessions.close()


def test_api_auth_and_server_controlled_audit_actor(client):
    current = client.get("/api/v1/editorial/article", params={"slug": "hq/tesla"}).json()
    result = client.post("/api/v1/editorial/publish", json={"slug": "hq/tesla", "markdown": "# Тесла\n\nПроверенный текст", "expected_revision": current["revision"], "reason": "Проверка", "actor": "Поддельное имя"})
    assert result.status_code == 200, result.text
    versions = client.get("/api/v1/editorial/history", params={"slug": "hq/tesla"}).json()["versions"]
    assert versions[0]["actor"].startswith("Редактор ") and versions[0]["actor"] != "Поддельное имя"
    client.headers.pop("Authorization")
    assert client.get("/api/v1/editorial/articles").status_code == 401
    assert client.get("/api/v1/editorial/discussions").status_code == 401


def test_api_requires_draft_and_published_base_revisions(client):
    assert client.put("/api/v1/editorial/draft", json={"slug": "hq/tesla", "markdown": "# Тесла"}).status_code == 422
    assert client.post("/api/v1/editorial/publish", json={"slug": "hq/tesla", "markdown": "# Тесла", "expected_revision": "outdated", "reason": "Проверка"}).status_code == 409


def test_only_selected_document_excerpt_becomes_public(wiki):
    from backend.wiki.archive import source_text
    item = {"source_kind": "document", "external_id": "document:abc-123", "title": "Положение",
            "text": "Публичный пункт\nЕщё один пункт\nЧастное приложение", "published_at": None}
    store = EditorialStore(wiki)
    excerpt = store.source_excerpt(item, 1, 2, "Редактор")
    public = source_text(excerpt["reference"], wiki)
    assert "Публичный пункт" in public and "Ещё один пункт" in public
    assert "Частное приложение" not in public
    assert "Дата публикации в архиве: не указана" in public
    assert source_text("document:arbitrary-file", wiki) is None
    assert store.source_excerpt(item, 1, 2, "Редактор")["reference"] == excerpt["reference"]


def test_interruption_after_atomic_write_is_recovered_without_duplicate_version(wiki, monkeypatch):
    import backend.wiki.editorial_store as module
    store = EditorialStore(wiki)
    before = store.article("hq/tesla")
    write = module._atomic_write
    def interrupted(path, text):
        write(path, text)
        raise OSError("process interrupted after file replacement")
    monkeypatch.setattr(module, "_atomic_write", interrupted)
    with pytest.raises(OSError):
        store.publish("hq/tesla", "# Тесла\n\nСохранённый новый текст", before["revision"], "Правка")
    assert "Сохранённый новый текст" in store.article("hq/tesla")["markdown"]
    assert len(store.history("hq/tesla")) == 2


def test_restore_archive_from_merged_alias_uses_canonical_address(wiki, tmp_path):
    import io
    import tarfile
    from backend.wiki.editorial_snapshots import import_snapshots
    (wiki / "hq/index.md").write_text('---\nredirect_to: hq/tesla\n---\n')
    old = '---\nslug: hq/index\nkind: hq\n---\n\n# Штаб\n\nСтарая проверенная версия\n'
    archive = tmp_path / "before.tar.gz"
    with tarfile.open(archive, "w:gz") as tar:
        member = tarfile.TarInfo("wiki/hq/index.md")
        member.size = len(old.encode())
        tar.addfile(member, io.BytesIO(old.encode()))
    import_snapshots(wiki, [archive])
    store = EditorialStore(wiki)
    revision = store.article("hq/tesla")["revision"]
    version = next(v for v in store.history("hq/tesla") if v["kind"] == "archive")
    store.restore("hq/tesla", version["id"], revision, "Возврат архивной версии", "Редактор")
    restored = store.article("hq/tesla")["markdown"]
    assert "Старая проверенная версия" in restored and "slug: hq/tesla" in restored
    assert store.version("hq/tesla", version["id"])["markdown"] == old
