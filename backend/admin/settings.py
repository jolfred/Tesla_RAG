"""API-ключи из админки: хранение в admin.db, применение без рестарта.

Значения наружу не отдаём — только is_set. Пустое значение = удалить
override (откат к .env). Проверка — один дешёвый запрос на ключ.
"""

from __future__ import annotations

from backend.admin.db import get_connection, init_admin_db
from backend.admin.secrets import drop_cache, get_secret

MANAGED_KEYS = (
    "GIGACHAT_AUTH_KEY",
    "PROXYAPI_KEY",
    "GOOGLE_AI_STUDIO_KEY",
    "VK_SERVICE_TOKEN",
    "VK_SERVICE_TOKEN1",
    "NEO4J_PASS",
)

TITLES = {
    "GIGACHAT_AUTH_KEY": "GigaChat (ответы, граф, сообщества)",
    "PROXYAPI_KEY": "ProxyAPI (эмбеддинги text-embedding-3-small)",
    "GOOGLE_AI_STUDIO_KEY": "Google AI Studio (режим gemma)",
    "VK_SERVICE_TOKEN": "VK service token (парсер)",
    "VK_SERVICE_TOKEN1": "VK service token запасной (парсер)",
    "NEO4J_PASS": "Neo4j пароль",
}


def list_settings() -> list[dict]:
    init_admin_db()
    conn = get_connection()
    try:
        rows = {r["key"]: True for r in conn.execute("SELECT key FROM settings WHERE value <> ''")}
    finally:
        conn.close()
    return [
        {
            "key": k,
            "title": TITLES[k],
            "in_db": k in rows,
            "in_env": bool(__import__("os").getenv(k)),
        }
        for k in MANAGED_KEYS
    ]


def set_setting(key: str, value: str) -> None:
    if key not in MANAGED_KEYS:
        raise ValueError(f"unknown key: {key}")
    init_admin_db()
    conn = get_connection()
    try:
        if (value or "").strip():
            conn.execute(
                "INSERT INTO settings (key, value, updated_at) VALUES (?, ?, datetime('now')) "
                "ON CONFLICT(key) DO UPDATE SET value = excluded.value, updated_at = datetime('now')",
                (key, value.strip()),
            )
        else:
            conn.execute("DELETE FROM settings WHERE key = ?", (key,))
        conn.commit()
    finally:
        conn.close()
    drop_cache(key)


def check_setting(key: str) -> dict:
    """Дешёвая проверка ключа. Возвращает {ok, info}."""
    if key not in MANAGED_KEYS:
        raise ValueError(f"unknown key: {key}")
    try:
        if key == "GIGACHAT_AUTH_KEY":
            from backend.utils.gigachat_client import GigaChatClient

            token = GigaChatClient()._fetch_token()
            return {"ok": bool(token), "info": "OAuth токен получен"}
        if key == "PROXYAPI_KEY":
            from openai import OpenAI

            base = get_secret(
                "PROXYAPI_BASE_URL", "https://openai.api.proxyapi.ru/v1"
            )
            models = OpenAI(base_url=base, api_key=get_secret("PROXYAPI_KEY")).models.list()
            return {"ok": True, "info": f"моделей доступно: {len(models.data)}"}
        if key == "GOOGLE_AI_STUDIO_KEY":
            from openai import OpenAI

            from backend.config import GEMMA_BASE_URL

            models = OpenAI(
                base_url=GEMMA_BASE_URL, api_key=get_secret("GOOGLE_AI_STUDIO_KEY")
            ).models.list()
            return {"ok": True, "info": f"моделей доступно: {len(models.data)}"}
        if key in ("VK_SERVICE_TOKEN", "VK_SERVICE_TOKEN1"):
            import json
            import urllib.parse
            import urllib.request

            token = get_secret(key)
            if not token:
                return {"ok": False, "info": "ключ не задан"}
            qs = urllib.parse.urlencode(
                {"group_ids": "rso_tesla", "fields": "members_count", "v": "5.199",
                 "access_token": token}
            )
            with urllib.request.urlopen(
                f"https://api.vk.com/method/groups.getById?{qs}", timeout=15
            ) as resp:
                data = json.load(resp)
            if "response" in data:
                return {"ok": True, "info": f"группа: {data['response'][0].get('name', '?')}"}
            return {"ok": False, "info": str(data.get("error", data))[:200]}
        if key == "NEO4J_PASS":
            from neo4j import GraphDatabase

            from backend.config import NEO4J_URI, NEO4J_USER

            driver = GraphDatabase.driver(
                NEO4J_URI,
                auth=(NEO4J_USER, get_secret("NEO4J_PASS", "tesla_neo4j")),
                connection_timeout=5,
                max_transaction_retry_time=5,
            )
            try:
                with driver.session() as s:
                    s.run("RETURN 1").single()
            finally:
                driver.close()
            return {"ok": True, "info": "подключение успешно"}
    except Exception as e:
        return {"ok": False, "info": str(e)[:300]}
    return {"ok": False, "info": "неизвестный ключ"}
