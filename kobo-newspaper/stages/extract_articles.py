from __future__ import annotations

import re
from pathlib import Path
from urllib.parse import urlparse

import requests

try:
    import trafilatura
except Exception:
    trafilatura = None  # type: ignore

try:
    from bs4 import BeautifulSoup
except Exception:
    BeautifulSoup = None  # type: ignore

from app.models import EXTRACTED_OUTPUT, RSS_OUTPUT, read_json, write_json

REQUEST_TIMEOUT = 12
USER_AGENT = (
    "Mozilla/5.0 (Macintosh; Intel Mac OS X 14_0) "
    "AppleWebKit/537.36 (KHTML, like Gecko) "
    "Chrome/122.0.0.0 Safari/537.36"
)
MAX_TEXT_LENGTH = 30000
MIN_ARTICLE_WORDS = 150
MIN_CLEAN_ARTICLE_WORDS = 250
MIN_PARAGRAPH_LENGTH = 40

BOILERPLATE_PATTERNS = [
    r"\bsubscribe\b",
    r"\blogin to continue\b",
    r"\bpaywall\b",
    r"\badvertisement\b",
    r"\bcookie consent\b",
]

NAVIGATION_PATTERNS = [
    r"\bshare\b",
    r"\bfollow\b",
    r"\bread more\b",
]


def _clean(value: str) -> str:
    return " ".join((value or "").split())


def _source_domain(url: str) -> str:
    domain = urlparse(_clean(url)).netloc.lower()
    if domain.startswith("www."):
        domain = domain[4:]
    return domain


def _extract_with_bs4(html: str) -> str:
    if not html:
        return ""

    if BeautifulSoup is None:
        text = re.sub(r"<script[\\s\\S]*?</script>", " ", html, flags=re.IGNORECASE)
        text = re.sub(r"<style[\\s\\S]*?</style>", " ", text, flags=re.IGNORECASE)
        text = re.sub(r"<[^>]+>", " ", text)
        text = _clean(text)[:MAX_TEXT_LENGTH]
        return text

    soup = BeautifulSoup(html, "html.parser")
    for tag in soup(["script", "style", "noscript"]):
        tag.decompose()

    paragraphs = [
        _clean(paragraph.get_text(" ", strip=True))
        for paragraph in soup.find_all("p")
    ]
    paragraphs = [paragraph for paragraph in paragraphs if paragraph]

    if paragraphs:
        return "\n\n".join(paragraphs)[:MAX_TEXT_LENGTH]

    body_text = _clean(soup.get_text(" ", strip=True))
    return body_text[:MAX_TEXT_LENGTH]


def _extract_with_trafilatura(url: str) -> tuple[str, str]:
    if trafilatura is None:
        return "", ""

    downloaded = trafilatura.fetch_url(url)
    if not downloaded:
        return "", ""

    extracted_text = trafilatura.extract(downloaded) or ""
    return _clean(extracted_text)[:MAX_TEXT_LENGTH], downloaded


def _fetch_text(url: str) -> str:
    extracted_text, downloaded = _extract_with_trafilatura(url)
    if extracted_text:
        return extracted_text

    if downloaded:
        fallback = _extract_with_bs4(downloaded)
        if fallback:
            return fallback

    headers = {"User-Agent": USER_AGENT}
    try:
        response = requests.get(url, headers=headers, timeout=REQUEST_TIMEOUT)
        response.raise_for_status()
    except requests.RequestException:
        return ""

    html = response.text or ""
    return _extract_with_bs4(html)


def _contains_pattern(text: str, patterns: list[str]) -> bool:
    lowered = text.lower()
    return any(re.search(pattern, lowered) for pattern in patterns)


def _split_paragraphs(text: str) -> list[str]:
    normalized = (text or "").replace("\r\n", "\n").replace("\r", "\n")
    paragraphs = [part.strip() for part in re.split(r"\n\s*\n", normalized) if part.strip()]
    if paragraphs:
        return paragraphs
    return [part.strip() for part in re.split(r"(?<=[.!?])\s+", normalized) if part.strip()]


def clean_article(article: dict[str, str]) -> dict[str, str] | None:
    raw_text = str(article.get("text", ""))
    paragraphs = _split_paragraphs(raw_text)

    seen: set[str] = set()
    cleaned_paragraphs: list[str] = []

    for paragraph in paragraphs:
        cleaned = _clean(paragraph)
        if not cleaned:
            continue
        if len(cleaned) < MIN_PARAGRAPH_LENGTH:
            continue
        if _contains_pattern(cleaned, BOILERPLATE_PATTERNS):
            continue
        if _contains_pattern(cleaned, NAVIGATION_PATTERNS):
            continue

        dedupe_key = cleaned.lower()
        if dedupe_key in seen:
            continue
        seen.add(dedupe_key)
        cleaned_paragraphs.append(cleaned)

    cleaned_text = "\n\n".join(cleaned_paragraphs)
    cleaned_text = cleaned_text[:MAX_TEXT_LENGTH]
    word_count = len(_clean(cleaned_text).split())
    if word_count < MIN_CLEAN_ARTICLE_WORDS:
        return None

    article["text"] = cleaned_text
    return article


def _is_valid_article_text(text: str, min_words: int = MIN_ARTICLE_WORDS) -> bool:
    words = _clean(text).split()
    return len(words) >= min_words


def run() -> Path:
    payload = read_json(RSS_OUTPUT, default=[])
    if not isinstance(payload, list):
        raise ValueError("Expected list input from rss_ingest")

    seen_urls: set[str] = set()
    output: list[dict[str, str]] = []

    for item in payload:
        if not isinstance(item, dict):
            continue

        title = _clean(str(item.get("title", "")))
        url = _clean(str(item.get("url", "")))
        source = _clean(str(item.get("source", "")))
        summary = _clean(str(item.get("summary", "")))
        published = _clean(str(item.get("published", "")))
        image_url = _clean(str(item.get("image_url", "")))

        if not title or not url or url in seen_urls:
            continue

        seen_urls.add(url)
        text = _fetch_text(url)

        if not _is_valid_article_text(text):
            continue

        article = {
            "title": title,
            "url": url,
            "source_url": url,
            "source": source,
            "source_domain": _source_domain(url),
            "summary": summary,
            "published": published,
            "image_url": image_url,
            "text": text,
        }

        cleaned_article = clean_article(article)
        if cleaned_article is None:
            continue

        output.append(cleaned_article)

    return write_json(EXTRACTED_OUTPUT, output)


if __name__ == "__main__":
    output = run()
    print(f"Saved extracted articles to: {output}")
