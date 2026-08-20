from fastapi import FastAPI, Depends
from fastapi.middleware.cors import CORSMiddleware
from backend.api.auth import verify_user
from backend.api.routes import chat, communities, documents, index, status
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

# User-protected endpoints
app.include_router(chat.router, dependencies=[Depends(verify_user)], tags=["chat"])

# Admin-protected endpoints
from backend.api.auth import verify_admin
app.include_router(documents.router, dependencies=[Depends(verify_admin)], tags=["documents"])
app.include_router(index.router, dependencies=[Depends(verify_admin)], tags=["index"])
app.include_router(communities.router, dependencies=[Depends(verify_admin)], tags=["graph"])


@app.get("/")
async def root():
    return {"service": "GraphRAG API — Штаб Тесла", "version": "1.0.0"}
