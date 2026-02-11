# backend/app/main.py
from pathlib import Path

from fastapi import FastAPI
from fastapi.responses import FileResponse
from fastapi.staticfiles import StaticFiles

from backend.app.api.run import router as run_router
from backend.app.api.secrets import router as secrets_router
from backend.app.api.drafts import router as drafts_router

app = FastAPI(title="inbox-copilot API")
app.include_router(run_router, prefix="/api")
app.include_router(secrets_router, prefix="/api")
app.include_router(drafts_router, prefix="/api")

repo_root = Path(__file__).resolve().parents[2]
frontend_dist = repo_root / "frontend" / "dist"

if frontend_dist.exists():
    app.mount("/static", StaticFiles(directory=frontend_dist), name="static")

    @app.get("/", include_in_schema=False)
    def index() -> FileResponse:
        return FileResponse(frontend_dist / "index.html")

    @app.get("/{path:path}", include_in_schema=False)
    def spa_fallback(_path: str) -> FileResponse:
        return FileResponse(frontend_dist / "index.html")
