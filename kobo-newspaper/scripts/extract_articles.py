from __future__ import annotations

import json
import re
from html import unescape
from pathlib import Path
from typing import Any
from urllib.parse import urlparse

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


def _clean_whitespace(value: str) -> str:
    return " ".join(value.split())


def _extract_source_domain(url: str) -> str:
    domain = urlparse(_clean_whitespace(url)).netloc.lower()
    if domain.startswith("www."):
        domain = domain[4:]
    return domain


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
    extracted_articles: list[dict[str, str]] = []

    for article in input_articles:
        title = _clean_whitespace(str(article.get("title", "")))
        url = _clean_whitespace(str(article.get("link", article.get("url", ""))))
        source = _clean_whitespace(str(article.get("source_name", article.get("source", ""))))
        published = _clean_whitespace(str(article.get("published", "")))
        summary = _clean_whitespace(str(article.get("summary", "")))
        image_url = _clean_whitespace(str(article.get("image_url", "")))

        if not title or not url or url in seen_urls:
            continue

        seen_urls.add(url)
        text = _fetch_article_text(url)

        extracted_articles.append(
            {
                "title": title,
                "url": url,
                "source_url": url,
                "source_domain": _extract_source_domain(url),
                "source": source,
                "text": text,
                "summary": summary,
                "image_url": image_url,
                "published": published,
            }
        )

    OUTPUT_PATH.parent.mkdir(parents=True, exist_ok=True)
    OUTPUT_PATH.write_text(json.dumps(extracted_articles, ensure_ascii=False, indent=2), encoding="utf-8")
    return OUTPUT_PATH


if __name__ == "__main__":
    output_file = extract_articles()
    print(f"Saved extracted articles to: {output_file}")
