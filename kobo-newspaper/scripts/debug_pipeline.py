from __future__ import annotations

from collections import Counter
from statistics import mean
from typing import Any
import re

from app.models import (
    CLUSTERED_OUTPUT,
    DEDUPED_OUTPUT,
    EXTRACTED_OUTPUT,
    HTML_OUTPUT,
    QUOTES_OUTPUT,
    RSS_OUTPUT,
    SUMMARIZED_OUTPUT,
    clean_text,
    read_json,
    write_json,
)
from stages import build_html, cluster_articles, dedupe_articles, extract_articles, rss_ingest, summarize_articles

SWEDISH_DOMAINS = {"svt.se", "sverigesradio.se", "sr.se", "svd.se", "dn.se", "di.se"}
AI_TECH_KEYWORDS = {
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
    "technology",
    "tech",
}
FINAL_ARTICLE_LIMIT = 12
PAYWALL_KEYWORDS = ["subscribe", "paywall", "log in", "continue reading"]


def _print_header(title: str) -> None:
    print(f"\n=== {title} ===")


def _summary_sentence_count(summary: Any) -> int:
    if isinstance(summary, list):
        return len([clean_text(item) for item in summary if clean_text(item)])
    cleaned = clean_text(summary)
    return 1 if cleaned else 0


def _split_sentences(text: str) -> list[str]:
    cleaned = clean_text(text)
    if not cleaned:
        return []
    return [part.strip() for part in re.split(r"(?<=[.!?])\s+", cleaned) if part.strip()]


def _count_duplicate_sentences(sentences: list[str]) -> int:
    seen: set[str] = set()
    duplicates = 0
    for sentence in sentences:
        normalized = clean_text(sentence).lower()
        if not normalized:
            continue
        if normalized in seen:
            duplicates += 1
            continue
        seen.add(normalized)
    return duplicates


def _to_float(value: Any) -> float:
    try:
        return float(value)
    except (TypeError, ValueError):
        return 0.0


def _to_int(value: Any, default: int = 0) -> int:
    try:
        return int(value)
    except (TypeError, ValueError):
        return default


def _is_swedish_domain(domain: str) -> bool:
    normalized = clean_text(domain).lower()
    return any(normalized == candidate or normalized.endswith(f".{candidate}") for candidate in SWEDISH_DOMAINS)


def _prepare_build_input_from_summaries(summarized_articles: list[dict[str, Any]]) -> None:
    payload: list[dict[str, Any]] = []
    for article in summarized_articles:
        item = dict(article)
        quote = clean_text(item.get("quote", ""))
        if not quote:
            summary = item.get("summary", [])
            if isinstance(summary, list):
                quote = clean_text(summary[0]) if summary else "Inget citat tillgängligt."
            else:
                quote = clean_text(summary) or "Inget citat tillgängligt."
        item["quote"] = quote
        payload.append(item)

    write_json(QUOTES_OUTPUT, payload)


def main() -> None:
    _print_header("RUN PIPELINE")
    rss_ingest.run()
    rss_items = read_json(RSS_OUTPUT, default=[])

    extract_articles.run()
    extracted_items = read_json(EXTRACTED_OUTPUT, default=[])

    dedupe_articles.run()
    deduped_items = read_json(DEDUPED_OUTPUT, default=[])

    cluster_articles.run()
    clustered_items = read_json(CLUSTERED_OUTPUT, default=[])

    if isinstance(clustered_items, list):
        write_json(CLUSTERED_OUTPUT, clustered_items[:FINAL_ARTICLE_LIMIT])

    summarize_articles.run()
    summarized_items = read_json(SUMMARIZED_OUTPUT, default=[])

    _prepare_build_input_from_summaries(summarized_items)
    build_html.run()
    rendered_payload = read_json(HTML_OUTPUT, default={})

    _print_header("RSS STAGE")
    total_rss = len(rss_items) if isinstance(rss_items, list) else 0
    unique_domains = sorted(
        {
            clean_text(item.get("source_domain", "")).lower()
            for item in rss_items
            if isinstance(item, dict) and clean_text(item.get("source_domain", ""))
        }
    )
    swedish_source_count = sum(
        1
        for item in rss_items
        if isinstance(item, dict) and _is_swedish_domain(str(item.get("source_domain", "")))
    )
    print(f"total rss items: {total_rss}")
    print(f"unique domains ({len(unique_domains)}): {', '.join(unique_domains) if unique_domains else '-'}")
    print(f"Swedish source count: {swedish_source_count}")

    _print_header("EXTRACT STAGE")
    extracted_count = len(extracted_items) if isinstance(extracted_items, list) else 0
    article_lengths = [
        len(clean_text(item.get("text", "")).split())
        for item in extracted_items
        if isinstance(item, dict)
    ]
    avg_len = mean(article_lengths) if article_lengths else 0.0
    empty_count = sum(
        1
        for item in extracted_items
        if isinstance(item, dict) and not clean_text(item.get("text", ""))
    )
    print(f"articles extracted: {extracted_count}")
    print(f"average article length (words): {avg_len:.1f}")
    print(f"empty article count: {empty_count}")

    _print_header("DEDUPE STAGE")
    before_dedupe = extracted_count
    after_dedupe = len(deduped_items) if isinstance(deduped_items, list) else 0
    removed_duplicates = max(before_dedupe - after_dedupe, 0)
    print(f"articles before dedupe: {before_dedupe}")
    print(f"articles after dedupe: {after_dedupe}")
    print(f"removed duplicates: {removed_duplicates}")

    _print_header("CLUSTER STAGE")
    cluster_count = len(clustered_items) if isinstance(clustered_items, list) else 0
    cluster_sizes = [
        max(_to_int(item.get("cluster_size", 1), 1), 1)
        for item in clustered_items
        if isinstance(item, dict)
    ]
    avg_cluster_size = mean(cluster_sizes) if cluster_sizes else 0.0
    multi_source_clusters = 0
    for item in clustered_items:
        if not isinstance(item, dict):
            continue
        source_domains = item.get("sources_covering_event", [])
        if isinstance(source_domains, list) and len(source_domains) > 1:
            multi_source_clusters += 1
        elif _to_int(item.get("sources_count", 0), 0) > 1:
            multi_source_clusters += 1

    print(f"cluster count: {cluster_count}")
    print(f"average cluster size: {avg_cluster_size:.2f}")
    print(f"clusters with >1 source: {multi_source_clusters}")

    _print_header("SUMMARIZE STAGE")
    summary_lengths = [
        _summary_sentence_count(item.get("summary", []))
        for item in summarized_items
        if isinstance(item, dict)
    ]
    distribution = Counter(summary_lengths)
    print(f"summary sentence length distribution: {dict(sorted(distribution.items()))}")
    print(f"min sentences: {min(summary_lengths) if summary_lengths else 0}")
    print(f"max sentences: {max(summary_lengths) if summary_lengths else 0}")

    _print_header("FINAL SELECTION")
    final_count = _to_int(rendered_payload.get("article_count", len(summarized_items)), len(summarized_items))
    final_swedish_count = sum(
        1
        for item in summarized_items
        if isinstance(item, dict) and _is_swedish_domain(str(item.get("source_domain", "")))
    )

    tech_count = 0
    for item in summarized_items:
        if not isinstance(item, dict):
            continue
        summary_text = item.get("summary", [])
        if isinstance(summary_text, list):
            summary_blob = " ".join(clean_text(part) for part in summary_text)
        else:
            summary_blob = clean_text(summary_text)
        text = " ".join(
            [
                clean_text(item.get("title", "")),
                summary_blob,
                clean_text(item.get("why_it_matters", "")),
            ]
        ).lower()
        if any(keyword in text for keyword in AI_TECH_KEYWORDS):
            tech_count += 1

    print(f"total articles in final newspaper: {final_count}")
    print(f"Swedish sources count: {final_swedish_count}")
    print(f"tech/AI article count: {tech_count}")

    _print_header("QUALITY CHECKS")
    warnings: list[str] = []

    if final_count < 12:
        warnings.append("final article count < 12")

    normalized_titles = [
        clean_text(item.get("title", "")).lower()
        for item in summarized_items
        if isinstance(item, dict) and clean_text(item.get("title", ""))
    ]
    if len(normalized_titles) != len(set(normalized_titles)):
        warnings.append("duplicate titles exist")

    if any(length < 5 for length in summary_lengths):
        warnings.append("summary sentences < 5 detected")
    if any(length > 8 for length in summary_lengths):
        warnings.append("summary sentences > 8 detected")
    if final_swedish_count == 0:
        warnings.append("no Swedish sources")
    if tech_count == 0:
        warnings.append("no AI/tech articles")

    if warnings:
        for warning in warnings:
            print(f"WARNING: {warning}")
    else:
        print("No quality warnings.")

    _print_header("TOP 5 RANKED ARTICLES")
    ranked = sorted(
        [item for item in summarized_items if isinstance(item, dict)],
        key=lambda item: _to_float(item.get("importance_score", 0.0)),
        reverse=True,
    )

    for article in ranked[:5]:
        print(f"title: {clean_text(article.get('title', ''))}")
        print(f"importance_score: {_to_float(article.get('importance_score', 0.0)):.4f}")
        print(f"cluster_size: {_to_int(article.get('cluster_size', 1), 1)}")
        print(f"source_domain: {clean_text(article.get('source_domain', ''))}")
        print("-")

    _print_header("DUPLICATE TITLE DETECTION")
    deduped_payload = read_json(DEDUPED_OUTPUT, default=[])
    deduped_titles = [
        clean_text(item.get("title", "")).lower()
        for item in deduped_payload
        if isinstance(item, dict) and clean_text(item.get("title", ""))
    ]
    duplicate_titles_count = sum(count - 1 for count in Counter(deduped_titles).values() if count > 1)
    print(f"duplicate_titles_count: {duplicate_titles_count}")

    _print_header("DUPLICATE SUMMARY SENTENCE DETECTION")
    quotes_payload = read_json(QUOTES_OUTPUT, default=[])
    duplicate_summary_sentences = 0
    for item in quotes_payload:
        if not isinstance(item, dict):
            continue
        summary_value = item.get("summary", [])
        if isinstance(summary_value, list):
            summary_text = " ".join(clean_text(part) for part in summary_value if clean_text(part))
        else:
            summary_text = clean_text(summary_value)
        duplicate_summary_sentences += _count_duplicate_sentences(_split_sentences(summary_text))
    print(f"duplicate_summary_sentences: {duplicate_summary_sentences}")

    _print_header("PAYWALL DETECTION")
    paywall_detected = False
    for item in extracted_items:
        if not isinstance(item, dict):
            continue
        article_text = clean_text(item.get("text", "")).lower()
        if any(keyword in article_text for keyword in PAYWALL_KEYWORDS):
            paywall_detected = True
            break

    if paywall_detected:
        print("PAYWALL_CONTENT_DETECTED")
    else:
        print("No paywall content detected.")

    _print_header("SOURCE DISTRIBUTION")
    source_counter: Counter[str] = Counter(
        clean_text(item.get("source_domain", "")).lower()
        for item in summarized_items
        if isinstance(item, dict) and clean_text(item.get("source_domain", ""))
    )
    for domain, count in source_counter.most_common():
        print(f"{domain}: {count}")

    _print_header("SUMMARY SENTENCE STATISTICS")
    summary_min = min(summary_lengths) if summary_lengths else 0
    summary_max = max(summary_lengths) if summary_lengths else 0
    summary_avg = mean(summary_lengths) if summary_lengths else 0.0
    print(f"minimum sentence count: {summary_min}")
    print(f"maximum sentence count: {summary_max}")
    print(f"average sentence count: {summary_avg:.2f}")

    _print_header("PIPELINE HEALTH REPORT")
    print(f"Articles extracted: {extracted_count}")
    print(f"Articles after dedupe: {after_dedupe}")
    print(f"Clusters: {cluster_count}")
    print(f"Clusters with multiple sources: {multi_source_clusters}")
    print("")
    print(f"Duplicate titles: {duplicate_titles_count}")
    print(f"Duplicate summary sentences: {duplicate_summary_sentences}")


if __name__ == "__main__":
    main()
