from __future__ import annotations

import json
import re
from pathlib import Path
from typing import Any

PROJECT_ROOT = Path(__file__).resolve().parents[1]
INPUT_PATH = PROJECT_ROOT / "pages" / "summarized_articles.json"
OUTPUT_PATH = PROJECT_ROOT / "pages" / "articles_with_quotes.json"


def _clean_text(value: Any) -> str:
    return " ".join(str(value or "").replace("\n", " ").split())


def _split_sentences(text: str) -> list[str]:
    cleaned = _clean_text(text)
    if not cleaned:
        return []
    return [part.strip() for part in re.split(r"(?<=[.!?])\s+", cleaned) if part.strip()]


def _pick_best_quote(article: dict[str, Any]) -> str:
    text_candidates: list[str] = []

    for field in ["text", "summary", "why_it_matters"]:
        field_value = article.get(field, "")
        if isinstance(field_value, list):
            text_candidates.extend(_clean_text(item) for item in field_value if _clean_text(item))
        else:
            text_candidates.append(_clean_text(field_value))

    best_quote = ""
    best_score = -1

    for block in text_candidates:
        for sentence in _split_sentences(block):
            candidate = sentence.strip(' "“”')
            if len(candidate) < 45 or len(candidate) > 220:
                continue

            score = 0
            if any(char.isdigit() for char in candidate):
                score += 2
            if any(word in candidate.lower() for word in ["ökar", "minskar", "beslut", "procent", "miljard", "miljoner"]):
                score += 2
            score += min(len(candidate) // 40, 3)

            if score > best_score:
                best_score = score
                best_quote = candidate

    if not best_quote:
        fallback_summary = article.get("summary", "")
        if isinstance(fallback_summary, list):
            for item in fallback_summary:
                candidate = _clean_text(item)
                if candidate:
                    return candidate
        else:
            candidate = _clean_text(fallback_summary)
            if candidate:
                return candidate

    return best_quote or "Inget citat tillgängligt."


def extract_quotes() -> Path:
    if not INPUT_PATH.exists():
        raise FileNotFoundError(f"Input file not found: {INPUT_PATH}")

    payload = json.loads(INPUT_PATH.read_text(encoding="utf-8"))
    if not isinstance(payload, list):
        raise ValueError("Input file must contain a JSON list")

    output: list[dict[str, Any]] = []
    for raw_article in payload:
        if not isinstance(raw_article, dict):
            continue

        article = dict(raw_article)
        article["quote"] = _pick_best_quote(article)
        output.append(article)

    OUTPUT_PATH.parent.mkdir(parents=True, exist_ok=True)
    OUTPUT_PATH.write_text(json.dumps(output, ensure_ascii=False, indent=2), encoding="utf-8")
    return OUTPUT_PATH


if __name__ == "__main__":
    output = extract_quotes()
    print(f"Saved articles with quotes to: {output}")
