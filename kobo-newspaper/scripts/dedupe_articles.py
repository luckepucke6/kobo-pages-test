from __future__ import annotations

import json
import re
from difflib import SequenceMatcher
from pathlib import Path
from typing import Any

PROJECT_ROOT = Path(__file__).resolve().parents[1]
INPUT_PATH = PROJECT_ROOT / "pages" / "articles_with_text.json"
OUTPUT_PATH = PROJECT_ROOT / "pages" / "deduped_articles.json"

TITLE_SIMILARITY_THRESHOLD = 0.8
PREFERRED_SWEDISH_DOMAINS = {
    "svt.se",
    "sr.se",
    "svd.se",
    "dn.se",
    "di.se",
}


def _clean_text(value: Any) -> str:
    return " ".join(str(value or "").replace("\n", " ").split())


def _normalize_title(title: str) -> str:
    cleaned = _clean_text(title).lower()
    cleaned = re.sub(r"[^\w\s]", " ", cleaned)
    return " ".join(cleaned.split())


def _split_sentences(text: str) -> list[str]:
    cleaned = _clean_text(text)
    if not cleaned:
        return []
    return [part.strip() for part in re.split(r"(?<=[.!?])\s+", cleaned) if part.strip()]


def _remove_duplicate_sentences(text: str) -> str:
    sentences = _split_sentences(text)
    seen: set[str] = set()
    unique: list[str] = []

    for sentence in sentences:
        normalized = sentence.lower().strip()
        if normalized in seen:
            continue
        seen.add(normalized)
        unique.append(sentence)

    return " ".join(unique)


def _remove_duplicate_paragraphs(text: str) -> str:
    paragraphs = [part.strip() for part in re.split(r"\n\s*\n", str(text or "")) if part.strip()]
    if not paragraphs:
        return _clean_text(text)

    seen: set[str] = set()
    unique: list[str] = []
    for paragraph in paragraphs:
        normalized = _clean_text(paragraph).lower()
        if normalized in seen:
            continue
        seen.add(normalized)
        unique.append(_clean_text(paragraph))

    return "\n\n".join(unique)


def _is_preferred_swedish_source(article: dict[str, Any]) -> bool:
    domain = _clean_text(article.get("source_domain", "")).lower()
    if domain and any(domain == preferred or domain.endswith(f".{preferred}") for preferred in PREFERRED_SWEDISH_DOMAINS):
        return True

    source_text = _clean_text(article.get("source", "")).lower()
    markers = {"svt", "sveriges radio", "svd", "dn", "di"}
    return any(marker in source_text for marker in markers)


def _title_similarity(title_a: str, title_b: str) -> float:
    if not title_a or not title_b:
        return 0.0
    return SequenceMatcher(None, title_a, title_b).ratio()


def _choose_best_article(current: dict[str, Any], candidate: dict[str, Any]) -> dict[str, Any]:
    current_preferred = _is_preferred_swedish_source(current)
    candidate_preferred = _is_preferred_swedish_source(candidate)

    if current_preferred != candidate_preferred:
        return current if current_preferred else candidate

    current_len = len(_clean_text(current.get("text", "")))
    candidate_len = len(_clean_text(candidate.get("text", "")))
    return current if current_len >= candidate_len else candidate


def deduplicate_articles() -> Path:
    if not INPUT_PATH.exists():
        raise FileNotFoundError(f"Input file not found: {INPUT_PATH}")

    payload = json.loads(INPUT_PATH.read_text(encoding="utf-8"))
    if not isinstance(payload, list):
        raise ValueError("Input file must contain a JSON list")

    selected: list[dict[str, Any]] = []
    normalized_titles: list[str] = []

    for raw_article in payload:
        if not isinstance(raw_article, dict):
            continue

        article = dict(raw_article)
        article["title"] = _clean_text(article.get("title", ""))
        article["url"] = _clean_text(article.get("url", article.get("source_url", "")))
        article["source_url"] = _clean_text(article.get("source_url", article.get("url", "")))
        article["text"] = _remove_duplicate_sentences(_remove_duplicate_paragraphs(article.get("text", "")))
        article["summary"] = _remove_duplicate_sentences(_clean_text(article.get("summary", "")))

        if not article["title"] or not article["url"]:
            continue

        candidate_title = _normalize_title(article["title"])
        duplicate_index = -1

        for index, existing_title in enumerate(normalized_titles):
            similarity = _title_similarity(candidate_title, existing_title)
            if similarity > TITLE_SIMILARITY_THRESHOLD:
                duplicate_index = index
                break

        if duplicate_index == -1:
            selected.append(article)
            normalized_titles.append(candidate_title)
            continue

        best = _choose_best_article(selected[duplicate_index], article)
        selected[duplicate_index] = best
        normalized_titles[duplicate_index] = _normalize_title(best.get("title", ""))

    OUTPUT_PATH.parent.mkdir(parents=True, exist_ok=True)
    OUTPUT_PATH.write_text(json.dumps(selected, ensure_ascii=False, indent=2), encoding="utf-8")
    return OUTPUT_PATH


if __name__ == "__main__":
    output = deduplicate_articles()
    print(f"Saved deduplicated articles to: {output}")
