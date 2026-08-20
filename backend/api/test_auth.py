import pytest
from fastapi.testclient import TestClient

from backend.api.sessions import store
from backend.main import app

client = TestClient(app)

ADMIN_KEY = "test-admin-key"
USER_KEY = "test-user-key"

VK_PARAMS = {
    "vk_app_id": "1",
    "vk_user_id": "123456789",
    "vk_is_app_user": "1",
    "vk_are_notifications_enabled": "1",
    "vk_language": "ru",
    "vk_access_token_settings": "",
    "vk_platform": "android",
    "vk_ref": "other",
}
# Тест-вектор: HMAC-SHA256("test_vk_secret", отсортированные пары VK_PARAMS),
# hex -> URL-энкодинг (FR-1.8, P-4).
VK_SIGN = "1f9cf3244f3fe64af0301fbdc9d003c7d5a20c155928757fd4e4b04177519d68"


@pytest.fixture(autouse=True)
def clean_sessions():
    store.clear()
    yield
    store.clear()


@pytest.fixture(autouse=True)
def test_config(monkeypatch):
    """Фиксируем конфиг независимо от порядка импорта .env."""
    monkeypatch.setattr("backend.api.auth.ADMIN_API_KEY", ADMIN_KEY)
    monkeypatch.setattr("backend.api.auth.USER_API_KEY", USER_KEY)
    monkeypatch.setattr("backend.api.routes.auth.ADMIN_API_KEY", ADMIN_KEY)
    monkeypatch.setattr("backend.api.routes.auth.VK_APP_ID", "app1")
    monkeypatch.setattr("backend.api.routes.auth.VK_APP_SECRET", "test_vk_secret")
    monkeypatch.setattr("backend.api.routes.auth.VK_ADMIN_IDS", {"123456789"})


class FakeSearcher:
    def search(self, question):
        return {
            "answer": "Ответ от тестового поисковика",
            "sources": [{"title": "Источник", "url": "https://vk.com/test"}],
            "media": [],
            "mode": "local",
            "facts_count": 1,
            "posts_used": 2,
        }


@pytest.fixture
def mock_searcher(monkeypatch):
    searcher = FakeSearcher()
    monkeypatch.setattr("backend.api.routes.chat._get_searcher", lambda: searcher)
    return searcher


# --- A-1 / A-2: гость, me, невалидный токен ---

def test_guest_flow():
    resp = client.post("/api/v1/auth/guest")
    assert resp.status_code == 200
    data = resp.json()
    assert data["role"] == "user"
    assert data["token"]
    assert data["expires_at"]

    me = client.get("/api/v1/auth/me", headers={"Authorization": f"Bearer {data['token']}"})
    assert me.status_code == 200
    me_data = me.json()
    assert me_data["role"] == "user"
    assert me_data["vk_user_id"] is None
    assert me_data["expires_at"] == data["expires_at"]


def test_me_with_invalid_token_401():
    resp = client.get("/api/v1/auth/me", headers={"Authorization": "Bearer fake-token"})
    assert resp.status_code == 401


def test_me_without_token_401():
    assert client.get("/api/v1/auth/me").status_code == 401


# --- A-3: админ-вход ---

def test_admin_correct_key():
    resp = client.post("/api/v1/auth/admin", json={"api_key": ADMIN_KEY})
    assert resp.status_code == 200
    assert resp.json()["role"] == "admin"


def test_admin_wrong_key_401():
    resp = client.post("/api/v1/auth/admin", json={"api_key": "wrong-key"})
    assert resp.status_code == 401


# --- A-4: logout ---

def test_logout_revokes_token():
    guest = client.post("/api/v1/auth/guest").json()
    headers = {"Authorization": f"Bearer {guest['token']}"}
    assert client.get("/api/v1/auth/me", headers=headers).status_code == 200
    assert client.post("/api/v1/auth/logout", headers=headers).status_code == 200
    assert client.get("/api/v1/auth/me", headers=headers).status_code == 401


# --- A-5 / A-6: /chat с Bearer и с X-API-Key ---

def test_chat_with_bearer_200(mock_searcher):
    guest = client.post("/api/v1/auth/guest").json()
    resp = client.post(
        "/api/v1/chat",
        json={"question": "Кто командует отрядом?"},
        headers={"Authorization": f"Bearer {guest['token']}"},
    )
    assert resp.status_code == 200
    data = resp.json()
    assert data["answer"]
    assert data["mode"] == "local"
    assert data["facts_count"] == 1
    assert data["posts_used"] == 2
    assert data["sources"][0]["url"] == "https://vk.com/test"


def test_chat_with_x_api_key_200(mock_searcher):
    resp = client.post(
        "/api/v1/chat",
        json={"question": "Тест"},
        headers={"X-API-Key": USER_KEY},
    )
    assert resp.status_code == 200
    assert resp.json()["answer"]


def test_chat_with_admin_api_key_200(mock_searcher):
    resp = client.post(
        "/api/v1/chat",
        json={"question": "Тест"},
        headers={"X-API-Key": ADMIN_KEY},
    )
    assert resp.status_code == 200


def test_chat_without_credentials_401(mock_searcher):
    resp = client.post("/api/v1/chat", json={"question": "Тест"})
    assert resp.status_code == 401


# --- A-7: VK sign ---

def test_vk_sign_correct_admin():
    resp = client.post("/api/v1/auth/vk", json={"params": VK_PARAMS, "sign": VK_SIGN})
    assert resp.status_code == 200
    data = resp.json()
    assert data["role"] == "admin"  # vk_user_id в allowlist
    assert data["vk_user_id"] == "123456789"


def test_vk_sign_correct_user_not_in_allowlist(monkeypatch):
    monkeypatch.setattr("backend.api.routes.auth.VK_ADMIN_IDS", set())
    params = dict(VK_PARAMS, vk_user_id="987654321")
    sign = "e508559584c372658ffbb9e5daeda707ffb00dbc2efee6b620ac2c7f9a7a445a"
    resp = client.post("/api/v1/auth/vk", json={"params": params, "sign": sign})
    assert resp.status_code == 200
    assert resp.json()["role"] == "user"


def test_vk_sign_forged_params_401():
    params = dict(VK_PARAMS, vk_user_id="000000000")
    resp = client.post("/api/v1/auth/vk", json={"params": params, "sign": VK_SIGN})
    assert resp.status_code == 401


def test_vk_sign_tampered_sign_401():
    resp = client.post(
        "/api/v1/auth/vk",
        json={"params": VK_PARAMS, "sign": VK_SIGN[:-1] + ("0" if VK_SIGN[-1] != "0" else "1")},
    )
    assert resp.status_code == 401


def test_vk_wrong_app_id_401():
    # Валидная подпись для params с vk_app_id=2, но приложение в конфиге app1 -> 401
    params = dict(VK_PARAMS, vk_app_id="2")
    sign = "ac7d892bb87062a278f76e971279b2f3295ca52f711080931031d1de9b5dcf88"
    resp = client.post("/api/v1/auth/vk", json={"params": params, "sign": sign})
    assert resp.status_code == 401


def test_vk_sign_missing_secret_501(monkeypatch):
    monkeypatch.setattr("backend.api.routes.auth.VK_APP_SECRET", "")
    resp = client.post("/api/v1/auth/vk", json={"params": VK_PARAMS, "sign": VK_SIGN})
    assert resp.status_code == 501