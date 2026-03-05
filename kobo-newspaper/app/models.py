from __future__ import annotations

import json
from dataclasses import asdict, dataclass
from datetime import datetime
from pathlib import Path
from typing import Any

PROJECT_ROOT = Path(__file__).resolve().parents[1]
DATA_DIR = PROJECT_ROOT / "data"
PAGES_DIR = PROJECT_ROOT / "pages"

RSS_OUTPUT = DATA_DIR / "rss_articles.json"
EXTRACTED_OUTPUT = DATA_DIR / "articles_fulltext.json"
DEDUPED_OUTPUT = DATA_DIR / "articles_deduped.json"
CLUSTERED_OUTPUT = DATA_DIR / "articles_clustered.json"
SUMMARIZED_OUTPUT = DATA_DIR / "articles_summarized.json"
QUOTES_OUTPUT = DATA_DIR / "articles_with_quotes.json"
HTML_OUTPUT = DATA_DIR / "rendered_newspaper.json"
PUBLISH_OUTPUT = DATA_DIR / "publish_result.json"


@dataclass
class Article:
    title: str
    url: str
    source: str
    source_domain: str
    published: str = ""
    summary: str = ""
    text: str = ""
    image_url: str = ""
    quote: str = ""
    why_it_matters: str = ""
    eli5: str = ""


@dataclass
class RenderedEdition:
    date: str
    title: str
    html: str
    edition_filename: str


@dataclass
class PublishResult:
    date: str
    latest_index_path: str
    edition_path: str


def clean_text(value: Any) -> str:
    return " ".join(str(value or "").replace("\n", " ").split())


def read_json(path: Path, default: Any = None) -> Any:
    if not path.exists():
        if default is not None:
            return default
        raise FileNotFoundError(f"Input file not found: {path}")
    return json.loads(path.read_text(encoding="utf-8"))


def write_json(path: Path, payload: Any) -> Path:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")
    return path


def article_from_dict(payload: dict[str, Any]) -> Article:
    return Article(
        title=clean_text(payload.get("title", "")),
        url=clean_text(payload.get("url", payload.get("link", ""))),
        source=clean_text(payload.get("source", payload.get("source_name", ""))),
        source_domain=clean_text(payload.get("source_domain", "")),
        published=clean_text(payload.get("published", "")),
        summary=clean_text(payload.get("summary", "")),
        text=clean_text(payload.get("text", "")),
        image_url=clean_text(payload.get("image_url", "")),
        quote=clean_text(payload.get("quote", "")),
        why_it_matters=clean_text(payload.get("why_it_matters", "")),
        eli5=clean_text(payload.get("eli5", "")),
    )


def article_to_dict(article: Article) -> dict[str, Any]:
    return asdict(article)


def today_iso() -> str:
    return datetime.now().strftime("%Y-%m-%d")
