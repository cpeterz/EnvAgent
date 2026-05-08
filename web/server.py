from __future__ import annotations

import logging
from pathlib import Path

from fastapi import FastAPI
from fastapi.staticfiles import StaticFiles
from fastapi.templating import Jinja2Templates

from news_collector.config import AppSettings

WEB_DIR = Path(__file__).parent


def create_app(*, settings: AppSettings, root_dir: Path, logger: logging.Logger) -> FastAPI:
    app = FastAPI(title="环境新闻查询Agent", version="1.0.0")

    app.state.settings = settings
    app.state.root_dir = root_dir
    app.state.logger = logger
    app.state.collector = None
    app.state.active_task = None

    app.mount("/static", StaticFiles(directory=WEB_DIR / "static"), name="static")

    templates = Jinja2Templates(directory=WEB_DIR / "templates")
    app.state.templates = templates

    from .routes import router
    app.include_router(router)

    return app
