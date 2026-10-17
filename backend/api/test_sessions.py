from datetime import datetime, timedelta, timezone

import pytest

from backend.api.sessions import SessionStore, hash_token


@pytest.fixture
def store(tmp_path):
    s = SessionStore(db_path=str(tmp_path / "sessions.db"), ttl_days=30)
    yield s
    s.close()


def test_create_stores_hash_not_token(store, tmp_path):
    created = store.create("user")
    assert created["token"]
    assert created["role"] == "user"
    assert created["expires_at"]

    import sqlite3

    conn = sqlite3.connect(str(tmp_path / "sessions.db"))
    row = conn.execute("SELECT token_hash FROM sessions").fetchone()
    conn.close()
    assert row[0] == hash_token(created["token"])
    assert row[0] != created["token"]


def test_create_returns_ttl_expiry(store):
    created = store.create("admin")
    expires = datetime.fromisoformat(created["expires_at"])
    now = datetime.now(timezone.utc)
    assert timedelta(days=29) < expires - now < timedelta(days=31)


def test_verify_valid_token(store):
    created = store.create("user")
    session = store.verify(created["token"])
    assert session is not None
    assert session["role"] == "user"


def test_verify_invalid_token_returns_none(store):
    assert store.verify("not-a-real-token") is None
    assert store.verify("") is None
    assert store.verify(None) is None


def test_verify_expired_token_returns_none(tmp_path):
    expired_store = SessionStore(db_path=str(tmp_path / "expired.db"), ttl_days=0)
    created = expired_store.create("user")
    assert expired_store.verify(created["token"]) is None
    expired_store.close()


def test_revoke(store):
    created = store.create("user")
    assert store.verify(created["token"]) is not None
    assert store.revoke(created["token"]) is True
    assert store.verify(created["token"]) is None
    assert store.revoke(created["token"]) is False


def test_cleanup_removes_expired_only(store):
    fresh = store.create("user")
    import sqlite3

    now = datetime.now(timezone.utc)
    conn = store._conn
    conn.execute(
        "INSERT INTO sessions (token_hash, role, vk_user_id, created_at, expires_at) "
        "VALUES (?, ?, ?, ?, ?)",
        ("oldhash", "user", None, now.isoformat(), (now - timedelta(days=1)).isoformat()),
    )
    conn.commit()

    removed = store.cleanup()
    assert removed == 1
    assert store.verify(fresh["token"]) is not None


def test_verify_deletes_expired_row_on_hit(tmp_path):
    s = SessionStore(db_path=str(tmp_path / "lazy.db"), ttl_days=0)
    created = s.create("user")
    assert s.verify(created["token"]) is None
    import sqlite3

    conn = sqlite3.connect(str(tmp_path / "lazy.db"))
    count = conn.execute("SELECT COUNT(*) FROM sessions").fetchone()[0]
    conn.close()
    assert count == 0
    s.close()


def test_legacy_debug_admin_sessions_are_downgraded_and_new_roles_survive_restart(tmp_path, monkeypatch):
    import sqlite3

    import backend.api.sessions as sessions_module

    db_path = tmp_path / "legacy-sessions.db"
    now = datetime.now(timezone.utc)
    expires = (now + timedelta(days=30)).isoformat()
    legacy_admin_token = "old-debug-admin-token"
    legacy_user_token = "old-user-token"
    conn = sqlite3.connect(db_path)
    conn.execute(
        "CREATE TABLE sessions (token_hash TEXT PRIMARY KEY, role TEXT NOT NULL, vk_user_id TEXT, "
        "created_at TEXT NOT NULL, expires_at TEXT NOT NULL)"
    )
    conn.executemany(
        "INSERT INTO sessions(token_hash,role,vk_user_id,created_at,expires_at) VALUES(?,?,?,?,?)",
        [
            (hash_token(legacy_admin_token), "admin", None, now.isoformat(), expires),
            (hash_token(legacy_user_token), "user", None, now.isoformat(), expires),
        ],
    )
    conn.commit()
    conn.close()

    monkeypatch.setattr(sessions_module, "TESLA_ALL_ADMIN", True)
    migrated = SessionStore(db_path=str(db_path), ttl_days=30)
    assert migrated.verify(legacy_admin_token)["role"] == "user"
    assert migrated.verify(legacy_user_token)["role"] == "user"

    new_guest = migrated.create("user")
    new_admin = migrated.create("admin")
    assert new_guest["role"] == "user"
    assert new_admin["role"] == "admin"
    migrated.close()

    restarted = SessionStore(db_path=str(db_path), ttl_days=30)
    assert restarted.verify(legacy_admin_token)["role"] == "user"
    assert restarted.verify(new_guest["token"])["role"] == "user"
    assert restarted.verify(new_admin["token"])["role"] == "admin"
    auth_sources = {
        row["token_hash"]: row["auth_source"]
        for row in restarted._conn.execute("SELECT token_hash,auth_source FROM sessions")
    }
    assert auth_sources[hash_token(new_guest["token"])] == "guest"
    assert auth_sources[hash_token(new_admin["token"])] == "admin_key"
    restarted.close()
