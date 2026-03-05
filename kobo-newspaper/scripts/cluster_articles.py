from __future__ import annotations

import json
import re
from pathlib import Path
from typing import Any

PROJECT_ROOT = Path(__file__).resolve().parents[1]
INPUT_PATH = PROJECT_ROOT / "pages" / "deduped_articles.json"
OUTPUT_PATH = PROJECT_ROOT / "pages" / "clustered_articles.json"

SIMILARITY_THRESHOLD = 0.6
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
PREFERRED_SWEDISH_DOMAINS = {
    "svt.se",
    "sr.se",
    "svd.se",
    "dn.se",
    "di.se",
}


def _clean_text(value: Any) -> str:
    return " ".join(str(value or "").replace("\n", " ").split())


def _split_sentences(text: str) -> list[str]:
    cleaned = _clean_text(text)
    if not cleaned:
        return []
    return [part.strip() for part in re.split(r"(?<=[.!?])\s+", cleaned) if part.strip()]


def _tokenize_headline(headline: str) -> set[str]:
    normalized = re.sub(r"[^\w\s]", " ", _clean_text(headline).lower())
    return {token for token in normalized.split() if len(token) > 2 and token not in STOPWORDS}


def _jaccard_similarity(tokens_a: set[str], tokens_b: set[str]) -> float:
    if not tokens_a or not tokens_b:
        return 0.0
    union = tokens_a | tokens_b
    if not union:
        return 0.0
    return len(tokens_a & tokens_b) / len(union)


def _is_preferred_swedish_source(article: dict[str, Any]) -> bool:
    domain = _clean_text(article.get("source_domain", "")).lower()
    if domain and any(domain == preferred or domain.endswith(f".{preferred}") for preferred in PREFERRED_SWEDISH_DOMAINS):
        return True

    source_text = _clean_text(article.get("source", "")).lower()
    markers = {"svt", "sveriges radio", "svd", "dn", "di"}
    return any(marker in source_text for marker in markers)


def _merge_unique_sentences(text_blocks: list[str], max_sentences: int = 18) -> str:
    seen: set[str] = set()
    merged: list[str] = []

    for block in text_blocks:
        for sentence in _split_sentences(block):
            normalized = sentence.lower().strip()
            if normalized in seen:
                continue
            seen.add(normalized)
            merged.append(sentence)
            if len(merged) >= max_sentences:
                return " ".join(merged)

    return " ".join(merged)


def _pick_best_image(cluster: list[dict[str, Any]]) -> str:
    preferred_with_image = [
        article for article in cluster if _is_preferred_swedish_source(article) and _clean_text(article.get("image_url", ""))
    ]
    if preferred_with_image:
        return _clean_text(preferred_with_image[0].get("image_url", ""))

    for article in cluster:
        image_url = _clean_text(article.get("image_url", ""))
        if image_url:
            return image_url
    return ""


def _pick_primary_article(cluster: list[dict[str, Any]]) -> dict[str, Any]:
    sorted_cluster = sorted(
        cluster,
        key=lambda article: (
            1 if _is_preferred_swedish_source(article) else 0,
            len(_clean_text(article.get("text", ""))),
        ),
        reverse=True,
    )
    return sorted_cluster[0]


def _merge_cluster(cluster: list[dict[str, Any]]) -> dict[str, Any]:
    primary = _pick_primary_article(cluster)

    combined_text = _merge_unique_sentences([_clean_text(article.get("text", "")) for article in cluster], max_sentences=22)
    combined_summary = _merge_unique_sentences([_clean_text(article.get("summary", "")) for article in cluster], max_sentences=8)

    sources: list[str] = []
    urls: list[str] = []
    for article in cluster:
        source = _clean_text(article.get("source", ""))
        url = _clean_text(article.get("url", ""))
        if source and source not in sources:
            sources.append(source)
        if url and url not in urls:
            urls.append(url)

    return {
        "title": _clean_text(primary.get("title", "")),
        "url": _clean_text(primary.get("url", "")),
        "source_url": _clean_text(primary.get("source_url", primary.get("url", ""))),
        "source": " / ".join(sources),
        "source_domain": _clean_text(primary.get("source_domain", "")),
        "image_url": _pick_best_image(cluster),
        "published": _clean_text(primary.get("published", "")),
        "summary": combined_summary,
        "text": combined_text,
        "source_urls": urls,
    }


def cluster_articles() -> Path:
    if not INPUT_PATH.exists():
        raise FileNotFoundError(f"Input file not found: {INPUT_PATH}")

    payload = json.loads(INPUT_PATH.read_text(encoding="utf-8"))
    if not isinstance(payload, list):
        raise ValueError("Input file must contain a JSON list")

    clusters: list[dict[str, Any]] = []

    for raw_article in payload:
        if not isinstance(raw_article, dict):
            continue

        article = dict(raw_article)
        article_tokens = _tokenize_headline(str(article.get("title", "")))

        if not article_tokens:
            clusters.append({"articles": [article], "token_sets": [set()]})
            continue

        best_cluster_index = -1
        best_similarity = 0.0

        for index, cluster in enumerate(clusters):
            token_sets: list[set[str]] = cluster["token_sets"]
            if not token_sets:
                continue
            cluster_similarity = max(_jaccard_similarity(article_tokens, tokens) for tokens in token_sets)
            if cluster_similarity > best_similarity:
                best_similarity = cluster_similarity
                best_cluster_index = index

        if best_cluster_index >= 0 and best_similarity > SIMILARITY_THRESHOLD:
            clusters[best_cluster_index]["articles"].append(article)
            clusters[best_cluster_index]["token_sets"].append(article_tokens)
        else:
            clusters.append({"articles": [article], "token_sets": [article_tokens]})

    merged_articles = [_merge_cluster(cluster["articles"]) for cluster in clusters]

    OUTPUT_PATH.parent.mkdir(parents=True, exist_ok=True)
    OUTPUT_PATH.write_text(json.dumps(merged_articles, ensure_ascii=False, indent=2), encoding="utf-8")
    return OUTPUT_PATH


if __name__ == "__main__":
    output = cluster_articles()
    print(f"Saved clustered articles to: {output}")
