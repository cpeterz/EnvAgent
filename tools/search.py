from __future__ import annotations

import asyncio
import time
import threading
from typing import Any
from urllib.parse import quote_plus

import httpx
from bs4 import BeautifulSoup

from news_collector.config import AppSettings, SearchNewsTimeLimit

from .base import SearchToolProtocol

_MIN_INTERVAL = 4.0


class _EngineSession:
    def __init__(self, name: str):
        self.name = name
        self._client: httpx.Client | None = None
        self.blocked = False
        self.blocked_at = 0.0

    @property
    def client(self) -> httpx.Client:
        if self._client is None or self._client.is_closed:
            self._client = httpx.Client(
                timeout=30,
                follow_redirects=True,
                headers={
                    "User-Agent": (
                        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
                        "AppleWebKit/537.36 (KHTML, like Gecko) "
                        "Chrome/120.0.0.0 Safari/537.36"
                    ),
                    "Accept-Language": "zh-CN,zh;q=0.9,en;q=0.8",
                    "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
                },
            )
            self.blocked = False
        return self._client

    def mark_blocked(self) -> None:
        self.blocked = True
        self.blocked_at = time.monotonic()
        if self._client and not self._client.is_closed:
            try:
                self._client.close()
            except Exception:
                pass
        self._client = None

    def is_available(self) -> bool:
        if not self.blocked:
            return True
        return (time.monotonic() - self.blocked_at) > 300


class MultiEngineSearchTool(SearchToolProtocol):
    """Rotates between Sogou and 360 search with persistent sessions."""

    def __init__(self, settings: AppSettings):
        self._max_results = settings.search.max_results
        self._lock = threading.Lock()
        self._last_request_time = 0.0
        self._sogou = _EngineSession("sogou")
        self._so360 = _EngineSession("360")
        self._engines = [self._sogou, self._so360]
        self._next_engine = 0

    async def search_news(
        self,
        *,
        query: str,
        timelimit: SearchNewsTimeLimit,
        max_results: int,
    ) -> list[dict[str, Any]]:
        return await asyncio.to_thread(
            self._search_sync, query, timelimit, max_results
        )

    def _throttle(self) -> None:
        elapsed = time.monotonic() - self._last_request_time
        if elapsed < _MIN_INTERVAL:
            time.sleep(_MIN_INTERVAL - elapsed)

    def _search_sync(
        self, query: str, timelimit: SearchNewsTimeLimit, max_results: int,
    ) -> list[dict[str, Any]]:
        with self._lock:
            for attempt in range(len(self._engines)):
                idx = (self._next_engine + attempt) % len(self._engines)
                engine = self._engines[idx]
                if not engine.is_available():
                    continue

                self._throttle()
                self._next_engine = (idx + 1) % len(self._engines)

                try:
                    results = self._do_search(engine, query, max_results)
                finally:
                    self._last_request_time = time.monotonic()

                if results is not None:
                    return results

            return []

    def _do_search(
        self, engine: _EngineSession, query: str, max_results: int,
    ) -> list[dict[str, Any]] | None:
        q = quote_plus(query)

        if engine.name == "sogou":
            url = f"https://www.sogou.com/sogou?query={q}&ie=utf8"
        else:
            url = f"https://www.so.com/s?q={q}"

        try:
            resp = engine.client.get(url)
            resp.raise_for_status()
        except Exception:
            return None

        resp_url = str(resp.url)
        if "antispider" in resp_url or "qcaptcha" in resp_url:
            engine.mark_blocked()
            return None

        if engine.name == "sogou":
            return self._parse_sogou(resp.text, max_results)
        return self._parse_360(resp.text, max_results)

    def _parse_sogou(self, html: str, max_results: int) -> list[dict[str, Any]]:
        soup = BeautifulSoup(html, "html.parser")
        results: list[dict[str, Any]] = []

        for item in soup.select("div.vrwrap"):
            if len(results) >= max_results:
                break

            title_el = item.select_one("h3 a")
            if not title_el:
                continue

            title = title_el.get_text(strip=True)
            if not title:
                continue

            data_url_el = item.select_one("[data-url]")
            href = data_url_el.get("data-url", "").strip() if data_url_el else ""
            if not href:
                raw_href = title_el.get("href", "").strip()
                if raw_href.startswith("http"):
                    href = raw_href
            if not href:
                continue

            snippet = ""
            for sel in ("div.text-layout p", "p.star-wiki", "div.text-layout"):
                el = item.select_one(sel)
                if el:
                    text = el.get_text(strip=True)
                    if len(text) > 15:
                        snippet = text
                        break

            source = ""
            cite_el = item.select_one("cite")
            if cite_el:
                source = cite_el.get_text(strip=True)

            results.append({
                "title": title,
                "url": href,
                "body": snippet,
                "source": source,
                "date": "",
            })

        return results

    def _parse_360(self, html: str, max_results: int) -> list[dict[str, Any]]:
        soup = BeautifulSoup(html, "html.parser")
        results: list[dict[str, Any]] = []

        for item in soup.select("li.res-list"):
            if len(results) >= max_results:
                break

            link = item.select_one("h3 a")
            if not link:
                continue

            title = link.get_text(strip=True)
            if not title:
                continue

            href = link.get("data-mdurl", "").strip()
            if not href:
                mdurl_el = item.select_one("[data-mdurl]")
                if mdurl_el:
                    href = mdurl_el.get("data-mdurl", "").strip()
            if not href or href.startswith("https://www.so.com/link"):
                continue

            snippet = ""
            snippet_el = item.select_one("p.res-desc")
            if snippet_el:
                snippet = snippet_el.get_text(strip=True)

            source = ""
            cite_el = item.select_one("cite")
            if cite_el:
                source = cite_el.get_text(strip=True)

            results.append({
                "title": title,
                "url": href,
                "body": snippet,
                "source": source,
                "date": "",
            })

        return results


def create_search_tool(settings: AppSettings) -> SearchToolProtocol:
    return MultiEngineSearchTool(settings)
