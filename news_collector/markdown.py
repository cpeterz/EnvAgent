from __future__ import annotations

from typing import Any


def _labels_for_language(language: str) -> dict[str, str]:
    normalized = language.lower()
    if "chinese" in normalized or normalized.startswith("zh"):
        return {
            "generated_at": "生成时间",
            "topic": "主题",
            "prologue": "导语",
            "news_list": "新闻列表",
            "source": "来源",
            "date": "日期",
            "summary": "摘要",
            "comment": "推荐理由",
            "model": "模型",
        }
    return {
        "generated_at": "Generated At",
        "topic": "Topic",
        "prologue": "Prologue",
        "news_list": "News List",
        "source": "Source",
        "date": "Date",
        "summary": "Summary",
        "comment": "Why It Matters",
        "model": "Model",
    }


def render_markdown(
    *,
    report_title: str,
    generated_at: str,
    topic: str,
    language: str,
    columns: list[dict[str, Any]],
    model_label: str,
) -> str:
    labels = _labels_for_language(language)
    lines = [
        f"# {report_title}",
        "",
        f"> {labels['generated_at']}: {generated_at}",
        f"> {labels['topic']}: {topic}",
        "",
    ]

    for column in columns:
        title = str(column.get("title") or "").strip()
        news_list = column.get("news_list") or []
        if not title or not news_list:
            continue

        lines.extend([
            f"## {title}",
            "",
            f"### {labels['prologue']}",
            "",
            column.get("prologue") or "",
            "",
            f"### {labels['news_list']}",
            "",
        ])

        for news in news_list:
            lines.append(f"- [{news['title']}]({news['url']})")
            meta_parts = []
            if news.get("source"):
                meta_parts.append(f"{labels['source']}: {news['source']}")
            if news.get("date"):
                meta_parts.append(f"{labels['date']}: {news['date']}")
            if meta_parts:
                lines.append(f"  - {' | '.join(meta_parts)}")
            lines.append(f"  - {labels['summary']}: {news.get('summary', '')}")
            comment = news.get("recommend_comment", "")
            if comment:
                lines.append(f"  - {labels['comment']}: {comment}")
            lines.append("")

    lines.extend([
        "---",
        "",
        "Powered by [Env News Agent](https://github.com/AgentEra/Agently)",
        "",
        f"{labels['model']}: {model_label}",
    ])

    return "\n".join(lines).strip() + "\n"
