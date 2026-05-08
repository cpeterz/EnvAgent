from __future__ import annotations

import asyncio
import hashlib
import time
from typing import Any

import feedparser

from news_collector.config import AppSettings

from .base import RSSFeedToolProtocol


class RSSFeedTool(RSSFeedToolProtocol):
    def __init__(self, settings: AppSettings):
        self._sources = settings.rss.sources
        self._update_interval = settings.rss.update_interval
        self._cache: dict[str, list[dict[str, Any]]] = {}
        self._cache_time: dict[str, float] = {}

    async def fetch_feeds(self, *, category: str | None = None) -> list[dict[str, Any]]:
        sources = self._sources
        if category:
            sources = [s for s in sources if s.get("category") == category]

        tasks = [self._fetch_single(source) for source in sources]
        results = await asyncio.gather(*tasks, return_exceptions=True)

        all_items: list[dict[str, Any]] = []
        for result in results:
            if isinstance(result, list):
                all_items.extend(result)
        return all_items

    async def _fetch_single(self, source: dict[str, str]) -> list[dict[str, Any]]:
        url = source.get("url", "")
        name = source.get("name", "")
        cache_key = hashlib.md5(url.encode()).hexdigest()

        now = time.time()
        if cache_key in self._cache and (now - self._cache_time.get(cache_key, 0)) < self._update_interval:
            return self._cache[cache_key]

        items = await asyncio.to_thread(self._parse_feed, url, name)
        self._cache[cache_key] = items
        self._cache_time[cache_key] = now
        return items

    @staticmethod
    def _parse_feed(url: str, source_name: str) -> list[dict[str, Any]]:
        try:
            feed = feedparser.parse(url)
        except Exception:
            return []

        items: list[dict[str, Any]] = []
        for entry in feed.entries[:20]:
            title = getattr(entry, "title", "").strip()
            link = getattr(entry, "link", "").strip()
            if not title or not link:
                continue

            summary = getattr(entry, "summary", "") or getattr(entry, "description", "")
            published = getattr(entry, "published", "") or getattr(entry, "updated", "")

            items.append({
                "id": len(items),
                "title": title,
                "brief": str(summary).strip()[:300],
                "url": link,
                "source": source_name,
                "date": str(published).strip(),
            })
        return items


def create_rss_tool(settings: AppSettings) -> RSSFeedToolProtocol:
    return RSSFeedTool(settings)
