import hashlib
import hmac
from typing import Optional
from urllib.parse import quote, unquote

from fastapi import Depends, HTTPException, Security
from fastapi.security import APIKeyHeader

from backend.api.sessions import store
from backend.config import ADMIN_API_KEY, USER_API_KEY
from backend.utils.logger import setup_logger

logger = setup_logger("auth")

api_key_header = APIKeyHeader(name="X-API-Key", auto_error=False)
bearer_header = APIKeyHeader(name="Authorization", auto_error=False)

_BEARER_PREFIX = "Bearer "


def _extract_bearer(authorization: Optional[str]) -> Optional[str]:
    if not authorization or not authorization.startswith(_BEARER_PREFIX):
        return None
    token = authorization[len(_BEARER_PREFIX):].strip()
    return token or None


def get_bearer_token(authorization: str = Security(bearer_header)) -> Optional[str]:
    """Сырой Bearer-токен из заголовка Authorization (может быть None)."""
    return _extract_bearer(authorization)


def _verify_session(token: Optional[str]) -> Optional[dict]:
    session = store.verify(token)
    if session is None:
        raise HTTPException(status_code=401, detail="Invalid or expired token")
    session["token"] = token
    return session


def verify_user_session(token: Optional[str] = Depends(get_bearer_token)) -> dict:
    """Обязательный Bearer-токен (любая роль). 401 при отсутствии/истечении."""
    return _verify_session(token)


def verify_user_session_optional(
    token: Optional[str] = Depends(get_bearer_token),
) -> Optional[dict]:
    """Необязательный Bearer-токен: None, если нет/невалиден."""
    if token is None:
        return None
    session = store.verify(token)
    if session is None:
        return None
    session["token"] = token
    return session


def verify_admin_session(token: Optional[str] = Depends(get_bearer_token)) -> dict:
    """Обязательный Bearer-токен с ролью admin. Готов для admin-роутов (M2+)."""
    session = _verify_session(token)
    if session["role"] != "admin":
        raise HTTPException(status_code=403, detail="Admin access required")
    return session


def verify_admin_session_optional(
    token: Optional[str] = Depends(get_bearer_token),
) -> Optional[dict]:
    """Необязательный admin: dict сессии при admin-токене, иначе None (панель «Рентген»)."""
    if token is None:
        return None
    session = store.verify(token)
    if session is None or session.get("role") != "admin":
        return None
    session["token"] = token
    return session


def verify_user(api_key: str = Security(api_key_header)) -> str:
    """X-API-Key: USER или ADMIN ключ (обратная совместимость, CLI/curl/бенчмарк)."""
    if api_key and hmac.compare_digest(api_key, ADMIN_API_KEY):
        return "admin"
    if api_key and hmac.compare_digest(api_key, USER_API_KEY):
        return "user"
    raise HTTPException(status_code=401, detail="Invalid or missing API key")


def verify_admin(api_key: str = Security(api_key_header)) -> str:
    if api_key and hmac.compare_digest(api_key, ADMIN_API_KEY):
        return "admin"
    raise HTTPException(status_code=403, detail="Admin access required")


def verify_user_any(
    session: Optional[dict] = Depends(verify_user_session_optional),
    api_key: str = Security(api_key_header),
) -> str:
    """Для /chat: Bearer-токен ИЛИ X-API-Key (FR-1.6)."""
    if session is not None:
        return session["role"]
    return verify_user(api_key)


def verify_vk_sign(params: dict, sign: str, secret: str) -> bool:
    """Проверка подписи VK launch-параметров (FR-1.8, официальный алгоритм VK).

    Пары (кроме sign) URL-декодируются -> сортировка по ключу ->
    склейка k1=v1&k2=v2 -> HMAC-SHA256(secret) -> hex -> URL-энкодинг ->
    сравнение с sign через hmac.compare_digest. secret передаётся явно (значение
    из config контролирует роут).
    """
    if not secret:
        return False
    items = sorted(
        (unquote(str(k)), unquote(str(v)))
        for k, v in params.items()
        if k != "sign"
    )
    message = "&".join(f"{k}={v}" for k, v in items)
    digest = hmac.new(secret.encode("utf-8"), message.encode("utf-8"), hashlib.sha256)
    expected = quote(digest.hexdigest(), safe="")
    return hmac.compare_digest(expected, sign)