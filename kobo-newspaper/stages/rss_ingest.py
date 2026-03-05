from __future__ import annotations

import random
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any
from urllib.parse import urlparse

import feedparser

from app.models import RSS_OUTPUT, clean_text, write_json

SOURCE_FEEDS: list[tuple[str, str]] = [
    ("https://www.svt.se/nyheter/rss.xml", "SVT"),
    ("https://feeds.sr.se/senasteekot", "Sveriges Radio"),
    ("https://www.dn.se/rss/", "DN"),
    ("https://www.svd.se/?service=rss", "SvD"),
    ("https://www.di.se/rss/", "DI"),
    ("https://www.reuters.com/world/rss", "Reuters"),
    ("http://feeds.bbci.co.uk/news/world/rss.xml", "BBC World"),
    ("http://feeds.bbci.co.uk/news/technology/rss.xml", "BBC Technology"),
    ("https://apnews.com/apf-topnews", "Associated Press"),
    ("https://apnews.com/hub/apf-topnews?output=rss", "Associated Press"),
    ("https://www.theguardian.com/world/rss", "The Guardian World"),
    ("https://www.theguardian.com/technology/rss", "The Guardian Technology"),
    ("https://techcrunch.com/feed/", "TechCrunch"),
    ("https://www.wired.com/feed/rss", "Wired"),
    ("https://www.technologyreview.com/feed/", "MIT Technology Review"),
    ("https://www.theverge.com/rss/index.xml", "The Verge"),
]

SWEDISH_PRIORITY_DOMAINS = [
    "svt.se",
    "sverigesradio.se",
    "dn.se",
    "svd.se",
    "di.se",
]

MAX_ITEMS_PER_FEED = 20


def _extract_published(entry: dict[str, Any]) -> str:
    parsed = entry.get("published_parsed") or entry.get("updated_parsed")
    if not parsed:
        return ""
    return datetime(*parsed[:6], tzinfo=timezone.utc).isoformat()


def _extract_domain(url: str) -> str:
    domain = urlparse(clean_text(url)).netloc.lower()
    if domain.startswith("www."):
        domain = domain[4:]
    return domain


def _swedish_priority_boost(source_domain: str) -> int:
    normalized = clean_text(source_domain).lower()
    return 1 if any(normalized == domain or normalized.endswith(f".{domain}") for domain in SWEDISH_PRIORITY_DOMAINS) else 0


def run() -> Path:
    since = datetime.now(timezone.utc) - timedelta(hours=36)
    all_articles: list[dict[str, Any]] = []
    seen_urls: set[str] = set()

    for feed_url, source in SOURCE_FEEDS:
        parsed = feedparser.parse(feed_url)

        for entry in parsed.entries[:MAX_ITEMS_PER_FEED]:
            title = clean_text(entry.get("title", ""))
            link = clean_text(entry.get("link", ""))
            summary = clean_text(entry.get("summary", entry.get("description", "")))
            published = _extract_published(entry)

            if not title or not link or not published:
                continue

            if link in seen_urls:
                continue

            try:
                published_dt = datetime.fromisoformat(published.replace("Z", "+00:00"))
            except ValueError:
                continue

            if published_dt < since:
                continue

            seen_urls.add(link)

            source_domain = _extract_domain(link)
            swedish_boost = _swedish_priority_boost(source_domain)

            all_articles.append(
                {
                    "title": title,
                    "url": link,
                    "source_domain": source_domain,
                    "published_at": published,
                    "feed_url": feed_url,
                    "source": source,
                    "summary": summary,
                    "published": published,
                    "swedish_source_boost": swedish_boost,
                    "image_url": "",
                }
            )

    random.shuffle(all_articles)

    all_articles.sort(
        key=lambda item: (int(item.get("swedish_source_boost", 0)), item.get("published_at", "")),
        reverse=True,
    )

    unique_domains = {
        clean_text(item.get("source_domain", "")).lower()
        for item in all_articles
        if clean_text(item.get("source_domain", ""))
    }
    print(f"total RSS items collected: {len(all_articles)}")
    print(f"unique domains count: {len(unique_domains)}")

    return write_json(RSS_OUTPUT, all_articles)


if __name__ == "__main__":
    output = run()
    print(f"Saved RSS output to: {output}")
