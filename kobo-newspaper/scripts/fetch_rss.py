from __future__ import annotations

import json
import re
from datetime import datetime, timedelta, timezone
from pathlib import Path
import time
from typing import Any

import feedparser
import requests

PROJECT_ROOT = Path(__file__).resolve().parents[1]
RAW_OUTPUT_PATH = PROJECT_ROOT / "pages" / "raw_articles.json"

PREFERRED_SWEDISH_SOURCES = {
    "SVT Nyheter",
    "Sveriges Radio",
    "SvD",
    "DN",
    "DI",
}

SECONDARY_INTERNATIONAL_SOURCES = {
    "Reuters",
    "BBC",
    "Guardian",
    "AP",
    "MIT Technology Review",
    "Ars Technica",
}

ALLOWED_SOURCES = PREFERRED_SWEDISH_SOURCES | SECONDARY_INTERNATIONAL_SOURCES

SOURCE_PRIORITY = {
    "SVT Nyheter": 1,
    "Sveriges Radio": 2,
    "SvD": 3,
    "DN": 4,
    "DI": 5,
    "Reuters": 6,
    "BBC": 7,
    "Guardian": 8,
    "AP": 9,
    "MIT Technology Review": 10,
    "Ars Technica": 11,
}

SOURCE_FETCH_ORDER = [
    "SVT Nyheter",
    "Sveriges Radio",
    "SvD",
    "DN",
    "DI",
    "Reuters",
    "BBC",
    "Guardian",
    "AP",
    "MIT Technology Review",
    "Ars Technica",
]

MAX_ARTICLES_PER_SOURCE = 3

SOURCE_ALIASES = {
    "reuters": "Reuters",
    "bbc": "BBC",
    "the guardian": "Guardian",
    "guardian": "Guardian",
    "associated press": "AP",
    "ap news": "AP",
    "ap": "AP",
    "svt": "SVT Nyheter",
    "svt nyheter": "SVT Nyheter",
    "sveriges radio": "Sveriges Radio",
    "sr": "Sveriges Radio",
    "dagens nyheter": "DN",
    "dn": "DN",
    "svenska dagbladet": "SvD",
    "svd": "SvD",
    "dagens industri": "DI",
    "di": "DI",
    "mit technology review": "MIT Technology Review",
    "technology review": "MIT Technology Review",
    "ars technica": "Ars Technica",
}

GENERAL_FEEDS: list[tuple[str, str]] = [
    ("https://www.svt.se/nyheter/rss.xml", "SVT Nyheter"),
    ("https://feeds.sr.se/senasteekot", "Sveriges Radio"),
    ("https://www.svd.se/?service=rss", "SvD"),
    ("https://www.dn.se/rss/", "DN"),
    ("https://www.di.se/rss/", "DI"),
    ("https://www.reuters.com/world/rss", "Reuters"),
    ("https://feeds.bbci.co.uk/news/world/rss.xml", "BBC"),
    ("https://www.theguardian.com/world/rss", "Guardian"),
    ("https://apnews.com/hub/apf-topnews?output=rss", "AP"),
]

TECH_FEEDS: list[tuple[str, str]] = [
    ("https://www.technologyreview.com/feed/", "MIT Technology Review"),
    ("https://feeds.arstechnica.com/arstechnica/index", "Ars Technica"),
]

GENERAL_LIMIT = 20
TECH_LIMIT = 15
REQUEST_TIMEOUT = 10
FETCH_USER_AGENT = (
    "Mozilla/5.0 (Macintosh; Intel Mac OS X 14_0) "
    "AppleWebKit/537.36 (KHTML, like Gecko) "
    "Chrome/122.0.0.0 Safari/537.36"
)


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


def _extract_article_text(article_url: str) -> str:
    if not article_url:
        return ""

    headers = {"User-Agent": FETCH_USER_AGENT}
    try:
        response = requests.get(article_url, timeout=REQUEST_TIMEOUT, headers=headers)
        response.raise_for_status()
    except requests.RequestException:
        return ""

    html = response.text or ""
    html = re.sub(r"<script[\s\S]*?</script>", " ", html, flags=re.IGNORECASE)
    html = re.sub(r"<style[\s\S]*?</style>", " ", html, flags=re.IGNORECASE)

    paragraph_matches = re.findall(r"<p[^>]*>([\s\S]*?)</p>", html, flags=re.IGNORECASE)
    if paragraph_matches:
        text_blocks = [re.sub(r"<[^>]+>", " ", block) for block in paragraph_matches]
        article_text = " ".join(" ".join(block.split()) for block in text_blocks if block.strip())
    else:
        plain = re.sub(r"<[^>]+>", " ", html)
        article_text = " ".join(plain.split())

    return article_text[:8000]


def _normalize_topic_key(title: str, summary: str) -> str:
    base_text = f"{title} {summary}".lower()
    clean_text = re.sub(r"[^\w\s]", " ", base_text)
    tokens = [token for token in clean_text.split() if len(token) > 3]

    stopwords = {
        "och",
        "med",
        "från",
        "det",
        "this",
        "that",
        "from",
        "about",
        "says",
        "också",
        "after",
        "their",
        "into",
    }
    filtered = [token for token in tokens if token not in stopwords]
    if not filtered:
        return ""

    return " ".join(filtered[:8])


def _source_priority(source_name: str) -> int:
    return SOURCE_PRIORITY.get(source_name, 99)


def _published_sort_key(article: dict[str, Any]) -> str:
    return str(article.get("published") or "")


def _prefer_article(candidate: dict[str, Any], current: dict[str, Any]) -> bool:
    candidate_priority = _source_priority(str(candidate.get("source_name", "")))
    current_priority = _source_priority(str(current.get("source_name", "")))

    if candidate_priority != current_priority:
        return candidate_priority < current_priority

    return _published_sort_key(candidate) > _published_sort_key(current)


def _deduplicate_by_topic(articles: list[dict[str, Any]]) -> list[dict[str, Any]]:
    selected_by_topic: dict[str, dict[str, Any]] = {}

    for article in articles:
        topic_key = str(article.get("topic_key") or "")
        if not topic_key:
            topic_key = str(article.get("title") or "").lower()

        existing = selected_by_topic.get(topic_key)
        if existing is None or _prefer_article(article, existing):
            selected_by_topic[topic_key] = article

    deduplicated = list(selected_by_topic.values())
    deduplicated.sort(key=lambda item: str(item.get("published", "")), reverse=True)
    return deduplicated


def _deduplicate_source_topic(articles: list[dict[str, Any]]) -> list[dict[str, Any]]:
    selected_by_source_topic: dict[tuple[str, str], dict[str, Any]] = {}

    for article in articles:
        source_name = str(article.get("source_name") or "")
        topic_key = str(article.get("topic_key") or "")
        if not source_name or not topic_key:
            continue

        key = (source_name, topic_key)
        existing = selected_by_source_topic.get(key)
        if existing is None:
            selected_by_source_topic[key] = article
            continue

        if str(article.get("published", "")) > str(existing.get("published", "")):
            selected_by_source_topic[key] = article

    deduplicated = list(selected_by_source_topic.values())
    deduplicated.sort(key=lambda item: str(item.get("published", "")), reverse=True)
    return deduplicated


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


def _extract_entries(feed_url: str, since: datetime, default_source: str) -> list[dict[str, Any]]:
    parsed = feedparser.parse(feed_url)
    articles: list[dict[str, Any]] = []
    feed_title = str(parsed.feed.get("title") or "")
    feed_source = _normalize_source(feed_title) or default_source

    for entry in parsed.entries:
        title = (entry.get("title") or "").strip()
        link = (entry.get("link") or "").strip()
        summary = (entry.get("summary") or entry.get("description") or "").strip()
        published_dt = _extract_published_datetime(entry)
        image_url = _extract_image_url(entry)
        article_text = _extract_article_text(link)

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

        topic_key = _normalize_topic_key(title, summary)

        articles.append(
            {
                "title": title,
                "link": link,
                "published": published_dt.isoformat(),
                "summary": summary,
                "article_text": article_text,
                "source": source_name,
                "source_name": source_name,
                "image_url": image_url,
                "topic_key": topic_key,
            }
        )

    return articles


def _sort_by_published_desc(articles: list[dict[str, Any]]) -> list[dict[str, Any]]:
    return sorted(articles, key=lambda item: item["published"], reverse=True)


def _sort_feeds_by_priority(feeds: list[tuple[str, str]]) -> list[tuple[str, str]]:
    order_index = {source: index for index, source in enumerate(SOURCE_FETCH_ORDER)}
    return sorted(feeds, key=lambda feed: order_index.get(feed[1], 999))


def _limit_articles_per_source(
    articles: list[dict[str, Any]], max_per_source: int = MAX_ARTICLES_PER_SOURCE
) -> list[dict[str, Any]]:
    source_counts: dict[str, int] = {}
    limited: list[dict[str, Any]] = []

    for article in articles:
        source_name = str(article.get("source_name") or "")
        current_count = source_counts.get(source_name, 0)
        if current_count >= max_per_source:
            continue

        limited.append(article)
        source_counts[source_name] = current_count + 1

    return limited


def fetch_all_news() -> dict[str, list[dict[str, str]]]:
    since = datetime.now(timezone.utc) - timedelta(hours=24)
    general_news: list[dict[str, str]] = []
    tech_news: list[dict[str, str]] = []

    for url, source in _sort_feeds_by_priority(GENERAL_FEEDS):
        general_news.extend(_extract_entries(url, since, source))

    for url, source in _sort_feeds_by_priority(TECH_FEEDS):
        tech_news.extend(_extract_entries(url, since, source))

    general_news = _sort_by_published_desc(general_news)
    tech_news = _sort_by_published_desc(tech_news)

    general_news = _limit_articles_per_source(general_news)
    tech_news = _limit_articles_per_source(tech_news)

    general_news = _deduplicate_source_topic(general_news)
    tech_news = _deduplicate_source_topic(tech_news)

    general_news = _deduplicate_by_topic(general_news)[:GENERAL_LIMIT]
    tech_news = _deduplicate_by_topic(tech_news)[:TECH_LIMIT]

    for item in general_news + tech_news:
        item.pop("topic_key", None)

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
