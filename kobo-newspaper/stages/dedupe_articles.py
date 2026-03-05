from __future__ import annotations

import math
import re
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from app.models import DEDUPED_OUTPUT, EXTRACTED_OUTPUT, read_json, write_json

PREFERRED_SWEDISH_DOMAINS = {"svt.se", "sr.se", "sverigesradio.se", "svd.se", "dn.se", "di.se"}
FINAL_ARTICLE_COUNT = 12

BANNED_KEYWORDS = [
    "sport",
    "match",
    "cupen",
    "allsvenskan",
    "nhl",
    "nba",
    "fotboll",
    "hockey",
    "väder",
    "storm",
    "snö",
    "regn",
    "temperatur",
    "lokalt",
]

LOCAL_CITY_KEYWORDS = [
    "stockholm",
    "göteborg",
    "malmö",
    "uppsala",
    "västerås",
    "örebro",
    "linköping",
    "helsingborg",
]

TOPIC_KEYWORDS = {
    "geopolitics": [
        "iran",
        "israel",
        "gaza",
        "ukraina",
        "ryssland",
        "kina",
        "taiwan",
        "nato",
        "eu",
        "krig",
    ],
    "swedish_politics": [
        "regeringen",
        "riksdagen",
        "statsminister",
        "budget",
        "asyl",
        "migration",
    ],
    "economy": [
        "inflation",
        "ränta",
        "riksbank",
        "börs",
        "bank",
        "marknad",
        "oljepris",
    ],
    "ai_tech": [
        "ai",
        "artificial intelligence",
        "machine learning",
        "llm",
        "openai",
        "anthropic",
        "deepmind",
        "nvidia",
        "chip",
        "semiconductor",
        "model",
    ],
}


def _clean(value: Any) -> str:
    return " ".join(str(value or "").replace("\n", " ").split())


def _normalize_title(title: str) -> str:
    text = _clean(title).lower()
    text = re.sub(r"[^\w\s]", " ", text)
    return " ".join(text.split())


def _event_key(title: str) -> str:
    normalized = _normalize_title(title)
    tokens = normalized.split()
    if not tokens:
        return ""
    return " ".join(tokens[:8])


def _split_sentences(text: str) -> list[str]:
    clean = _clean(text)
    if not clean:
        return []
    return [part.strip() for part in re.split(r"(?<=[.!?])\s+", clean) if part.strip()]


def _remove_duplicate_sentences(text: str) -> str:
    seen: set[str] = set()
    unique: list[str] = []
    for sentence in _split_sentences(text):
        key = sentence.lower().strip()
        if key in seen:
            continue
        seen.add(key)
        unique.append(sentence)
    return " ".join(unique)


def _remove_duplicate_paragraphs(text: str) -> str:
    parts = [part.strip() for part in re.split(r"\n\s*\n", str(text or "")) if part.strip()]
    if not parts:
        return _clean(text)
    seen: set[str] = set()
    unique: list[str] = []
    for part in parts:
        normalized = _clean(part).lower()
        if normalized in seen:
            continue
        seen.add(normalized)
        unique.append(_clean(part))
    return "\n\n".join(unique)


def _clean_article_text(text: str) -> str:
    without_duplicate_paragraphs = _remove_duplicate_paragraphs(text)
    return _remove_duplicate_sentences(without_duplicate_paragraphs)


def _is_preferred(article: dict[str, Any]) -> bool:
    domain = _clean(article.get("source_domain", "")).lower()
    return any(domain == item or domain.endswith(f".{item}") for item in PREFERRED_SWEDISH_DOMAINS)


def _is_low_relevance(article: dict[str, Any]) -> bool:
    title = _normalize_title(article.get("title", ""))
    if not title:
        return True

    banned = BANNED_KEYWORDS + LOCAL_CITY_KEYWORDS
    return any(keyword in title for keyword in banned)


def _parse_datetime(value: str) -> datetime | None:
    cleaned = _clean(value)
    if not cleaned:
        return None
    try:
        return datetime.fromisoformat(cleaned.replace("Z", "+00:00"))
    except ValueError:
        return None


def _topic_score(article: dict[str, Any]) -> int:
    text = " ".join([
        _normalize_title(article.get("title", "")),
        _clean(article.get("summary", "")).lower(),
    ])

    score = 0
    for keywords in TOPIC_KEYWORDS.values():
        for keyword in keywords:
            if keyword in text:
                score += 1
    return score


def _recency_score(article: dict[str, Any], now: datetime) -> float:
    published_value = str(article.get("published_at", article.get("published", "")))
    published_dt = _parse_datetime(published_value)
    if published_dt is None:
        return 0.0
    if published_dt.tzinfo is None:
        published_dt = published_dt.replace(tzinfo=timezone.utc)

    age_hours = max((now - published_dt).total_seconds() / 3600.0, 0.0)
    return max(0.0, 1.0 - (age_hours / 48.0))


def _importance_score(article: dict[str, Any], source_count: int, now: datetime) -> float:
    topic = float(_topic_score(article))
    recency = _recency_score(article, now)
    swedish_boost = 1.0 if _is_preferred(article) else 0.0
    coverage = math.log(max(source_count, 1))
    return (3.0 * topic) + (4.0 * recency) + (2.0 * swedish_boost) + (1.5 * coverage)


def _choose_best(current: dict[str, Any], candidate: dict[str, Any]) -> dict[str, Any]:
    if _is_preferred(current) != _is_preferred(candidate):
        return current if _is_preferred(current) else candidate

    current_len = len(_clean(current.get("text", "")))
    candidate_len = len(_clean(candidate.get("text", "")))
    return current if current_len >= candidate_len else candidate


def run() -> Path:
    payload = read_json(EXTRACTED_OUTPUT, default=[])
    if not isinstance(payload, list):
        raise ValueError("Expected list input from extract_articles")

    deduped_by_title: dict[str, dict[str, Any]] = {}
    source_coverage_by_event: dict[str, set[str]] = {}

    for raw in payload:
        if not isinstance(raw, dict):
            continue

        article = dict(raw)
        article["title"] = _clean(article.get("title", ""))
        article["text"] = _clean_article_text(str(article.get("text", "")))
        article["summary"] = _clean_article_text(str(article.get("summary", "")))

        if _is_low_relevance(article):
            continue

        normalized = _normalize_title(article.get("title", ""))
        if not normalized:
            continue

        event = _event_key(article.get("title", ""))
        source_domain = _clean(article.get("source_domain", article.get("source", "")).lower())
        source_coverage_by_event.setdefault(event, set()).add(source_domain)

        existing = deduped_by_title.get(normalized)
        if existing is None:
            deduped_by_title[normalized] = article
            continue

        deduped_by_title[normalized] = _choose_best(existing, article)

    deduped = list(deduped_by_title.values())

    now = datetime.now(timezone.utc)
    for article in deduped:
        event = _event_key(article.get("title", ""))
        source_count = len(source_coverage_by_event.get(event, set()))
        score = _importance_score(article, source_count=source_count, now=now)
        article["importance_score"] = round(score, 4)

    deduped.sort(
        key=lambda item: (
            float(item.get("importance_score", 0.0)),
            str(item.get("published_at", item.get("published", ""))),
        ),
        reverse=True,
    )
    deduped = deduped[:FINAL_ARTICLE_COUNT]

    return write_json(DEDUPED_OUTPUT, deduped)


if __name__ == "__main__":
    output = run()
    print(f"Saved deduplicated articles to: {output}")
