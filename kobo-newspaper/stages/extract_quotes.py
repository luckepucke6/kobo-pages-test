from __future__ import annotations

import re
from pathlib import Path
from typing import Any

from app.models import QUOTES_OUTPUT, SUMMARIZED_OUTPUT, clean_text, read_json, write_json


def _split_sentences(text: str) -> list[str]:
    cleaned = clean_text(text)
    if not cleaned:
        return []
    return [part.strip() for part in re.split(r"(?<=[.!?])\s+", cleaned) if part.strip()]


def _pick_best_quote(article: dict[str, Any]) -> str:
    candidates: list[str] = []

    summary = article.get("summary", "")
    if isinstance(summary, list):
        candidates.extend(clean_text(item) for item in summary if clean_text(item))
    else:
        candidates.append(clean_text(summary))

    candidates.append(clean_text(article.get("text", "")))
    candidates.append(clean_text(article.get("why_it_matters", "")))

    best_quote = ""
    best_score = -1

    for block in candidates:
        for sentence in _split_sentences(block):
            candidate = sentence.strip(' "“”')
            if len(candidate) < 45 or len(candidate) > 220:
                continue

            score = 0
            if any(char.isdigit() for char in candidate):
                score += 2
            if any(token in candidate.lower() for token in ["ökar", "minskar", "beslut", "procent", "miljoner", "miljarder"]):
                score += 2
            score += min(len(candidate) // 40, 3)

            if score > best_score:
                best_score = score
                best_quote = candidate

    return best_quote or "Inget citat tillgängligt."


def run() -> Path:
    payload = read_json(SUMMARIZED_OUTPUT, default=[])
    if not isinstance(payload, list):
        raise ValueError("Expected list input from summarize_articles")

    output: list[dict[str, Any]] = []
    for raw_article in payload:
        if not isinstance(raw_article, dict):
            continue
        article = dict(raw_article)
        article["quote"] = _pick_best_quote(article)
        output.append(article)

    return write_json(QUOTES_OUTPUT, output)


if __name__ == "__main__":
    output = run()
    print(f"Saved quote-enriched articles to: {output}")
