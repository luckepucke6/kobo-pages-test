from __future__ import annotations

import re
from html import unescape
from pathlib import Path
from urllib.parse import urlparse

import requests

from app.models import EXTRACTED_OUTPUT, RSS_OUTPUT, read_json, write_json

REQUEST_TIMEOUT = 12
USER_AGENT = (
    "Mozilla/5.0 (Macintosh; Intel Mac OS X 14_0) "
    "AppleWebKit/537.36 (KHTML, like Gecko) "
    "Chrome/122.0.0.0 Safari/537.36"
)
MAX_TEXT_LENGTH = 30000


def _clean(value: str) -> str:
    return " ".join((value or "").split())


def _source_domain(url: str) -> str:
    domain = urlparse(_clean(url)).netloc.lower()
    if domain.startswith("www."):
        domain = domain[4:]
    return domain


def _strip_tags(html: str) -> str:
    text = re.sub(r"<script[\\s\\S]*?</script>", " ", html, flags=re.IGNORECASE)
    text = re.sub(r"<style[\\s\\S]*?</style>", " ", text, flags=re.IGNORECASE)
    text = re.sub(r"<[^>]+>", " ", text)
    text = unescape(text)
    return _clean(text)


def _extract_text_from_html(html: str) -> str:
    paragraph_matches = re.findall(r"<p[^>]*>([\\s\\S]*?)</p>", html, flags=re.IGNORECASE)
    if paragraph_matches:
        paragraphs = [_strip_tags(chunk) for chunk in paragraph_matches]
        paragraphs = [item for item in paragraphs if item]
        return _clean(" ".join(paragraphs))
    return _strip_tags(html)


def _fetch_text(url: str) -> str:
    headers = {"User-Agent": USER_AGENT}
    try:
        response = requests.get(url, headers=headers, timeout=REQUEST_TIMEOUT)
        response.raise_for_status()
    except requests.RequestException:
        return ""

    html = response.text or ""
    if not html:
        return ""
    return _extract_text_from_html(html)[:MAX_TEXT_LENGTH]


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

        output.append(
            {
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
        )

    return write_json(EXTRACTED_OUTPUT, output)


if __name__ == "__main__":
    output = run()
    print(f"Saved extracted articles to: {output}")
