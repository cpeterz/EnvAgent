from __future__ import annotations

import logging
import os
import re
from pathlib import Path
from typing import Any, cast

from agently import Agently

from tools import create_browse_tool, create_rss_tool, create_search_tool
from workflow import build_env_news_flow

from .config import AppSettings


class EnvNewsCollector:
    def __init__(
        self,
        *,
        settings: AppSettings,
        root_dir: str | Path,
        logger: logging.Logger,
    ):
        self.settings = settings
        self.root_dir = Path(root_dir).resolve()
        self.logger = logger
        self.model_label = ""

        self._configure_agently()

        search_tool = create_search_tool(self.settings)
        browse_tool = create_browse_tool(self.settings)
        rss_tool = create_rss_tool(self.settings)
        self.flow = build_env_news_flow(
            settings=self.settings,
            root_dir=self.root_dir,
            model_label=self.model_label,
        )
        self.flow.update_runtime_resources(
            logger=self.logger,
            search_tool=search_tool,
            browse_tool=browse_tool,
            rss_tool=rss_tool,
        )

    def collect(self, topic: str) -> dict[str, Any]:
        normalized_topic = topic.strip()
        if not normalized_topic:
            normalized_topic = self.settings.workflow.default_topic
        result = self.flow.start(normalized_topic)
        return result

    def _configure_agently(self) -> None:
        from dotenv import find_dotenv, load_dotenv

        load_dotenv(find_dotenv())
        model_settings = self.settings.model.to_agently_settings(self.settings.proxy)
        if self._missing_env_names(model_settings.get("auth")):
            model_settings.pop("auth", None)

        resolved_model_name = self._resolve_env_value(model_settings.get("model"))
        self.model_label = f"{self.settings.model.provider} / {resolved_model_name}"
        Agently.set_settings("debug", self.settings.debug)
        Agently.set_settings(
            self.settings.model.provider,
            model_settings,
            auto_load_env=True,
        )

    @classmethod
    def _collect_env_names(cls, value: Any) -> list[str]:
        if isinstance(value, str):
            return re.findall(r"\$\{\s*ENV\.([^}]+?)\s*\}", value)
        if isinstance(value, dict):
            env_names: list[str] = []
            for item in value.values():
                env_names.extend(cls._collect_env_names(item))
            return env_names
        if isinstance(value, list):
            env_names = []
            for item in value:
                env_names.extend(cls._collect_env_names(item))
            return env_names
        return []

    @classmethod
    def _missing_env_names(cls, value: Any) -> list[str]:
        env_names = sorted(set(cls._collect_env_names(value)))
        return [name for name in env_names if os.getenv(name) in (None, "")]

    @staticmethod
    def _resolve_env_value(value: Any) -> str:
        if not isinstance(value, str):
            return str(value)

        def replacer(match: re.Match[str]) -> str:
            env_name = match.group(1).strip()
            return os.getenv(env_name, match.group(0))

        return re.sub(r"\$\{\s*ENV\.([^}]+?)\s*\}", replacer, value)
