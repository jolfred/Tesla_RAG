from fastapi import HTTPException, Security
from fastapi.security import APIKeyHeader
from backend.config import ADMIN_API_KEY, USER_API_KEY
from backend.utils.logger import setup_logger

logger = setup_logger("auth")

api_key_header = APIKeyHeader(name="X-API-Key", auto_error=False)


def verify_user(api_key: str = Security(api_key_header)) -> str:
    if api_key == ADMIN_API_KEY:
        return "admin"
    if api_key == USER_API_KEY:
        return "user"
    raise HTTPException(status_code=401, detail="Invalid or missing API key")


def verify_admin(api_key: str = Security(api_key_header)) -> str:
    if api_key == ADMIN_API_KEY:
        return "admin"
    raise HTTPException(status_code=403, detail="Admin access required")
