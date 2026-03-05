from __future__ import annotations

from pathlib import Path
from typing import Callable

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


def run_pipeline() -> list[tuple[str, Path]]:
    results: list[tuple[str, Path]] = []
    for stage_name, stage_run in STAGES:
        output_path = stage_run()
        results.append((stage_name, output_path))
        print(f"[{stage_name}] wrote {output_path}")
    return results


if __name__ == "__main__":
    run_pipeline()
