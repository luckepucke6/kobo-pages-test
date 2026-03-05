from __future__ import annotations

import math
import re
from collections import Counter
from difflib import SequenceMatcher
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from app.models import CLUSTERED_OUTPUT, DEDUPED_OUTPUT, read_json, write_json

SIMILARITY_THRESHOLD = 0.6
EMBEDDING_THRESHOLD = 0.63
KEYWORD_OVERLAP_THRESHOLD = 0.14
MAX_EMBEDDING_TOKENS = 400
MAX_KEYWORDS = 18

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

TEXT_STOPWORDS = TITLE_STOPWORDS | {
    "that",
    "this",
    "will",
    "would",
    "into",
    "their",
    "they",
    "them",
    "about",
    "after",
    "before",
    "under",
    "över",
    "vid",
    "mot",
    "har",
    "hade",
    "kan",
    "ska",
    "som",
    "inte",
    "detta",
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


def _normalize_text_for_tokens(text: str) -> str:
    lowered = _clean(text).lower()
    lowered = re.sub(r"[^\w\s]", " ", lowered)
    return " ".join(lowered.split())


def _tokenize(text: str) -> list[str]:
    normalized = _normalize_text_for_tokens(text)
    return [
        token
        for token in normalized.split()
        if token not in TEXT_STOPWORDS and len(token) > 2 and not token.isdigit()
    ]


def _article_embedding(article: dict[str, Any]) -> dict[str, float]:
    combined = " ".join(
        [
            _clean(article.get("title", "")),
            _clean(article.get("summary", "")),
            _clean(article.get("text", ""))[:2500],
        ]
    )
    tokens = _tokenize(combined)[:MAX_EMBEDDING_TOKENS]
    if not tokens:
        return {}

    counts = Counter(tokens)
    total = float(sum(counts.values()))
    if total <= 0.0:
        return {}
    return {token: count / total for token, count in counts.items()}


def _cosine_similarity_sparse(vec_a: dict[str, float], vec_b: dict[str, float]) -> float:
    if not vec_a or not vec_b:
        return 0.0

    common_tokens = set(vec_a).intersection(vec_b)
    dot = sum(vec_a[token] * vec_b[token] for token in common_tokens)
    norm_a = math.sqrt(sum(value * value for value in vec_a.values()))
    norm_b = math.sqrt(sum(value * value for value in vec_b.values()))
    if norm_a == 0.0 or norm_b == 0.0:
        return 0.0
    return dot / (norm_a * norm_b)


def _article_keywords(article: dict[str, Any]) -> set[str]:
    title_tokens = _tokenize(_clean(article.get("title", "")))
    summary_tokens = _tokenize(_clean(article.get("summary", "")))
    text_tokens = _tokenize(_clean(article.get("text", ""))[:1800])

    weighted = Counter(title_tokens * 3 + summary_tokens * 2 + text_tokens)
    if not weighted:
        return set()

    return {token for token, _ in weighted.most_common(MAX_KEYWORDS)}


def _keyword_overlap(set_a: set[str], set_b: set[str]) -> float:
    if not set_a or not set_b:
        return 0.0
    union = set_a.union(set_b)
    if not union:
        return 0.0
    return len(set_a.intersection(set_b)) / float(len(union))


def _article_importance(article: dict[str, Any]) -> float:
    try:
        return float(article.get("importance_score", 0.0))
    except (TypeError, ValueError):
        return 0.0


def _article_quality(article: dict[str, Any]) -> float:
    base = _article_importance(article)
    text_len = len(_clean(article.get("text", "")).split())
    source_bonus = 0.5 if _clean(article.get("source_domain", "")) else 0.0
    return base + min(text_len / 400.0, 2.0) + source_bonus


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
        "embeddings": [_article_embedding(article) for article in articles],
        "keywords": [_article_keywords(article) for article in articles],
    }


def _pick_representative(cluster: dict[str, Any]) -> dict[str, Any]:
    articles = cluster.get("articles", []) if isinstance(cluster, dict) else []
    if not isinstance(articles, list) or not articles:
        return {}

    representative = max(articles, key=_article_quality)
    cluster_size = len(articles)
    boosted_score = _article_importance(representative) + math.log(max(cluster_size, 1))

    representative_id = id(representative)
    supporting_sources: list[str] = []
    supporting_info: list[str] = []
    related_articles: list[dict[str, str]] = []
    seen_supporting: set[str] = set()

    for article in articles:
        source_domain = _clean(article.get("source_domain", "")).lower()
        if source_domain and source_domain not in supporting_sources:
            supporting_sources.append(source_domain)

        related_articles.append(
            {
                "title": _clean(article.get("title", "")),
                "url": _clean(article.get("url", "")),
                "source_domain": source_domain,
            }
        )

        if id(article) == representative_id:
            continue

        support_text = _clean(article.get("summary", "")) or _clean(article.get("title", ""))
        if not support_text:
            continue
        key = support_text.lower()
        if key in seen_supporting:
            continue
        seen_supporting.add(key)
        supporting_info.append(support_text)

    output = dict(representative)
    output["cluster_id"] = _clean(cluster.get("cluster_id", ""))
    output["cluster_size"] = cluster_size
    output["sources_covering_event"] = list(cluster.get("source_domains", []))
    output["sources_count"] = int(cluster.get("sources_count", 0))
    output["topic_tags"] = list(cluster.get("topic_tags", []))
    output["supporting_sources"] = supporting_sources
    output["supporting_information"] = supporting_info[:8]
    output["related_articles"] = related_articles
    output["importance_score"] = round(boosted_score, 4)
    return output


def _cluster_similarity(article: dict[str, Any], cluster: dict[str, Any]) -> tuple[float, float, float, float]:
    normalized_title = normalize_title(article.get("title", ""))
    article_embedding = _article_embedding(article)
    article_keywords = _article_keywords(article)

    titles = cluster.get("normalized_titles", [])
    title_similarity = max(
        (_title_similarity(normalized_title, existing) for existing in titles if isinstance(existing, str)),
        default=0.0,
    )

    embeddings = cluster.get("embeddings", [])
    embedding_similarity = max(
        (
            _cosine_similarity_sparse(article_embedding, embedding)
            for embedding in embeddings
            if isinstance(embedding, dict)
        ),
        default=0.0,
    )

    keyword_sets = cluster.get("keywords", [])
    keyword_similarity = max(
        (
            _keyword_overlap(article_keywords, keyword_set)
            for keyword_set in keyword_sets
            if isinstance(keyword_set, set)
        ),
        default=0.0,
    )

    combined_similarity = (0.45 * title_similarity) + (0.4 * embedding_similarity) + (0.15 * keyword_similarity)
    return combined_similarity, title_similarity, embedding_similarity, keyword_similarity


def _should_join_cluster(
    combined_similarity: float,
    title_similarity: float,
    embedding_similarity: float,
    keyword_similarity: float,
) -> bool:
    if title_similarity >= SIMILARITY_THRESHOLD:
        return True
    if embedding_similarity >= EMBEDDING_THRESHOLD and keyword_similarity >= KEYWORD_OVERLAP_THRESHOLD:
        return True
    if title_similarity >= 0.5 and embedding_similarity >= 0.58 and keyword_similarity >= 0.12:
        return True
    return combined_similarity >= 0.6


def _nearest_hours_to_cluster(article: dict[str, Any], cluster: dict[str, Any]) -> float:
    article_published = _parse_datetime(str(article.get("published_at", article.get("published", ""))))
    if article_published is None:
        return 0.0

    cluster_times = [
        _parse_datetime(str(item.get("published_at", item.get("published", ""))))
        for item in cluster.get("articles", [])
        if isinstance(item, dict)
    ]
    cluster_times = [dt for dt in cluster_times if dt is not None]
    if not cluster_times:
        return 0.0

    return min(abs((article_published - dt).total_seconds()) / 3600.0 for dt in cluster_times)


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
        best_combined_similarity = 0.0
        best_title_similarity = 0.0
        best_embedding_similarity = 0.0
        best_keyword_similarity = 0.0

        for index, cluster in enumerate(clusters):
            combined_similarity, title_similarity, embedding_similarity, keyword_similarity = _cluster_similarity(article, cluster)
            if combined_similarity > best_combined_similarity:
                best_combined_similarity = combined_similarity
                best_title_similarity = title_similarity
                best_embedding_similarity = embedding_similarity
                best_keyword_similarity = keyword_similarity
                best_cluster_index = index

        allow_topic_match = (
            best_cluster_index >= 0
            and _topic_match_allowed(article, clusters[best_cluster_index], best_title_similarity)
        )

        should_join = _should_join_cluster(
            best_combined_similarity,
            best_title_similarity,
            best_embedding_similarity,
            best_keyword_similarity,
        )

        if should_join and best_cluster_index >= 0:
            candidate_cluster = clusters[best_cluster_index]
            nearest_hours = _nearest_hours_to_cluster(article, candidate_cluster)
            article_source = _clean(article.get("source_domain", "")).lower()
            cluster_sources = {
                _clean(item.get("source_domain", "")).lower()
                for item in candidate_cluster.get("articles", [])
                if isinstance(item, dict)
            }

            if nearest_hours > 72.0 and best_title_similarity < 0.65:
                should_join = False

            if article_source and article_source in cluster_sources:
                if best_title_similarity < 0.62 and not (
                    best_embedding_similarity >= 0.75 and best_keyword_similarity >= 0.28
                ):
                    should_join = False

        if best_cluster_index >= 0 and (should_join or allow_topic_match):
            clusters[best_cluster_index]["articles"].append(article)
            clusters[best_cluster_index]["normalized_titles"].append(normalized_title)
            clusters[best_cluster_index]["embeddings"].append(_article_embedding(article))
            clusters[best_cluster_index]["keywords"].append(_article_keywords(article))
            clusters[best_cluster_index]["topic_tags"] = sorted(
                set(clusters[best_cluster_index].get("topic_tags", [])) | _extract_topic_tags(article.get("title", ""))
            )
        else:
            clusters.append(
                {
                    "cluster_id": _event_key(article.get("title", "")) or normalized_title[:120],
                    "articles": [article],
                    "normalized_titles": [normalized_title],
                    "embeddings": [_article_embedding(article)],
                    "keywords": [_article_keywords(article)],
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
