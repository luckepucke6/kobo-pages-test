from __future__ import annotations

import re
from pathlib import Path
from typing import Any

from app.models import DEDUPED_OUTPUT, EXTRACTED_OUTPUT, read_json, write_json

PREFERRED_SWEDISH_DOMAINS = {"svt.se", "sr.se", "svd.se", "dn.se", "di.se"}


def _clean(value: Any) -> str:
    return " ".join(str(value or "").replace("\n", " ").split())


def _normalize_title(title: str) -> str:
    text = _clean(title).lower()
    text = re.sub(r"[^\w\s]", " ", text)
    return " ".join(text.split())


def _split_sentences(text: str) -> list[str]:
    clean = _clean(text)
    if not clean:
        return []
    return [part.strip() for part in re.split(r"(?<=[.!?])\s+", clean) if part.strip()]


def _remove_duplicate_sentences(text: str) -> str:
    seen: set[str] = set()
    unique: list[str] = []
    for sentence in _split_sentences(text):
        key = sentence.lower().strip()
        if key in seen:
            continue
        seen.add(key)
        unique.append(sentence)
    return " ".join(unique)


def _remove_duplicate_paragraphs(text: str) -> str:
    parts = [part.strip() for part in re.split(r"\n\s*\n", str(text or "")) if part.strip()]
    if not parts:
        return _clean(text)
    seen: set[str] = set()
    unique: list[str] = []
    for part in parts:
        normalized = _clean(part).lower()
        if normalized in seen:
            continue
        seen.add(normalized)
        unique.append(_clean(part))
    return "\n\n".join(unique)


def _clean_article_text(text: str) -> str:
    without_duplicate_paragraphs = _remove_duplicate_paragraphs(text)
    return _remove_duplicate_sentences(without_duplicate_paragraphs)


def _is_preferred(article: dict[str, Any]) -> bool:
    domain = _clean(article.get("source_domain", "")).lower()
    return any(domain == item or domain.endswith(f".{item}") for item in PREFERRED_SWEDISH_DOMAINS)


def _choose_best(current: dict[str, Any], candidate: dict[str, Any]) -> dict[str, Any]:
    if _is_preferred(current) != _is_preferred(candidate):
        return current if _is_preferred(current) else candidate

    current_len = len(_clean(current.get("text", "")))
    candidate_len = len(_clean(candidate.get("text", "")))
    return current if current_len >= candidate_len else candidate


def run() -> Path:
    payload = read_json(EXTRACTED_OUTPUT, default=[])
    if not isinstance(payload, list):
        raise ValueError("Expected list input from extract_articles")

    deduped_by_title: dict[str, dict[str, Any]] = {}

    for raw in payload:
        if not isinstance(raw, dict):
            continue

        article = dict(raw)
        article["title"] = _clean(article.get("title", ""))
        article["text"] = _clean_article_text(str(article.get("text", "")))
        article["summary"] = _clean_article_text(str(article.get("summary", "")))

        normalized = _normalize_title(article.get("title", ""))
        if not normalized:
            continue

        existing = deduped_by_title.get(normalized)
        if existing is None:
            deduped_by_title[normalized] = article
            continue

        deduped_by_title[normalized] = _choose_best(existing, article)

    deduped = list(deduped_by_title.values())

    return write_json(DEDUPED_OUTPUT, deduped)


if __name__ == "__main__":
    output = run()
    print(f"Saved deduplicated articles to: {output}")
