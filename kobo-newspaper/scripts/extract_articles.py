from __future__ import annotations

import json
import re
from difflib import SequenceMatcher
from html import unescape
from pathlib import Path
from typing import Any

import requests

try:
    from readability import Document  # type: ignore
except Exception:
    Document = None

PROJECT_ROOT = Path(__file__).resolve().parents[1]
INPUT_PATH = PROJECT_ROOT / "pages" / "raw_articles.json"
OUTPUT_PATH = PROJECT_ROOT / "pages" / "articles_with_text.json"

REQUEST_TIMEOUT = 12
USER_AGENT = (
    "Mozilla/5.0 (Macintosh; Intel Mac OS X 14_0) "
    "AppleWebKit/537.36 (KHTML, like Gecko) "
    "Chrome/122.0.0.0 Safari/537.36"
)
MAX_TEXT_LENGTH = 30000
SIMILARITY_THRESHOLD = 0.8
PREFERRED_SWEDISH_SOURCES = {
    "svt",
    "sveriges radio",
    "svd",
    "dn",
    "di",
}


def _clean_whitespace(value: str) -> str:
    return " ".join(value.split())


def _normalize_title(title: str) -> str:
    lowered = _clean_whitespace(title).lower()
    no_punctuation = re.sub(r"[^\w\s]", " ", lowered)
    return " ".join(no_punctuation.split())


def _is_preferred_swedish_source(source: str) -> bool:
    source_lower = _clean_whitespace(source).lower()
    return any(preferred in source_lower for preferred in PREFERRED_SWEDISH_SOURCES)


def _titles_are_similar(a: str, b: str) -> bool:
    if not a or not b:
        return False
    return SequenceMatcher(None, a, b).ratio() > SIMILARITY_THRESHOLD


def _choose_better_article(current: dict[str, str], candidate: dict[str, str]) -> dict[str, str]:
    current_preferred = _is_preferred_swedish_source(current.get("source", ""))
    candidate_preferred = _is_preferred_swedish_source(candidate.get("source", ""))

    if current_preferred != candidate_preferred:
        return current if current_preferred else candidate

    current_len = len(_clean_whitespace(current.get("text", "")))
    candidate_len = len(_clean_whitespace(candidate.get("text", "")))
    return current if current_len >= candidate_len else candidate


def _deduplicate_articles(articles: list[dict[str, str]]) -> list[dict[str, str]]:
    deduplicated: list[dict[str, str]] = []
    normalized_titles: list[str] = []

    for article in articles:
        candidate_title = _normalize_title(article.get("title", ""))
        if not candidate_title:
            deduplicated.append(article)
            normalized_titles.append("")
            continue

        duplicate_index = -1
        for index, existing_title in enumerate(normalized_titles):
            if _titles_are_similar(candidate_title, existing_title):
                duplicate_index = index
                break

        if duplicate_index == -1:
            deduplicated.append(article)
            normalized_titles.append(candidate_title)
            continue

        best = _choose_better_article(deduplicated[duplicate_index], article)
        deduplicated[duplicate_index] = best
        normalized_titles[duplicate_index] = _normalize_title(best.get("title", ""))

    return deduplicated


def _strip_tags(html: str) -> str:
    text = re.sub(r"<script[\\s\\S]*?</script>", " ", html, flags=re.IGNORECASE)
    text = re.sub(r"<style[\\s\\S]*?</style>", " ", text, flags=re.IGNORECASE)
    text = re.sub(r"<[^>]+>", " ", text)
    text = unescape(text)
    return _clean_whitespace(text)


def _extract_with_readability(html: str) -> str:
    if Document is None:
        return ""

    try:
        document = Document(html)
        content_html = document.summary()
        return _strip_tags(content_html)
    except Exception:
        return ""


def _extract_with_simple_parsing(html: str) -> str:
    paragraph_matches = re.findall(r"<p[^>]*>([\\s\\S]*?)</p>", html, flags=re.IGNORECASE)
    if paragraph_matches:
        paragraphs = [_strip_tags(chunk) for chunk in paragraph_matches]
        paragraphs = [p for p in paragraphs if p]
        return _clean_whitespace(" ".join(paragraphs))

    return _strip_tags(html)


def _fetch_article_text(url: str) -> str:
    headers = {"User-Agent": USER_AGENT}
    try:
        response = requests.get(url, headers=headers, timeout=REQUEST_TIMEOUT)
        response.raise_for_status()
    except requests.RequestException:
        return ""

    html = response.text or ""
    if not html:
        return ""

    text = _extract_with_readability(html)
    if not text:
        text = _extract_with_simple_parsing(html)

    return text[:MAX_TEXT_LENGTH]


def _iter_input_articles(payload: dict[str, Any]) -> list[dict[str, Any]]:
    if isinstance(payload.get("general"), list) or isinstance(payload.get("tech"), list):
        general = payload.get("general", [])
        tech = payload.get("tech", [])
        return [article for article in (general + tech) if isinstance(article, dict)]

    if isinstance(payload.get("articles"), list):
        return [article for article in payload.get("articles", []) if isinstance(article, dict)]

    return []


def extract_articles() -> Path:
    if not INPUT_PATH.exists():
        raise FileNotFoundError(f"Input file not found: {INPUT_PATH}")

    payload = json.loads(INPUT_PATH.read_text(encoding="utf-8"))
    input_articles = _iter_input_articles(payload)

    seen_urls: set[str] = set()
    result: list[dict[str, str]] = []

    for article in input_articles:
        title = _clean_whitespace(str(article.get("title", "")))
        url = _clean_whitespace(str(article.get("link", article.get("url", ""))))
        source = _clean_whitespace(str(article.get("source_name", article.get("source", ""))))
        published = _clean_whitespace(str(article.get("published", "")))

        if not title or not url or url in seen_urls:
            continue

        seen_urls.add(url)
        text = _fetch_article_text(url)

        result.append(
            {
                "title": title,
                "url": url,
                "source": source,
                "text": text,
                "published": published,
            }
        )

    deduplicated = _deduplicate_articles(result)

    OUTPUT_PATH.parent.mkdir(parents=True, exist_ok=True)
    OUTPUT_PATH.write_text(json.dumps(deduplicated, ensure_ascii=False, indent=2), encoding="utf-8")
    return OUTPUT_PATH


if __name__ == "__main__":
    output_file = extract_articles()
    print(f"Saved extracted articles to: {output_file}")
