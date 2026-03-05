from __future__ import annotations

import re
from pathlib import Path
from typing import Any

from app.models import CLUSTERED_OUTPUT, DEDUPED_OUTPUT, read_json, write_json

SIMILARITY_THRESHOLD = 0.6
PREFERRED_SWEDISH_DOMAINS = {"svt.se", "sr.se", "svd.se", "dn.se", "di.se"}
STOPWORDS = {
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
}


def _clean(value: Any) -> str:
    return " ".join(str(value or "").replace("\n", " ").split())


def _split_sentences(text: str) -> list[str]:
    clean = _clean(text)
    if not clean:
        return []
    return [part.strip() for part in re.split(r"(?<=[.!?])\s+", clean) if part.strip()]


def _tokens(title: str) -> set[str]:
    normalized = re.sub(r"[^\w\s]", " ", _clean(title).lower())
    return {token for token in normalized.split() if len(token) > 2 and token not in STOPWORDS}


def _jaccard(a: set[str], b: set[str]) -> float:
    if not a or not b:
        return 0.0
    union = a | b
    return len(a & b) / len(union) if union else 0.0


def _is_preferred(article: dict[str, Any]) -> bool:
    domain = _clean(article.get("source_domain", "")).lower()
    return any(domain == item or domain.endswith(f".{item}") for item in PREFERRED_SWEDISH_DOMAINS)


def _merge_facts(texts: list[str], max_sentences: int = 20) -> str:
    seen: set[str] = set()
    merged: list[str] = []
    for text in texts:
        for sentence in _split_sentences(text):
            key = sentence.lower().strip()
            if key in seen:
                continue
            seen.add(key)
            merged.append(sentence)
            if len(merged) >= max_sentences:
                return " ".join(merged)
    return " ".join(merged)


def _best_primary(cluster: list[dict[str, Any]]) -> dict[str, Any]:
    ranked = sorted(
        cluster,
        key=lambda article: (1 if _is_preferred(article) else 0, len(_clean(article.get("text", "")))),
        reverse=True,
    )
    return ranked[0]


def _best_image(cluster: list[dict[str, Any]]) -> str:
    preferred_images = [article for article in cluster if _is_preferred(article) and _clean(article.get("image_url", ""))]
    if preferred_images:
        return _clean(preferred_images[0].get("image_url", ""))
    for article in cluster:
        image = _clean(article.get("image_url", ""))
        if image:
            return image
    return ""


def _merge_cluster(cluster: list[dict[str, Any]]) -> dict[str, Any]:
    primary = _best_primary(cluster)

    merged_text = _merge_facts([_clean(article.get("text", "")) for article in cluster], max_sentences=24)
    merged_summary = _merge_facts([_clean(article.get("summary", "")) for article in cluster], max_sentences=8)

    unique_sources: list[str] = []
    source_urls: list[str] = []
    for article in cluster:
        source = _clean(article.get("source", ""))
        url = _clean(article.get("url", ""))
        if source and source not in unique_sources:
            unique_sources.append(source)
        if url and url not in source_urls:
            source_urls.append(url)

    return {
        "title": _clean(primary.get("title", "")),
        "url": _clean(primary.get("url", "")),
        "source_url": _clean(primary.get("source_url", primary.get("url", ""))),
        "source": " / ".join(unique_sources),
        "source_domain": _clean(primary.get("source_domain", "")),
        "published": _clean(primary.get("published", "")),
        "summary": merged_summary,
        "text": merged_text,
        "image_url": _best_image(cluster),
        "source_urls": source_urls,
    }


def run() -> Path:
    payload = read_json(DEDUPED_OUTPUT, default=[])
    if not isinstance(payload, list):
        raise ValueError("Expected list input from dedupe_articles")

    clusters: list[dict[str, Any]] = []

    for raw_article in payload:
        if not isinstance(raw_article, dict):
            continue
        article = dict(raw_article)
        article_tokens = _tokens(article.get("title", ""))

        if not article_tokens:
            clusters.append({"articles": [article], "token_sets": [set()]})
            continue

        best_index = -1
        best_similarity = 0.0
        for index, cluster in enumerate(clusters):
            token_sets: list[set[str]] = cluster["token_sets"]
            if not token_sets:
                continue
            score = max(_jaccard(article_tokens, token_set) for token_set in token_sets)
            if score > best_similarity:
                best_similarity = score
                best_index = index

        if best_index >= 0 and best_similarity > SIMILARITY_THRESHOLD:
            clusters[best_index]["articles"].append(article)
            clusters[best_index]["token_sets"].append(article_tokens)
        else:
            clusters.append({"articles": [article], "token_sets": [article_tokens]})

    merged = [_merge_cluster(cluster["articles"]) for cluster in clusters]
    return write_json(CLUSTERED_OUTPUT, merged)


if __name__ == "__main__":
    output = run()
    print(f"Saved clustered articles to: {output}")
