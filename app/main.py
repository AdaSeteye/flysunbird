import os
import logging
from pathlib import Path

from fastapi import FastAPI, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles
from fastapi.responses import RedirectResponse, JSONResponse

from app.core.config import settings
from app.api.v1.api import api_router

logger = logging.getLogger(__name__)

app = FastAPI(title=settings.APP_NAME)

# CORS: use CORS_ORIGINS from env in production; in dev allow any localhost port
_default_origins = [
    "http://127.0.0.1:8080", "http://localhost:8080",
    "http://127.0.0.1:8090", "http://localhost:8090",
]
if settings.CORS_ORIGINS and settings.CORS_ORIGINS.strip():
    _origins = [o.strip() for o in settings.CORS_ORIGINS.split(",") if o.strip()]
    app.add_middleware(
        CORSMiddleware,
        allow_origins=_origins,
        allow_credentials=True,
        allow_methods=["*"],
        allow_headers=["*"],
    )
else:
    # Dev: allow any localhost/127.0.0.1 port so frontend on 8090, 3000, etc. works
    app.add_middleware(
        CORSMiddleware,
        allow_origin_regex=r"^https?://(localhost|127\.0\.0\.1)(:\d+)?$",
        allow_credentials=True,
        allow_methods=["*"],
        allow_headers=["*"],
    )

app.include_router(api_router)


def _cors_headers(origin: str | None) -> dict:
    """Headers so browser allows the response when origin is localhost."""
    if origin and ("localhost" in origin or "127.0.0.1" in origin):
        return {
            "Access-Control-Allow-Origin": origin,
            "Access-Control-Allow-Credentials": "true",
            "Access-Control-Allow-Methods": "*",
            "Access-Control-Allow-Headers": "*",
        }
    return {}


@app.exception_handler(Exception)
async def add_cors_on_exception(request: Request, exc: Exception):
    """Ensure 5xx and unhandled errors still send CORS so the client can read the error."""
    logger.exception("Unhandled exception: %s", exc)
    origin = request.headers.get("origin")
    headers = _cors_headers(origin)
    return JSONResponse(
        status_code=500,
        content={"detail": "Internal server error", "error": str(exc)},
        headers=headers,
    )


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
