from __future__ import annotations

import math
import re
from difflib import SequenceMatcher
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from app.models import CLUSTERED_OUTPUT, DEDUPED_OUTPUT, read_json, write_json

SIMILARITY_THRESHOLD = 0.6

NOISE_PHRASES = [
    "as it happened",
    "live updates",
    "live blog",
    "live",
    "what we know",
    "latest updates",
    "latest",
    "breaking",
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
    "this",
    "that",
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
}

TOPIC_ALIASES = {
    "iran_conflict": ["iran", "iranska", "tehran", "teheran", "ayatollah"],
    "middle_east": ["middle east", "mellanostern", "mellanöstern", "gaza", "israel"],
    "evacuation": ["stranded", "strandsatt", "evacu", "charter", "flygkris", "resvagar", "resvägar"],
    "openai": ["openai", "altman"],
    "anthropic": ["anthropic", "amodei"],
    "nvidia": ["nvidia", "huang", "chip", "gpu", "semiconductor"],
    "inflation": ["inflation", "inflationen", "ranta", "ränta", "riksbank"],
    "oil_price": ["oil", "oljepris", "brent"],
}


def _clean(value: Any) -> str:
    return " ".join(str(value or "").replace("\n", " ").split())


def normalize_title(title: str) -> str:
    lowered = _clean(title).lower()
    no_parentheses = re.sub(r"\([^)]*\)", " ", lowered)
    no_separators = re.sub(r"[|•–—-]", " ", no_parentheses)
    no_punctuation = re.sub(r"[^\w\s]", " ", no_separators)
    normalized = " ".join(no_punctuation.split())
    for phrase in NOISE_PHRASES:
        normalized = re.sub(rf"\b{re.escape(phrase)}\b", " ", normalized)
    normalized = " ".join(normalized.split())
    return normalized


def _normalized_token_title(title: str) -> str:
    normalized = normalize_title(title)
    if not normalized:
        return ""
    tokens = [
        token
        for token in normalized.split()
        if token not in TITLE_STOPWORDS and len(token) > 2 and not token.isdigit()
    ]
    return " ".join(tokens)


def _sorted_token_title(title: str) -> str:
    tokenized = _normalized_token_title(title)
    if not tokenized:
        return ""
    return " ".join(sorted(tokenized.split()))


def _event_key(title: str) -> str:
    normalized = normalize_title(title)
    return normalized[:120]


def _parse_datetime(value: str) -> datetime | None:
    cleaned = _clean(value)
    if not cleaned:
        return None
    try:
        parsed = datetime.fromisoformat(cleaned.replace("Z", "+00:00"))
    except ValueError:
        return None
    if parsed.tzinfo is None:
        parsed = parsed.replace(tzinfo=timezone.utc)
    return parsed


def _extract_topic_tags(title: str) -> set[str]:
    normalized = normalize_title(title)
    if not normalized:
        return set()

    tags: set[str] = set()
    for topic, aliases in TOPIC_ALIASES.items():
        for alias in aliases:
            if re.search(rf"\b{re.escape(alias)}\b", normalized):
                tags.add(topic)
                break
    return tags


def _title_similarity(title_a: str, title_b: str) -> float:
    if not title_a or not title_b:
        return 0.0
    base_ratio = SequenceMatcher(None, title_a, title_b).ratio()
    token_a = _normalized_token_title(title_a)
    token_b = _normalized_token_title(title_b)
    token_ratio = SequenceMatcher(None, token_a, token_b).ratio() if token_a and token_b else 0.0
    sorted_a = _sorted_token_title(title_a)
    sorted_b = _sorted_token_title(title_b)
    sorted_ratio = SequenceMatcher(None, sorted_a, sorted_b).ratio() if sorted_a and sorted_b else 0.0
    return max(base_ratio, token_ratio, sorted_ratio)


def _article_importance(article: dict[str, Any]) -> float:
    try:
        return float(article.get("importance_score", 0.0))
    except (TypeError, ValueError):
        return 0.0


def _build_cluster(cluster_id: str, articles: list[dict[str, Any]]) -> dict[str, Any]:
    source_domains: list[str] = []
    for article in articles:
        source_domain = _clean(article.get("source_domain", "")).lower()
        if source_domain and source_domain not in source_domains:
            source_domains.append(source_domain)

    return {
        "cluster_id": cluster_id,
        "articles": articles,
        "sources_count": len(source_domains),
        "source_domains": source_domains,
        "normalized_titles": [normalize_title(article.get("title", "")) for article in articles],
        "topic_tags": sorted({tag for article in articles for tag in _extract_topic_tags(article.get("title", ""))}),
    }


def _pick_representative(cluster: dict[str, Any]) -> dict[str, Any]:
    articles = cluster.get("articles", []) if isinstance(cluster, dict) else []
    if not isinstance(articles, list) or not articles:
        return {}

    representative = max(articles, key=_article_importance)
    cluster_size = len(articles)
    boosted_score = _article_importance(representative) + math.log(max(cluster_size, 1))

    output = dict(representative)
    output["cluster_id"] = _clean(cluster.get("cluster_id", ""))
    output["cluster_size"] = cluster_size
    output["sources_covering_event"] = list(cluster.get("source_domains", []))
    output["sources_count"] = int(cluster.get("sources_count", 0))
    output["topic_tags"] = list(cluster.get("topic_tags", []))
    output["importance_score"] = round(boosted_score, 4)
    return output


def _topic_match_allowed(article: dict[str, Any], cluster: dict[str, Any], similarity: float) -> bool:
    article_tags = _extract_topic_tags(article.get("title", ""))
    cluster_tags = set(cluster.get("topic_tags", []))
    if not article_tags or not cluster_tags:
        return False

    shared = article_tags.intersection(cluster_tags)
    if not shared:
        return False

    article_published = _parse_datetime(str(article.get("published_at", article.get("published", ""))))
    cluster_times = [
        _parse_datetime(str(item.get("published_at", item.get("published", ""))))
        for item in cluster.get("articles", [])
        if isinstance(item, dict)
    ]
    cluster_times = [dt for dt in cluster_times if dt is not None]

    nearest_hours = 0.0
    if article_published is not None and cluster_times:
        nearest_hours = min(abs((article_published - dt).total_seconds()) / 3600.0 for dt in cluster_times)
        if nearest_hours > 48.0:
            return False

    shared_count = len(shared)
    if shared_count >= 2 and similarity >= 0.35:
        return True
    if shared_count >= 1 and similarity >= 0.5:
        return True
    if shared_count >= 1 and similarity >= 0.4 and nearest_hours <= 24.0:
        return True
    return False


def run() -> Path:
    payload = read_json(DEDUPED_OUTPUT, default=[])
    if not isinstance(payload, list):
        raise ValueError("Expected list input from dedupe_articles")

    clusters: list[dict[str, Any]] = []

    for raw_article in payload:
        if not isinstance(raw_article, dict):
            continue
        article = dict(raw_article)

        normalized_title = normalize_title(article.get("title", ""))
        if not normalized_title:
            continue

        best_cluster_index = -1
        best_similarity = 0.0

        for index, cluster in enumerate(clusters):
            titles = cluster.get("normalized_titles", [])
            if not isinstance(titles, list) or not titles:
                continue
            similarity = max(_title_similarity(normalized_title, existing) for existing in titles)
            if similarity > best_similarity:
                best_similarity = similarity
                best_cluster_index = index

        allow_topic_match = (
            best_cluster_index >= 0
            and _topic_match_allowed(article, clusters[best_cluster_index], best_similarity)
        )

        if best_cluster_index >= 0 and (best_similarity > SIMILARITY_THRESHOLD or allow_topic_match):
            clusters[best_cluster_index]["articles"].append(article)
            clusters[best_cluster_index]["normalized_titles"].append(normalized_title)
            clusters[best_cluster_index]["topic_tags"] = sorted(
                set(clusters[best_cluster_index].get("topic_tags", [])) | _extract_topic_tags(article.get("title", ""))
            )
        else:
            clusters.append(
                {
                    "cluster_id": _event_key(article.get("title", "")) or normalized_title[:120],
                    "articles": [article],
                    "normalized_titles": [normalized_title],
                    "topic_tags": sorted(_extract_topic_tags(article.get("title", ""))),
                }
            )

    cluster_payload = [
        _build_cluster(cluster_id=str(cluster.get("cluster_id", "")), articles=list(cluster.get("articles", [])))
        for cluster in clusters
    ]

    representatives = [_pick_representative(cluster) for cluster in cluster_payload]
    representatives = [article for article in representatives if article]
    representatives.sort(key=_article_importance, reverse=True)

    return write_json(CLUSTERED_OUTPUT, representatives)


if __name__ == "__main__":
    output = run()
    print(f"Saved clustered articles to: {output}")
