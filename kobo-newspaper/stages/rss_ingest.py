from __future__ import annotations

from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any

import feedparser

from app.models import RSS_OUTPUT, clean_text, write_json

SOURCE_FEEDS: list[tuple[str, str]] = [
    ("https://www.svt.se/nyheter/rss.xml", "SVT"),
    ("https://feeds.sr.se/senasteekot", "Sveriges Radio"),
    ("https://www.svd.se/?service=rss", "SvD"),
    ("https://www.dn.se/rss/", "DN"),
    ("https://www.di.se/rss/", "DI"),
    ("https://www.reuters.com/world/rss", "Reuters"),
    ("https://feeds.bbci.co.uk/news/world/rss.xml", "BBC"),
    ("https://www.theguardian.com/world/rss", "Guardian"),
    ("https://apnews.com/hub/apf-topnews?output=rss", "AP"),
    ("https://www.technologyreview.com/feed/", "MIT Technology Review"),
    ("https://feeds.arstechnica.com/arstechnica/index", "Ars Technica"),
]
MAX_PER_SOURCE = 3


def _extract_published(entry: dict[str, Any]) -> str:
    parsed = entry.get("published_parsed") or entry.get("updated_parsed")
    if not parsed:
        return ""
    return datetime(*parsed[:6], tzinfo=timezone.utc).isoformat()


def run() -> Path:
    since = datetime.now(timezone.utc) - timedelta(hours=36)
    all_articles: list[dict[str, Any]] = []

    for feed_url, source in SOURCE_FEEDS:
        parsed = feedparser.parse(feed_url)
        source_articles: list[dict[str, Any]] = []

        for entry in parsed.entries:
            title = clean_text(entry.get("title", ""))
            link = clean_text(entry.get("link", ""))
            summary = clean_text(entry.get("summary", entry.get("description", "")))
            published = _extract_published(entry)

            if not title or not link or not published:
                continue

            try:
                published_dt = datetime.fromisoformat(published.replace("Z", "+00:00"))
            except ValueError:
                continue

            if published_dt < since:
                continue

            source_articles.append(
                {
                    "title": title,
                    "url": link,
                    "source": source,
                    "summary": summary,
                    "published": published,
                    "image_url": "",
                }
            )

        source_articles.sort(key=lambda item: item.get("published", ""), reverse=True)
        all_articles.extend(source_articles[:MAX_PER_SOURCE])

    all_articles.sort(key=lambda item: item.get("published", ""), reverse=True)
    return write_json(RSS_OUTPUT, all_articles)


if __name__ == "__main__":
    output = run()
    print(f"Saved RSS output to: {output}")
