from __future__ import annotations

import asyncio
import copy
import re
import time
from typing import Any, Callable

from agently import TriggerFlowRuntimeData

from .common import (
    EnvNewsChunkConfig,
    create_editor_agent,
    is_chinese_language,
    require_browse_tool,
    require_logger,
    run_with_timeout,
    safe_int,
)


def create_summarize_column_chunk(
    config: EnvNewsChunkConfig,
) -> Callable[[TriggerFlowRuntimeData], Any]:
    """Summarize a column's picked news in a single, self-contained async pass.

    This intentionally avoids the previous event-driven loop (repeatedly
    re-emitting ``Summary.Dispatch`` and re-running a nested ``for_each`` inside
    a nested sub-flow), which could deadlock after a few iterations and stall
    the whole run. Here we process candidates with bounded concurrency in a
    plain ``while`` loop, stopping as soon as ``target_count`` summaries succeed.
    """

    async def summarize_column_news(data: TriggerFlowRuntimeData) -> dict[str, Any] | None:
        context = _coerce_summary_context(data.value)
        if context is None:
            return None

        logger = require_logger(data)
        browse_tool = require_browse_tool(data)
        column_outline = context["column_outline"]
        title = str(column_outline.get("column_title") or "").strip()

        candidates = build_summary_candidates(
            config,
            column_outline,
            context["searched_news"],
            context["picked_news"],
        )
        target_count = min(
            len(context["picked_news"]),
            config.settings.workflow.max_news_per_column,
        )

        summarized_news: list[dict[str, Any]] = []
        if target_count > 0 and candidates:
            concurrency = max(config.settings.workflow.summary_concurrency, 1)
            cursor = 0
            while len(summarized_news) < target_count and cursor < len(candidates):
                batch_size = min(
                    concurrency,
                    target_count - len(summarized_news),
                    len(candidates) - cursor,
                )
                batch = candidates[cursor : cursor + batch_size]
                logger.info(
                    "[Dispatch] cursor=%d batch=%d target=%d results=%d candidates=%d",
                    cursor, batch_size, target_count, len(summarized_news), len(candidates),
                )
                cursor += batch_size

                summaries = await asyncio.gather(
                    *(
                        summarize_single_news(
                            config, logger, browse_tool, column_outline, candidate["news"],
                        )
                        for candidate in batch
                    ),
                    return_exceptions=True,
                )

                for candidate, summary in zip(batch, summaries):
                    news_title = str(candidate["news"].get("title") or "").strip()
                    if isinstance(summary, dict):
                        summarized_news.append(summary)
                    elif isinstance(summary, BaseException):
                        logger.warning("[Summary Worker Error] %s: %s", news_title, summary)
                    elif candidate.get("is_backup"):
                        logger.info("[Backup News Rejected] %s", news_title)
                    else:
                        logger.info("[Backup News Activated] %s", news_title)

        result = copy.deepcopy(context)
        result["summarized_news"] = summarized_news
        logger.info("[Summarized News Count] %s => %s", title, len(summarized_news))
        return result

    return summarize_column_news


def _coerce_summary_context(value: Any) -> dict[str, Any] | None:
    if not isinstance(value, dict):
        return None
    column_outline = value.get("column_outline")
    searched_news = value.get("searched_news")
    picked_news = value.get("picked_news")
    if not isinstance(column_outline, dict) or not isinstance(searched_news, list) or not isinstance(picked_news, list):
        return None
    return {
        "column_outline": copy.deepcopy(column_outline),
        "searched_news": copy.deepcopy(searched_news),
        "picked_news": copy.deepcopy(picked_news),
    }


def build_summary_candidates(
    config: EnvNewsChunkConfig,
    column_outline: dict[str, Any],
    searched_news: list[dict[str, Any]],
    picked_news: list[dict[str, Any]],
) -> list[dict[str, Any]]:
    candidates: list[dict[str, Any]] = []
    picked_urls = {
        str(news.get("url") or "").strip()
        for news in picked_news
        if str(news.get("url") or "").strip()
    }
    seen_urls: set[str] = set()

    for news in picked_news:
        url = str(news.get("url") or "").strip()
        if not url or url in seen_urls:
            continue
        seen_urls.add(url)
        candidates.append({"news": copy.deepcopy(news), "is_backup": False})

    max_backups = config.settings.workflow.max_news_per_column
    backup_count = 0
    for news in searched_news:
        if backup_count >= max_backups:
            break
        url = str(news.get("url") or "").strip()
        if not url or url in seen_urls or url in picked_urls:
            continue
        seen_urls.add(url)
        backup_news = copy.deepcopy(news)
        if not str(backup_news.get("recommend_comment") or "").strip():
            backup_news["recommend_comment"] = _build_backup_recommend_comment(
                config, column_outline, backup_news,
            )
        candidates.append({"news": backup_news, "is_backup": True})
        backup_count += 1

    return candidates


async def pick_news(
    config: EnvNewsChunkConfig,
    column_outline: dict[str, Any],
    searched_news: list[dict[str, Any]],
) -> list[dict[str, Any]]:
    pick_results = await run_with_timeout(
        create_editor_agent(kind="column")
        .load_yaml_prompt(
            config.prompt_dir / "pick_news.yaml",
            mappings={
                "column_news": searched_news,
                "column_title": column_outline["column_title"],
                "column_requirement": column_outline["column_requirement"],
                "max_news_per_column": config.settings.workflow.max_news_per_column,
            },
        )
        .async_start(
            ensure_keys=[
                "[*].id",
                "[*].can_use",
                "[*].relevance_score",
                "[*].recommend_comment",
            ]
        ),
        timeout=60,
        default=None,
        label="pick_news",
    )
    if not isinstance(pick_results, list):
        return _fallback_pick_news(config, searched_news)

    picked_news = []
    seen_ids: set[int] = set()
    sorted_results = sorted(
        [item for item in pick_results if isinstance(item, dict)],
        key=lambda item: safe_int(item.get("relevance_score"), 0),
        reverse=True,
    )
    for item in sorted_results:
        if item.get("can_use") is not True:
            continue
        news_id = safe_int(item.get("id"), -1)
        if news_id < 0 or news_id >= len(searched_news) or news_id in seen_ids:
            continue
        seen_ids.add(news_id)
        picked_item = copy.deepcopy(searched_news[news_id])
        picked_item["recommend_comment"] = str(item.get("recommend_comment") or "").strip()
        picked_item["relevance_score"] = safe_int(item.get("relevance_score"), 0)
        picked_news.append(picked_item)
        if len(picked_news) >= config.settings.workflow.max_news_per_column:
            break

    if not picked_news:
        return _fallback_pick_news(config, searched_news)
    return picked_news


def _fallback_pick_news(
    config: EnvNewsChunkConfig,
    searched_news: list[dict[str, Any]],
) -> list[dict[str, Any]]:
    """Degrade gracefully when the LLM shortlist fails or yields nothing.

    The pick stage relies on structured LLM output, which can fail entirely
    (e.g. the endpoint returns "No target data in response"). Rather than
    dropping the whole column and producing an empty report, keep the top
    candidates in their original search order so the summary stage can proceed.
    """
    fallback: list[dict[str, Any]] = []
    seen_ids: set[int] = set()
    for index, news in enumerate(searched_news):
        if not isinstance(news, dict):
            continue
        if index in seen_ids:
            continue
        seen_ids.add(index)
        picked_item = copy.deepcopy(news)
        picked_item.setdefault("recommend_comment", "")
        picked_item["relevance_score"] = 0
        fallback.append(picked_item)
        if len(fallback) >= config.settings.workflow.max_news_per_column:
            break
    return fallback


async def summarize_single_news(
    config: EnvNewsChunkConfig,
    logger,
    browse_tool,
    column_outline: dict[str, Any],
    news: dict[str, Any],
) -> dict[str, Any] | None:
    logger.info("[Summarizing] %s", news["title"])
    browse_start = time.monotonic()
    try:
        content = await asyncio.wait_for(browse_tool.browse(news["url"]), timeout=20)
    except asyncio.TimeoutError:
        logger.warning(
            "[Summarizing] Failed - browse TIMEOUT after %.1fs | %s",
            time.monotonic() - browse_start, news["url"],
        )
        return None
    except Exception as exc:
        logger.warning(
            "[Summarizing] Failed - browse error after %.1fs: %s | %s",
            time.monotonic() - browse_start, exc, news["url"],
        )
        return None
    content = str(content or "").strip()
    logger.info(
        "[Browsed] %.1fs len=%d | %s",
        time.monotonic() - browse_start, len(content), news["url"],
    )
    if len(content) < config.settings.browse.min_content_length:
        logger.info("[Summarizing] Failed - content too short")
        return None
    if _is_invalid_browse_content(content):
        logger.info("[Summarizing] Failed - invalid browsed content")
        return None

    content = _extract_main_content(
        content,
        news["title"],
        config.settings.browse.summary_max_content_length,
        config.settings.browse.min_content_length,
    )

    llm_start = time.monotonic()
    summary_result = await run_with_timeout(
        create_editor_agent(kind="column")
        .load_yaml_prompt(
            config.prompt_dir / "summarize_news.yaml",
            mappings={
                "news_content": content,
                "news_title": news["title"],
                "column_requirement": column_outline["column_requirement"],
                "language": config.settings.workflow.output_language,
            },
        )
        .async_start(ensure_keys=["can_summarize", "summary"]),
        timeout=45,
        default=None,
        label=f"summarize:{str(news['title'])[:24]}",
    )
    logger.info("[Summary LLM] %.1fs | %s", time.monotonic() - llm_start, news["title"])
    if summary_result is None:
        logger.info("[Summarizing] Failed - timeout or error")
        return _build_brief_fallback(news, logger)

    if not isinstance(summary_result, dict):
        logger.info("[Summarizing] Failed - invalid summary output")
        return _build_brief_fallback(news, logger)
    if summary_result.get("can_summarize") is not True:
        logger.info("[Summarizing] Failed - model rejected content")
        return None

    summary = str(summary_result.get("summary") or "").strip()
    if not summary:
        logger.info("[Summarizing] Failed - empty summary")
        return _build_brief_fallback(news, logger)

    summarized_news = copy.deepcopy(news)
    summarized_news["summary"] = summary
    logger.info("[Summarizing] Success")
    return summarized_news


# 噪声行关键词（导航、页脚、版权、登录注册等），命中且行较短则丢弃。
_NOISE_KEYWORDS = (
    "版权",
    "copyright",
    "all rights reserved",
    "备案",
    "icp",
    "登录",
    "注册",
    "首页",
    "上一篇",
    "下一篇",
    "相关阅读",
    "相关推荐",
    "扫一扫",
    "分享到",
    "responsible editor",
    "编辑：",
    "来源：",
)


def _title_terms(title: str) -> list[str]:
    """从标题提取用于"正文相关行"判定的关键词。

    英文等以空白/标点分词；中文标题（无空格）改用 2-4 字滑窗切词，
    否则 ``term in line`` 对整条中文标题几乎不可能命中，导致标题保护失效。
    """
    normalized = re.sub(r"[，、,。.!！?？:：;；\s]+", " ", title).strip()
    terms: set[str] = set()
    for token in normalized.split(" "):
        token = token.strip()
        if not token:
            continue
        if re.search(r"[\u4e00-\u9fff]", token):
            # 含中日韩字符：用 2-4 字滑窗，捕获实体/机构等子串。
            for size in (4, 3, 2):
                if len(token) < size:
                    continue
                for i in range(len(token) - size + 1):
                    terms.add(token[i : i + size])
        elif len(token) >= 2:
            terms.add(token.lower())
    return [t for t in terms if t]


def _extract_main_content(
    content: str, title: str, max_chars: int, min_content_length: int
) -> str:
    """从浏览到的 markdown 内容中提取正文核心：纯 Python 去噪并按边界裁剪到 ``max_chars``。

    不调用 LLM。若去噪后内容低于 ``min_content_length``，回退到对原始内容的边界截断，
    避免误删导致内容过短被丢弃。
    """
    original = content.strip()
    if len(original) <= max_chars:
        # 内容本就不长，做一次轻量去噪但不强行裁剪；去噪后过短则透传原文。
        cleaned = _clean_lines(original, title)
        return cleaned if len(cleaned) >= min_content_length else original

    cleaned = _clean_lines(original, title)
    if len(cleaned) < min_content_length:
        cleaned = original
    return _truncate_on_boundary(cleaned, max_chars)


def _clean_lines(content: str, title: str) -> str:
    """逐行去噪：丢弃命中噪声关键词的短行与重复行，合并连续空行。

    去重始终生效（含标题行）；标题相关行仅豁免"噪声关键词短行"过滤，避免误删正文标题。
    """
    title_terms = _title_terms(title)
    seen: set[str] = set()
    kept: list[str] = []
    for raw_line in content.splitlines():
        line = raw_line.strip()
        if not line:
            kept.append("")
            continue
        if line in seen:
            continue
        seen.add(line)
        lowered = line.lower()
        is_title_related = any(term in lowered for term in title_terms)
        if not is_title_related and len(line) <= 40 and any(kw in lowered for kw in _NOISE_KEYWORDS):
            continue
        kept.append(line)

    result_lines: list[str] = []
    prev_blank = False
    for line in kept:
        blank = line == ""
        if blank and prev_blank:
            continue
        result_lines.append(line)
        prev_blank = blank
    return "\n".join(result_lines).strip()


def _truncate_on_boundary(content: str, max_chars: int) -> str:
    """按段落/句子边界截断到 ``max_chars``，避免硬切句子。"""
    if len(content) <= max_chars:
        return content
    window = content[:max_chars]
    para_cut = window.rfind("\n\n")
    if para_cut >= max_chars // 2:
        return window[:para_cut].strip()
    for sep in ("。", "！", "？", ".", "\n"):
        cut = window.rfind(sep)
        if cut >= max_chars // 2:
            return window[: cut + 1].strip()
    return window.strip()


def _build_brief_fallback(news: dict[str, Any], logger) -> dict[str, Any] | None:
    """LLM 摘要失败（超时/出错/空摘要）时，用搜索结果自带的 ``brief`` 降级生成摘要。

    仅作"数量兜底"：避免整条新闻被丢弃。若无可用 ``brief``，返回 ``None`` 以维持
    现有"调备用候选"逻辑。模型主动判定不相关（``can_summarize=False``）时不走此分支。
    """
    brief = _clean_lines(str(news.get("brief") or "").strip(), str(news.get("title") or ""))
    if not brief:
        return None
    if len(brief) > 300:
        brief = _truncate_on_boundary(brief, 300)
    summarized_news = copy.deepcopy(news)
    summarized_news["summary"] = brief
    logger.info("[Summarizing] Fallback - using search brief")
    return summarized_news


def _build_backup_recommend_comment(
    config: EnvNewsChunkConfig,
    column_outline: dict[str, Any],
    news: dict[str, Any],
) -> str:
    title = str(column_outline.get("column_title") or "本栏目")
    news_title = str(news.get("title") or "").strip()
    if is_chinese_language(config.settings.workflow.output_language):
        if news_title:
            return "该报道与"" + title + ""存在明确关联，可作为备用候选：" + news_title + "。"
        return "该报道与"" + title + ""存在明确关联，可作为备用候选。"
    if news_title:
        return f"This story is meaningfully related to {title} and is kept as a backup candidate: {news_title}."
    return f"This story is meaningfully related to {title} and is kept as a backup candidate."


def _is_invalid_browse_content(content: str) -> bool:
    lowered = content.strip().lower()
    invalid_markers = (
        "can not browse '",
        "fallback failed:",
        "content_empty_or_too_short",
        "we've detected unusual activity",
        "not a robot",
        "captcha",
        "access denied",
        "subscribe now",
    )
    return any(marker in lowered for marker in invalid_markers)


__all__ = [
    "create_summarize_column_chunk",
    "pick_news",
]
