from collections.abc import AsyncGenerator
from contextlib import asynccontextmanager
from pathlib import Path

import uvicorn
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import HTMLResponse
from fastapi.staticfiles import StaticFiles

from app.api.api import api_router
from app.api.endpoints.interview import websocket_interview
from app.config.logging_config import setup_logging
from app.config.settings import settings
from app.system.exceptions import BaseHTTPException, common_exception_handler

setup_logging()

BASE_DIR = Path(__file__).resolve().parent.parent


@asynccontextmanager
async def lifespan(app: FastAPI) -> AsyncGenerator:
    yield


def prepare_app() -> FastAPI:
    app = FastAPI(
        title=settings.APP_NAME,
        description="Interview",
        version="1.0.0",
        lifespan=lifespan
    )

    app.add_middleware(
        CORSMiddleware,
        allow_origins=["*"],
        allow_credentials=True,
        allow_methods=["*"],
        allow_headers=["*"],
    )

    app.include_router(api_router, prefix="/api/v1")
    app.add_exception_handler(BaseHTTPException, common_exception_handler)
    app.websocket("/api/v1/interview/ws")(websocket_interview)

    static_dir = BASE_DIR / "app" / "static"
    if static_dir.exists():
        app.mount("/static", StaticFiles(directory=str(static_dir)), name="static")

    @app.get("/", response_class=HTMLResponse)
    async def get_index():
        html_path = BASE_DIR / "app" / "templates" / "index.html"
        if html_path.exists():
            return html_path.read_text(encoding="utf-8")
        return "<h1>AI-HR API</h1><p>Template not found</p>"

    return app


def start_service() -> None:
    uvicorn.run(
        prepare_app(),
        host=settings.APP_ADDRESS,
        port=settings.APP_PORT,
    )


app = prepare_app()

if __name__ == "__main__":
    start_service()
