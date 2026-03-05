from __future__ import annotations

import json
from datetime import datetime, timedelta, timezone
from pathlib import Path
import time
from typing import Any

import feedparser

PROJECT_ROOT = Path(__file__).resolve().parents[1]
RAW_OUTPUT_PATH = PROJECT_ROOT / "pages" / "raw_articles.json"

ALLOWED_SOURCES = {
    "Reuters",
    "BBC",
    "The Guardian",
    "Associated Press",
    "SVT",
    "Sveriges Radio",
    "MIT Technology Review",
    "Ars Technica",
    "TechCrunch",
    "The Verge",
}

SOURCE_ALIASES = {
    "reuters": "Reuters",
    "bbc": "BBC",
    "the guardian": "The Guardian",
    "guardian": "The Guardian",
    "associated press": "Associated Press",
    "ap news": "Associated Press",
    "ap": "Associated Press",
    "svt": "SVT",
    "sveriges radio": "Sveriges Radio",
    "sr": "Sveriges Radio",
    "mit technology review": "MIT Technology Review",
    "technology review": "MIT Technology Review",
    "ars technica": "Ars Technica",
    "techcrunch": "TechCrunch",
    "the verge": "The Verge",
    "verge": "The Verge",
}

GENERAL_FEEDS: list[tuple[str, str]] = [
    ("https://www.reuters.com/world/rss", "Reuters"),
    ("https://feeds.bbci.co.uk/news/world/rss.xml", "BBC"),
    ("https://www.theguardian.com/world/rss", "The Guardian"),
    ("https://apnews.com/hub/apf-topnews?output=rss", "Associated Press"),
    ("https://www.svt.se/nyheter/rss.xml", "SVT"),
    ("https://feeds.sr.se/senasteekot", "Sveriges Radio"),
]

TECH_FEEDS: list[tuple[str, str]] = [
    ("https://www.technologyreview.com/feed/", "MIT Technology Review"),
    ("https://feeds.arstechnica.com/arstechnica/index", "Ars Technica"),
    ("https://techcrunch.com/feed/", "TechCrunch"),
    ("https://www.theverge.com/rss/index.xml", "The Verge"),
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


def _extract_image_url(entry: dict[str, Any]) -> str | None:
    media_content = entry.get("media_content") or []
    if isinstance(media_content, list):
        for item in media_content:
            if isinstance(item, dict):
                url = str(item.get("url") or "").strip()
                if url:
                    return url

    media_thumbnail = entry.get("media_thumbnail") or []
    if isinstance(media_thumbnail, list):
        for item in media_thumbnail:
            if isinstance(item, dict):
                url = str(item.get("url") or "").strip()
                if url:
                    return url

    enclosures = entry.get("enclosures") or []
    if isinstance(enclosures, list):
        for enclosure in enclosures:
            if not isinstance(enclosure, dict):
                continue
            enclosure_type = str(enclosure.get("type") or "").strip().lower()
            if not enclosure_type.startswith("image/"):
                continue
            url = str(enclosure.get("url") or enclosure.get("href") or "").strip()
            if url:
                return url

    return None


def _normalize_source(source_text: str) -> str | None:
    normalized = (source_text or "").strip().lower()
    if not normalized:
        return None

    if normalized in SOURCE_ALIASES:
        return SOURCE_ALIASES[normalized]

    for alias, canonical in SOURCE_ALIASES.items():
        if alias in normalized:
            return canonical

    return None


def _extract_entries(feed_url: str, since: datetime, default_source: str) -> list[dict[str, str]]:
    parsed = feedparser.parse(feed_url)
    articles: list[dict[str, str]] = []
    feed_title = str(parsed.feed.get("title") or "")
    feed_source = _normalize_source(feed_title) or default_source

    for entry in parsed.entries:
        title = (entry.get("title") or "").strip()
        link = (entry.get("link") or "").strip()
        summary = (entry.get("summary") or entry.get("description") or "").strip()
        published_dt = _extract_published_datetime(entry)
        image_url = _extract_image_url(entry)

        entry_source_data = entry.get("source") or {}
        entry_source_title = ""
        if isinstance(entry_source_data, dict):
            entry_source_title = str(entry_source_data.get("title") or "")
        source_name = _normalize_source(entry_source_title) or feed_source

        if source_name not in ALLOWED_SOURCES:
            continue

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
                "source": source_name,
                "image_url": image_url,
            }
        )

    return articles


def _sort_by_published_desc(articles: list[dict[str, str]]) -> list[dict[str, str]]:
    return sorted(articles, key=lambda item: item["published"], reverse=True)


def fetch_all_news() -> dict[str, list[dict[str, str]]]:
    since = datetime.now(timezone.utc) - timedelta(hours=24)
    general_news: list[dict[str, str]] = []
    tech_news: list[dict[str, str]] = []

    for url, source in GENERAL_FEEDS:
        general_news.extend(_extract_entries(url, since, source))

    for url, source in TECH_FEEDS:
        tech_news.extend(_extract_entries(url, since, source))

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
