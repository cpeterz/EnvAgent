from __future__ import annotations

from agently.builtins.tools import Browse

from news_collector.config import AppSettings

from .base import BrowseToolProtocol


class AgentlyBrowseTool(BrowseToolProtocol):
    def __init__(self, settings: AppSettings):
        self._tool = Browse(
            proxy=settings.browse.proxy or settings.proxy,
            enable_pyautogui=False,
            enable_playwright=settings.browse.enable_playwright,
            enable_bs4=True,
            response_mode=settings.browse.response_mode,
            max_content_length=settings.browse.max_content_length,
            min_content_length=settings.browse.min_content_length,
            playwright_headless=settings.browse.playwright_headless,
            timeout=settings.browse.timeout,
        )

    async def browse(self, url: str) -> str:
        result = await self._tool.browse(url)
        return str(result or "")


def create_browse_tool(settings: AppSettings) -> BrowseToolProtocol:
    return AgentlyBrowseTool(settings)
