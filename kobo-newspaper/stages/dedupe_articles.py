from __future__ import annotations

import math
import re
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from app.models import DEDUPED_OUTPUT, EXTRACTED_OUTPUT, read_json, write_json

PREFERRED_SWEDISH_DOMAINS = {"svt.se", "sr.se", "sverigesradio.se", "svd.se", "dn.se", "di.se"}
MAX_PRECLUSTER_ARTICLES = 60

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

SOURCE_AUTHORITY_WEIGHTS: dict[str, float] = {
    "svt.se": 3.0,
    "dn.se": 3.0,
    "svd.se": 3.0,
    "di.se": 2.0,
    "bbc.com": 2.0,
    "theguardian.com": 2.0,
}

IMPORTANCE_KEYWORDS = [
    "geopolitics",
    "economy",
    "ai",
    "technology",
    "war",
    "election",
]

AI_TECH_KEYWORDS = [
    "ai",
    "artificial intelligence",
    "machine learning",
    "large language model",
    "llm",
    "openai",
    "anthropic",
    "deepmind",
    "nvidia",
    "gpu",
    "semiconductor",
]

ECONOMY_KEYWORDS = [
    "inflation",
    "interest rate",
    "central bank",
    "market",
    "stock",
    "economy",
    "oil",
    "bank",
]

SWEDEN_KEYWORDS = [
    "sweden",
    "sverige",
    "kristersson",
    "riksdag",
    "regering",
    "stockholm",
]

SCIENCE_KEYWORDS = [
    "science",
    "forskning",
    "climate",
    "klimat",
    "miljö",
    "environment",
    "utsläpp",
    "energi",
]

MAX_AI_TECH_ARTICLES = 4
MIN_SWEDEN_ARTICLES = 3
MIN_WORLD_ARTICLES = 3

PRODUCT_REVIEW_KEYWORDS = [
    "review",
    "best",
    "guide",
    "tested",
    "top 10",
    "comparison",
    "vs",
]

OPINION_KEYWORDS = [
    "opinion",
    "analysis",
    "editorial",
    "column",
    "insändare",
    "debatt",
]

LIFESTYLE_KEYWORDS = [
    "headphones",
    "earbuds",
    "fitness",
    "diet",
    "recipe",
    "travel",
    "hotel",
    "fashion",
]

TITLE_STOPWORDS = {
    "the",
    "a",
    "an",
    "and",
    "or",
    "for",
    "to",
    "of",
    "in",
    "on",
    "at",
    "with",
    "from",
    "by",
    "is",
    "are",
    "det",
    "den",
    "en",
    "ett",
    "och",
    "eller",
    "för",
    "med",
    "som",
    "att",
    "från",
    "om",
    "på",
    "i",
    "av",
    "till",
    "nu",
    "idag",
}


def _clean(value: Any) -> str:
    return " ".join(str(value or "").replace("\n", " ").split())


def _normalize_title(title: str) -> str:
    text = _clean(title).lower()
    text = re.sub(r"[^\w\s]", " ", text)
    return " ".join(text.split())


def _normalized_headline_key(title: str) -> str:
    normalized = _normalize_title(title)
    if not normalized:
        return ""
    tokens = [token for token in normalized.split() if token not in TITLE_STOPWORDS]
    return " ".join(tokens)[:150]


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
    if any(keyword in title for keyword in banned):
        return True

    if any(keyword in title for keyword in PRODUCT_REVIEW_KEYWORDS):
        return True

    if any(keyword in title for keyword in OPINION_KEYWORDS):
        return True

    if any(keyword in title for keyword in LIFESTYLE_KEYWORDS):
        return True

    return False


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


def compute_importance_score(article: dict[str, Any]) -> float:
    now = datetime.now(timezone.utc)
    recency = _recency_score(article, now)
    recency_score = 1.0 + (2.0 * recency)

    source_domain = _clean(article.get("source_domain", article.get("source", ""))).lower()
    source_weight = SOURCE_AUTHORITY_WEIGHTS.get(source_domain, 1.0)

    combined_text = " ".join(
        [
            _clean(article.get("title", "")).lower(),
            _clean(article.get("summary", "")).lower(),
            _clean(article.get("text", "")).lower(),
        ]
    )
    combined_text = re.sub(r"[^\w\s]", " ", combined_text)
    combined_text = " ".join(combined_text.split())

    keyword_matches = 0
    for keyword in IMPORTANCE_KEYWORDS:
        pattern = r"\b" + re.escape(keyword.lower()) + r"\b"
        if re.search(pattern, combined_text):
            keyword_matches += 1

    keyword_score = 1.0 + (0.35 * keyword_matches)

    source_coverage_count = int(article.get("source_coverage_count", 1) or 1)
    cluster_size_bonus = 1.0 + (0.25 * math.log(max(source_coverage_count, 1) + 1.0))

    importance_score = recency_score * source_weight * keyword_score * cluster_size_bonus
    return max(importance_score, 0.0)


def _classify_category(article: dict[str, Any]) -> str:
    def contains_keyword(text: str, keyword: str) -> bool:
        pattern = r"\b" + re.escape(keyword.lower()) + r"\b"
        return re.search(pattern, text) is not None

    def contains_any_keyword(text: str, keywords: list[str]) -> bool:
        return any(contains_keyword(text, keyword) for keyword in keywords)

    text = " ".join(
        [
            _clean(article.get("title", "")).lower(),
            _clean(article.get("text", "")).lower(),
        ]
    )
    text = re.sub(r"[^\w\s]", " ", text)
    text = " ".join(text.split())

    if contains_any_keyword(text, SWEDEN_KEYWORDS):
        return "Sweden"
    if contains_any_keyword(text, ECONOMY_KEYWORDS):
        return "Economy"
    for keyword in AI_TECH_KEYWORDS:
        if contains_keyword(text, keyword):
            return "AI_Tech"
    if contains_any_keyword(text, SCIENCE_KEYWORDS):
        return "Science"
    return "World"


def _pick_top_from_category(articles: list[dict[str, Any]], category: str, limit: int) -> list[dict[str, Any]]:
    matches = [article for article in articles if article.get("category") == category]
    matches.sort(key=lambda item: float(item.get("importance_score", 0.0)), reverse=True)
    return matches[:limit]


def _balanced_selection(sorted_articles: list[dict[str, Any]], final_limit: int) -> list[dict[str, Any]]:
    selected: list[dict[str, Any]] = []
    selected_ids: set[int] = set()

    def _add_article(article: dict[str, Any]) -> None:
        article_id = id(article)
        if article_id in selected_ids:
            return
        selected.append(article)
        selected_ids.add(article_id)

    for article in _pick_top_from_category(sorted_articles, "Sweden", MIN_SWEDEN_ARTICLES):
        if len(selected) >= final_limit:
            break
        _add_article(article)

    for article in _pick_top_from_category(sorted_articles, "World", MIN_WORLD_ARTICLES):
        if len(selected) >= final_limit:
            break
        _add_article(article)

    while len(selected) < final_limit:
        remaining = [article for article in sorted_articles if id(article) not in selected_ids]
        if not remaining:
            break

        ai_count = sum(1 for article in selected if article.get("category") == "AI_Tech")

        best_candidate: dict[str, Any] | None = None
        best_adjusted_score = float("-inf")
        for candidate in remaining:
            adjusted_score = float(candidate.get("importance_score", 0.0))
            if candidate.get("category") == "AI_Tech" and ai_count >= MAX_AI_TECH_ARTICLES:
                adjusted_score *= 0.75

            if adjusted_score > best_adjusted_score:
                best_adjusted_score = adjusted_score
                best_candidate = candidate

        if best_candidate is None:
            break

        if best_candidate.get("category") == "AI_Tech" and ai_count >= MAX_AI_TECH_ARTICLES:
            best_candidate["importance_score"] = round(float(best_candidate.get("importance_score", 0.0)) * 0.75, 4)

        _add_article(best_candidate)

    selected.sort(
        key=lambda item: (
            float(item.get("importance_score", 0.0)),
            str(item.get("published_at", item.get("published", ""))),
        ),
        reverse=True,
    )
    return selected[:final_limit]


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

    for article in deduped:
        event = _event_key(article.get("title", ""))
        source_count = len(source_coverage_by_event.get(event, set()))
        article["source_coverage_count"] = source_count
        score = compute_importance_score(article)
        article["importance_score"] = round(score, 4)
        article["category"] = _classify_category(article)

    deduped.sort(
        key=lambda item: (
            float(item.get("importance_score", 0.0)),
            str(item.get("published_at", item.get("published", ""))),
        ),
        reverse=True,
    )

    deduped_by_headline_key: dict[str, dict[str, Any]] = {}
    for article in deduped:
        key = _normalized_headline_key(article.get("title", ""))
        if not key:
            continue

        existing = deduped_by_headline_key.get(key)
        if existing is None:
            deduped_by_headline_key[key] = article
            continue

        if float(article.get("importance_score", 0.0)) > float(existing.get("importance_score", 0.0)):
            deduped_by_headline_key[key] = article

    deduped = list(deduped_by_headline_key.values())
    deduped.sort(
        key=lambda item: (
            float(item.get("importance_score", 0.0)),
            str(item.get("published_at", item.get("published", ""))),
        ),
        reverse=True,
    )
    limit = min(MAX_PRECLUSTER_ARTICLES, len(deduped))
    deduped = _balanced_selection(deduped, limit)

    return write_json(DEDUPED_OUTPUT, deduped)


if __name__ == "__main__":
    output = run()
    print(f"Saved deduplicated articles to: {output}")
