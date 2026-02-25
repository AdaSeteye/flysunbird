import os
from pathlib import Path

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles
from fastapi.responses import RedirectResponse

from app.core.config import settings
from app.api.v1.api import api_router

app = FastAPI(title=settings.APP_NAME)

# CORS: use CORS_ORIGINS from env in production; default to localhost for dev
_default_origins = [
    "http://127.0.0.1:8080", "http://localhost:8080",
    "http://127.0.0.1:8090", "http://localhost:8090",
]
_origins = [o.strip() for o in settings.CORS_ORIGINS.split(",") if o.strip()] if settings.CORS_ORIGINS else _default_origins
app.add_middleware(
    CORSMiddleware,
    allow_origins=_origins,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

app.include_router(api_router)


@app.get("/health")
def health():
    return {"status": "ok"}


# Serve frontend (ops_console) so one Render URL = API + UI
_ops_console = Path(__file__).resolve().parent.parent / "ops_console"
if _ops_console.is_dir():
    @app.get("/")
    def _root():
        return RedirectResponse(url="/login.html")

    app.mount("/", StaticFiles(directory=str(_ops_console), html=True), name="ops_console")
