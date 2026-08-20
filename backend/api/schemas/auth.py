from pydantic import BaseModel


class AuthResponse(BaseModel):
    token: str
    role: str
    vk_user_id: str | None = None
    expires_at: str


class AdminRequest(BaseModel):
    api_key: str


class VkRequest(BaseModel):
    params: dict[str, str]
    sign: str


class MeResponse(BaseModel):
    role: str
    vk_user_id: str | None = None
    expires_at: str


class LogoutResponse(BaseModel):
    ok: bool = True