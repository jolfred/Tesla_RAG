import hmac

from fastapi import APIRouter, Depends, HTTPException

from backend.api.auth import verify_user_session, verify_vk_sign
from backend.api.schemas.auth import (
    AdminRequest,
    AuthResponse,
    LogoutResponse,
    MeResponse,
    VkRequest,
)
from backend.api.sessions import store
from backend.config import ADMIN_API_KEY, VK_ADMIN_IDS, VK_APP_ID, VK_APP_SECRET
from backend.utils.logger import setup_logger

logger = setup_logger("auth_route")

router = APIRouter()


@router.post("/api/v1/auth/guest", response_model=AuthResponse)
async def auth_guest():
    """Вход без учётных данных (FR-1.1)."""
    return AuthResponse(**store.create("user"))


@router.post("/api/v1/auth/admin", response_model=AuthResponse)
async def auth_admin(body: AdminRequest):
    """Вход админа по ADMIN_API_KEY (FR-1.2)."""
    if not hmac.compare_digest(body.api_key, ADMIN_API_KEY):
        raise HTTPException(status_code=401, detail="Invalid API key")
    return AuthResponse(**store.create("admin"))


@router.post("/api/v1/auth/vk", response_model=AuthResponse)
async def auth_vk(body: VkRequest):
    """VK-вход с проверкой подписи launch-параметров (FR-1.8)."""
    if not VK_APP_SECRET:
        raise HTTPException(status_code=501, detail="VK auth is not configured")
    if not verify_vk_sign(body.params, body.sign, VK_APP_SECRET):
        raise HTTPException(status_code=401, detail="Invalid VK signature")
    expected_app_id = str(VK_APP_ID).removeprefix("app")
    if expected_app_id and str(body.params.get("vk_app_id", "")) != expected_app_id:
        raise HTTPException(status_code=401, detail="Invalid VK app id")
    vk_user_id = body.params.get("vk_user_id")
    role = "admin" if vk_user_id in VK_ADMIN_IDS else "user"
    return AuthResponse(**store.create(role, vk_user_id))


@router.get("/api/v1/auth/me", response_model=MeResponse)
async def auth_me(session: dict = Depends(verify_user_session)):
    """Информация о текущей сессии (FR-1.3)."""
    return MeResponse(
        role=session["role"],
        vk_user_id=session["vk_user_id"],
        expires_at=session["expires_at"],
    )


@router.post("/api/v1/auth/logout", response_model=LogoutResponse)
async def auth_logout(session: dict = Depends(verify_user_session)):
    """Отзыв токена (FR-1.4)."""
    store.revoke(session["token"])
    return LogoutResponse(ok=True)