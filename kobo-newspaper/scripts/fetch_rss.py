from __future__ import annotations

import json
from datetime import datetime, timedelta, timezone
from pathlib import Path
import time
from typing import Any

import feedparser

PROJECT_ROOT = Path(__file__).resolve().parents[1]
RAW_OUTPUT_PATH = PROJECT_ROOT / "pages" / "raw_articles.json"

GENERAL_FEEDS = [
    "https://www.svt.se/nyheter/rss.xml",
    "https://feeds.bbci.co.uk/news/world/rss.xml",
    "https://www.theguardian.com/world/rss",
    "https://www.reuters.com/world/rss",
]

TECH_FEEDS = [
    "https://techcrunch.com/feed/",
    "https://www.theverge.com/rss/index.xml",
    "https://www.wired.com/feed/rss",
    "https://huggingface.co/blog/feed.xml",
]

GENERAL_LIMIT = 20
TECH_LIMIT = 15


def _to_utc_datetime(time_struct: time.struct_time | None) -> datetime | None:
    if not time_struct:
        return None
    return datetime.fromtimestamp(time.mktime(time_struct), tz=timezone.utc)


def _extract_published_datetime(entry: dict[str, Any]) -> datetime | None:
    published_dt = _to_utc_datetime(entry.get("published_parsed"))
    if published_dt:
        return published_dt
    return _to_utc_datetime(entry.get("updated_parsed"))


def _extract_entries(feed_url: str, since: datetime) -> list[dict[str, str]]:
    parsed = feedparser.parse(feed_url)
    articles: list[dict[str, str]] = []

    for entry in parsed.entries:
        title = (entry.get("title") or "").strip()
        link = (entry.get("link") or "").strip()
        summary = (entry.get("summary") or entry.get("description") or "").strip()
        published_dt = _extract_published_datetime(entry)

        if not title or not link or not published_dt:
            continue

        if published_dt < since:
            continue

        articles.append(
            {
                "title": title,
                "link": link,
                "published": published_dt.isoformat(),
                "summary": summary,
            }
        )

    return articles


def _sort_by_published_desc(articles: list[dict[str, str]]) -> list[dict[str, str]]:
    return sorted(articles, key=lambda item: item["published"], reverse=True)


def fetch_all_news() -> dict[str, list[dict[str, str]]]:
    since = datetime.now(timezone.utc) - timedelta(hours=24)
    general_news: list[dict[str, str]] = []
    tech_news: list[dict[str, str]] = []

    for url in GENERAL_FEEDS:
        general_news.extend(_extract_entries(url, since))

    for url in TECH_FEEDS:
        tech_news.extend(_extract_entries(url, since))

    general_news = _sort_by_published_desc(general_news)[:GENERAL_LIMIT]
    tech_news = _sort_by_published_desc(tech_news)[:TECH_LIMIT]

    return {
        "general": general_news,
        "tech": tech_news,
    }


def save_raw_news(data: dict[str, Any], output_path: Path = RAW_OUTPUT_PATH) -> None:
    output_path.parent.mkdir(parents=True, exist_ok=True)
    output_path.write_text(json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8")


if __name__ == "__main__":
    all_news = fetch_all_news()
    save_raw_news(all_news)
    print(f"Saved raw RSS articles to: {RAW_OUTPUT_PATH}")
