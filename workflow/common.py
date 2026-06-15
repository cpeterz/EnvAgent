from __future__ import annotations

import asyncio
import logging
import re
import time
from dataclasses import dataclass
from pathlib import Path
from typing import Any, TypeVar, cast

T = TypeVar("T")

from agently import Agently, TriggerFlowRuntimeData

from news_collector.config import AppSettings
from tools.base import BrowseToolProtocol, RSSFeedToolProtocol, SearchToolProtocol


@dataclass(frozen=True, slots=True)
class EnvNewsChunkConfig:
    settings: AppSettings
    prompt_dir: Path
    output_dir: Path
    model_label: str


def create_editor_agent(*, kind: str):
    agent = Agently.create_agent(name=f"{kind}_editor")
    if kind == "chief":
        agent.set_agent_prompt(
            "system",
            "You are a veteran environmental news chief editor who designs reliable daily environmental news briefings. "
            "You are deeply knowledgeable about environmental policy, ecological protection, climate change, "
            "pollution control, carbon emissions trading, and green sustainable development.",
        )
        agent.set_agent_prompt(
            "instruct",
            [
                "Prefer recent, factual, non-duplicated environmental stories.",
                "Keep structures stable and concise.",
                "Prioritize stories with environmental policy impact, ecological significance, or climate relevance.",
            ],
        )
    else:
        agent.set_agent_prompt(
            "system",
            "You are a meticulous environmental news editor who selects and rewrites high-signal environmental stories. "
            "You understand environmental science, policy frameworks, and can identify the ecological significance of news events.",
        )
        agent.set_agent_prompt(
            "instruct",
            [
                "Reject irrelevant or thin content.",
                "Keep comments practical and publication-ready.",
                "Highlight environmental impact, policy implications, and ecological significance.",
            ],
        )
    return agent


def is_chinese_language(language: str) -> bool:
    normalized = language.lower()
    return "chinese" in normalized or normalized.startswith("zh")


def safe_filename(name: str) -> str:
    cleaned = re.sub(r"[\\/:*?\"<>|]+", "-", name)
    cleaned = re.sub(r"\s+", " ", cleaned).strip(" .-_")
    return cleaned or "env-news-report"


def safe_int(value: Any, default: int) -> int:
    try:
        return int(value)
    except (TypeError, ValueError):
        return default


def require_logger(data: TriggerFlowRuntimeData) -> logging.Logger:
    return cast(logging.Logger, data.require_resource("logger"))


def require_search_tool(data: TriggerFlowRuntimeData) -> SearchToolProtocol:
    return cast(SearchToolProtocol, data.require_resource("search_tool"))


def require_browse_tool(data: TriggerFlowRuntimeData) -> BrowseToolProtocol:
    return cast(BrowseToolProtocol, data.require_resource("browse_tool"))


def require_rss_tool(data: TriggerFlowRuntimeData) -> RSSFeedToolProtocol:
    return cast(RSSFeedToolProtocol, data.require_resource("rss_tool"))


_diag_logger = logging.getLogger("env_news.diag")


async def run_with_timeout(coro, *, timeout: float, default: T, label: str = "") -> T:
    # NOTE: do NOT wrap `coro` in asyncio.shield here. wait_for must be able to
    # cancel the underlying coroutine on timeout, otherwise the LLM/browse task
    # keeps running orphaned and holds onto its network connection forever,
    # which progressively stalls the whole flow.
    start = time.monotonic()
    try:
        return await asyncio.wait_for(coro, timeout=timeout)
    except asyncio.TimeoutError:
        _diag_logger.warning(
            "[Timeout] %s exceeded %.0fs (waited %.1fs); task cancelled.",
            label or "async-call", timeout, time.monotonic() - start,
        )
        return default
    except asyncio.CancelledError:
        # Never swallow cancellation: re-raise so the surrounding for_each /
        # gather can actually tear this task down instead of hanging on it.
        raise
    except Exception as exc:
        _diag_logger.warning("[AsyncError] %s: %s", label or "async-call", exc)
        return default


__all__ = [
    "EnvNewsChunkConfig",
    "create_editor_agent",
    "is_chinese_language",
    "safe_filename",
    "safe_int",
    "run_with_timeout",
    "require_logger",
    "require_search_tool",
    "require_browse_tool",
    "require_rss_tool",
]
