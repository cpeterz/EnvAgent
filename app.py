#!/usr/bin/env python3
import sys
from pathlib import Path

ROOT_DIR = Path(__file__).parent.resolve()
sys.path.insert(0, str(ROOT_DIR))

from dotenv import find_dotenv, load_dotenv

load_dotenv(find_dotenv())

from news_collector.config import AppSettings
from news_collector.logging_utils import configure_logging
from web.server import create_app


def main():
    settings = AppSettings.load(ROOT_DIR / "SETTINGS.yaml")
    logger = configure_logging(debug=settings.debug, log_dir=ROOT_DIR / "logs")
    logger.info("Starting Env News Agent...")
    logger.info("Web server: http://%s:%d", settings.web.host, settings.web.port)

    app = create_app(settings=settings, root_dir=ROOT_DIR, logger=logger)

    import uvicorn
    uvicorn.run(app, host=settings.web.host, port=settings.web.port, log_level="info")


if __name__ == "__main__":
    main()
