from __future__ import annotations

import os
import re
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Literal, TypeAlias, TypeVar, cast

import yaml


ENV_PATTERN = re.compile(r"\$\{(?:ENV\.)?([A-Za-z_][A-Za-z0-9_]*)(?::-([^}]*))?\}")
LiteralStrT = TypeVar("LiteralStrT", bound=str)

ModelProvider: TypeAlias = Literal["OpenAICompatible", "OpenAI", "OAIClient"]
ModelType: TypeAlias = Literal["chat", "completions", "embeddings"]
SearchBackend: TypeAlias = Literal[
    "auto", "bing", "duckduckgo", "yahoo", "google",
    "mullvad_google", "yandex", "wikipedia",
]
SearchNewsTimeLimit: TypeAlias = Literal["d", "w", "m"]
BrowseResponseMode: TypeAlias = Literal["markdown", "text"]

MODEL_PROVIDER_VALUES: tuple[ModelProvider, ...] = ("OpenAICompatible", "OpenAI", "OAIClient")
MODEL_TYPE_VALUES: tuple[ModelType, ...] = ("chat", "completions", "embeddings")
SEARCH_BACKEND_VALUES: tuple[SearchBackend, ...] = (
    "auto", "bing", "duckduckgo", "yahoo", "google",
    "mullvad_google", "yandex", "wikipedia",
)
SEARCH_TIMELIMIT_VALUES: tuple[SearchNewsTimeLimit, ...] = ("d", "w", "m")
BROWSE_RESPONSE_MODE_VALUES: tuple[BrowseResponseMode, ...] = ("markdown", "text")


def _resolve_env_placeholders(value: Any) -> Any:
    if isinstance(value, str):
        def replace(match: re.Match[str]) -> str:
            env_name = match.group(1)
            default_value = match.group(2) or ""
            return os.getenv(env_name, default_value)
        return ENV_PATTERN.sub(replace, value)
    if isinstance(value, list):
        return [_resolve_env_placeholders(item) for item in value]
    if isinstance(value, dict):
        return {key: _resolve_env_placeholders(item) for key, item in value.items()}
    return value


def _as_dict(value: Any) -> dict[str, Any]:
    return value if isinstance(value, dict) else {}


def _as_int(value: Any, default: int) -> int:
    try:
        return int(value)
    except (TypeError, ValueError):
        return default


def _as_bool(value: Any, default: bool = False) -> bool:
    if value is None:
        return default
    if isinstance(value, bool):
        return value
    if isinstance(value, str):
        normalized = value.strip().lower()
        if normalized in {"1", "true", "yes", "on"}:
            return True
        if normalized in {"0", "false", "no", "off"}:
            return False
    return bool(value)


def _as_optional_str(value: Any) -> str | None:
    if value is None:
        return None
    text = str(value).strip()
    if not text or text.lower() in {"none", "null"}:
        return None
    return text


def _normalize_auth(value: Any) -> Any:
    if isinstance(value, str):
        normalized = _as_optional_str(value)
        if normalized and "input your api key" in normalized.lower():
            return None
        return normalized
    if isinstance(value, dict):
        normalized = {
            str(key): item for key, item in value.items()
            if item not in (None, "", [], {})
        }
        api_key = _as_optional_str(normalized.get("api_key"))
        if api_key is None:
            normalized.pop("api_key", None)
        else:
            normalized["api_key"] = api_key
        return normalized or None
    return value


def _as_literal(
    value: Any, *, allowed: tuple[LiteralStrT, ...], default: LiteralStrT,
) -> LiteralStrT:
    if isinstance(value, str):
        candidate = value.strip()
        if candidate in allowed:
            return cast(LiteralStrT, candidate)
        lower_candidate = candidate.lower()
        for item in allowed:
            if lower_candidate == item.lower():
                return item
    return default


@dataclass(slots=True)
class ModelConfig:
    provider: ModelProvider = "OpenAICompatible"
    base_url: str = "https://api.openai.com/v1"
    model: str = "gpt-4.1-mini"
    model_type: ModelType = "chat"
    auth: Any = None
    request_options: dict[str, Any] = field(default_factory=dict)
    proxy: str | None = None

    @classmethod
    def from_raw(cls, raw: dict[str, Any]) -> "ModelConfig":
        block = _as_dict(raw.get("MODEL") or raw.get("model"))
        legacy_request_options = dict(_as_dict(raw.get("MODEL_OPTIONS")))
        block_request_options = dict(_as_dict(block.get("request_options") or block.get("options")))
        request_options = block_request_options or legacy_request_options
        model_name = block.get("model") or request_options.pop("model", None) or "gpt-4.1-mini"
        return cls(
            provider=_as_literal(
                block.get("provider") or raw.get("MODEL_PROVIDER"),
                allowed=MODEL_PROVIDER_VALUES, default="OpenAICompatible",
            ),
            base_url=str(block.get("base_url") or raw.get("MODEL_URL") or "https://api.openai.com/v1"),
            model=str(model_name),
            model_type=_as_literal(block.get("model_type"), allowed=MODEL_TYPE_VALUES, default="chat"),
            auth=_normalize_auth(block.get("auth", raw.get("MODEL_AUTH"))),
            request_options=request_options,
            proxy=_as_optional_str(block.get("proxy")),
        )

    def to_agently_settings(self, global_proxy: str | None = None) -> dict[str, Any]:
        settings: dict[str, Any] = {
            "base_url": self.base_url,
            "model": self.model,
            "model_type": self.model_type,
            "request_options": self.request_options,
        }
        proxy = self.proxy or global_proxy
        if proxy:
            settings["proxy"] = proxy
        if self.auth is not None:
            settings["auth"] = self.auth
        return settings


@dataclass(slots=True)
class SearchConfig:
    max_results: int = 10
    timelimit: SearchNewsTimeLimit = "d"
    region: str = "cn-zh"
    backend: SearchBackend = "auto"
    proxy: str | None = None
    env_keywords_boost: list[str] = field(default_factory=list)

    @classmethod
    def from_raw(cls, raw: dict[str, Any]) -> "SearchConfig":
        block = _as_dict(raw.get("SEARCH") or raw.get("search"))
        boost = block.get("env_keywords_boost", [])
        if not isinstance(boost, list):
            boost = []
        return cls(
            max_results=max(_as_int(block.get("max_results"), 10), 1),
            timelimit=_as_literal(block.get("timelimit"), allowed=SEARCH_TIMELIMIT_VALUES, default="d"),
            region=str(block.get("region") or "cn-zh"),
            backend=_as_literal(block.get("backend"), allowed=SEARCH_BACKEND_VALUES, default="auto"),
            proxy=_as_optional_str(block.get("proxy")),
            env_keywords_boost=[str(k) for k in boost],
        )


@dataclass(slots=True)
class RSSConfig:
    enabled: bool = True
    update_interval: int = 3600
    sources: list[dict[str, str]] = field(default_factory=list)

    @classmethod
    def from_raw(cls, raw: dict[str, Any]) -> "RSSConfig":
        block = _as_dict(raw.get("RSS") or raw.get("rss"))
        sources = block.get("sources", [])
        if not isinstance(sources, list):
            sources = []
        return cls(
            enabled=_as_bool(block.get("enabled"), True),
            update_interval=max(_as_int(block.get("update_interval"), 3600), 60),
            sources=[s for s in sources if isinstance(s, dict)],
        )


@dataclass(slots=True)
class BrowseConfig:
    enable_playwright: bool = False
    playwright_headless: bool = True
    response_mode: BrowseResponseMode = "markdown"
    max_content_length: int = 12000
    min_content_length: int = 80
    proxy: str | None = None

    @classmethod
    def from_raw(cls, raw: dict[str, Any]) -> "BrowseConfig":
        block = _as_dict(raw.get("BROWSE") or raw.get("browse"))
        return cls(
            enable_playwright=_as_bool(block.get("enable_playwright"), False),
            playwright_headless=_as_bool(block.get("playwright_headless"), True),
            response_mode=_as_literal(
                block.get("response_mode"), allowed=BROWSE_RESPONSE_MODE_VALUES, default="markdown",
            ),
            max_content_length=max(_as_int(block.get("max_content_length"), 12000), 2000),
            min_content_length=max(_as_int(block.get("min_content_length"), 80), 20),
            proxy=_as_optional_str(block.get("proxy")),
        )


@dataclass(slots=True)
class WorkflowConfig:
    max_column_num: int = 4
    max_news_per_column: int = 5
    output_language: str = "Chinese"
    column_concurrency: int = 3
    summary_concurrency: int = 3
    default_topic: str = "今日环境新闻"

    @classmethod
    def from_raw(cls, raw: dict[str, Any]) -> "WorkflowConfig":
        block = _as_dict(raw.get("WORKFLOW") or raw.get("workflow"))
        return cls(
            max_column_num=max(_as_int(block.get("max_column_num"), 4), 1),
            max_news_per_column=max(_as_int(block.get("max_news_per_column"), 5), 1),
            output_language=str(block.get("output_language") or "Chinese"),
            column_concurrency=max(_as_int(block.get("column_concurrency"), 3), 1),
            summary_concurrency=max(_as_int(block.get("summary_concurrency"), 3), 1),
            default_topic=str(block.get("default_topic") or "今日环境新闻"),
        )


@dataclass(slots=True)
class OutlineConfig:
    use_customized: bool = False
    customized: dict[str, Any] = field(default_factory=dict)

    @classmethod
    def from_raw(cls, raw: dict[str, Any]) -> "OutlineConfig":
        block = _as_dict(raw.get("OUTLINE") or raw.get("outline"))
        customized = block.get("customized") or {}
        return cls(
            use_customized=_as_bool(block.get("use_customized"), False),
            customized=customized if isinstance(customized, dict) else {},
        )


@dataclass(slots=True)
class OutputConfig:
    directory: str = "outputs"

    @classmethod
    def from_raw(cls, raw: dict[str, Any]) -> "OutputConfig":
        block = _as_dict(raw.get("OUTPUT") or raw.get("output"))
        return cls(directory=str(block.get("directory") or "outputs"))


@dataclass(slots=True)
class WebConfig:
    host: str = "0.0.0.0"
    port: int = 8080

    @classmethod
    def from_raw(cls, raw: dict[str, Any]) -> "WebConfig":
        block = _as_dict(raw.get("WEB") or raw.get("web"))
        return cls(
            host=str(block.get("host") or "0.0.0.0"),
            port=_as_int(block.get("port"), 8080),
        )


@dataclass(slots=True)
class AppSettings:
    debug: bool = False
    proxy: str | None = None
    model: ModelConfig = field(default_factory=ModelConfig)
    search: SearchConfig = field(default_factory=SearchConfig)
    rss: RSSConfig = field(default_factory=RSSConfig)
    browse: BrowseConfig = field(default_factory=BrowseConfig)
    workflow: WorkflowConfig = field(default_factory=WorkflowConfig)
    outline: OutlineConfig = field(default_factory=OutlineConfig)
    output: OutputConfig = field(default_factory=OutputConfig)
    web: WebConfig = field(default_factory=WebConfig)

    @classmethod
    def load(cls, path: str | Path) -> "AppSettings":
        config_path = Path(path)
        raw = yaml.safe_load(config_path.read_text(encoding="utf-8")) or {}
        if not isinstance(raw, dict):
            raise TypeError(f"Settings file must contain a dictionary, got: {type(raw)}")
        resolved = _resolve_env_placeholders(raw)
        return cls(
            debug=_as_bool(resolved.get("DEBUG", resolved.get("debug", False))),
            proxy=_as_optional_str(resolved.get("PROXY", resolved.get("proxy"))),
            model=ModelConfig.from_raw(resolved),
            search=SearchConfig.from_raw(resolved),
            rss=RSSConfig.from_raw(resolved),
            browse=BrowseConfig.from_raw(resolved),
            workflow=WorkflowConfig.from_raw(resolved),
            outline=OutlineConfig.from_raw(resolved),
            output=OutputConfig.from_raw(resolved),
            web=WebConfig.from_raw(resolved),
        )
