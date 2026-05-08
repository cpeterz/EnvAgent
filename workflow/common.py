from __future__ import annotations

import logging
import re
from dataclasses import dataclass
from pathlib import Path
from typing import Any, cast

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


__all__ = [
    "EnvNewsChunkConfig",
    "create_editor_agent",
    "is_chinese_language",
    "safe_filename",
    "safe_int",
    "require_logger",
    "require_search_tool",
    "require_browse_tool",
    "require_rss_tool",
]
