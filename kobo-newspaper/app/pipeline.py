from __future__ import annotations

from pathlib import Path
from typing import Callable

from app.models import CLUSTERED_OUTPUT, read_json, write_json

from stages import build_html
from stages import cluster_articles
from stages import dedupe_articles
from stages import extract_articles
from stages import extract_quotes
from stages import publish_pages
from stages import rss_ingest
from stages import summarize_articles

STAGES: list[tuple[str, Callable[[], Path]]] = [
    ("rss_ingest", rss_ingest.run),
    ("extract_articles", extract_articles.run),
    ("dedupe_articles", dedupe_articles.run),
    ("cluster_articles", cluster_articles.run),
    ("summarize_articles", summarize_articles.run),
    ("extract_quotes", extract_quotes.run),
    ("build_html", build_html.run),
    ("publish_pages", publish_pages.run),
]

FINAL_ARTICLE_LIMIT = 12
MAX_ARTICLES_PER_DOMAIN = 3


def _limit_final_articles(path: Path, max_articles: int = FINAL_ARTICLE_LIMIT) -> None:
    payload = read_json(path, default=[])
    if not isinstance(payload, list):
        return

    ranked_articles = [item for item in payload if isinstance(item, dict)]
    selected_articles: list[dict] = []
    domain_counts: dict[str, int] = {}
    selected_ids: set[int] = set()

    for article in ranked_articles:
        domain = str(article.get("source_domain", "")).strip().lower() or "unknown"
        if domain_counts.get(domain, 0) >= MAX_ARTICLES_PER_DOMAIN:
            continue

        selected_articles.append(article)
        selected_ids.add(id(article))
        domain_counts[domain] = domain_counts.get(domain, 0) + 1

        if len(selected_articles) == max_articles:
            break

    if len(selected_articles) < max_articles:
        for article in ranked_articles:
            if id(article) in selected_ids:
                continue
            selected_articles.append(article)
            if len(selected_articles) == max_articles:
                break

    write_json(path, selected_articles[:max_articles])


def run_pipeline() -> list[tuple[str, Path]]:
    results: list[tuple[str, Path]] = []
    for stage_name, stage_run in STAGES:
        output_path = stage_run()
        if stage_name == "cluster_articles":
            _limit_final_articles(CLUSTERED_OUTPUT, FINAL_ARTICLE_LIMIT)
        results.append((stage_name, output_path))
        print(f"[{stage_name}] wrote {output_path}")
    return results


if __name__ == "__main__":
    run_pipeline()
