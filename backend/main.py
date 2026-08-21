from fastapi import FastAPI, Depends, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse
from fastapi.staticfiles import StaticFiles
from backend.api.auth import verify_user
from backend.api.routes import auth, chat, communities, documents, status
from backend.config import FRONTEND_DIST
from backend.utils.logger import setup_logger

logger = setup_logger("api")

app = FastAPI(
    title="GraphRAG API — Штаб Тесла",
    description="API сервиса GraphRAG для цифровой платформы Штаба СО КГЭУ «Тесла»",
    version="1.0.0",
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Public endpoints
app.include_router(status.router, tags=["status"])
app.include_router(auth.router, tags=["auth"])

# User-protected endpoints (Bearer-токен ИЛИ X-API-Key, FR-1.6)
app.include_router(chat.router, tags=["chat"])

# Admin-protected endpoints
from backend.api.auth import verify_admin
app.include_router(documents.router, dependencies=[Depends(verify_admin)], tags=["documents"])
app.include_router(communities.router, dependencies=[Depends(verify_admin)], tags=["graph"])

# Frontend: статические ассеты (FR-2.2)
_ASSETS_DIR = FRONTEND_DIST / "assets"
if _ASSETS_DIR.is_dir():
    app.mount("/assets", StaticFiles(directory=_ASSETS_DIR), name="assets")

INDEX_HTML = FRONTEND_DIST / "index.html"


@app.get("/{full_path:path}")
async def spa_fallback(full_path: str):
    """SPA-fallback (FR-2.2): не-API GET-пути -> index.html."""
    if full_path.startswith("api/") or full_path in ("docs", "openapi.json", "redoc"):
        raise HTTPException(status_code=404, detail="Not found")
    if INDEX_HTML.exists():
        return FileResponse(INDEX_HTML)
    if full_path == "":
        return {"service": "GraphRAG API — Штаб Тесла", "version": "1.0.0"}
    raise HTTPException(status_code=404, detail="Not found")