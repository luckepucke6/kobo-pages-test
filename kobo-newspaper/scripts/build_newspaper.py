from __future__ import annotations

import json
import re
from datetime import datetime
from pathlib import Path
from typing import Any

from jinja2 import Template

PROJECT_ROOT = Path(__file__).resolve().parents[1]
INPUT_PATH = PROJECT_ROOT / "pages" / "articles_with_quotes.json"
OUTPUT_HTML = PROJECT_ROOT / "pages" / "index.html"

SECTION_ORDER = [
    "VÄRLDEN",
    "EKONOMI",
    "AI FÖR ML-INGENJÖRER",
    "SVERIGE",
]

HTML_TEMPLATE = """<!doctype html>
<html lang="sv">
<head>
  <meta charset="utf-8" />
  <meta name="viewport" content="width=device-width, initial-scale=1" />
  <title>Morgontidningen</title>
  <style>
    body { max-width: 700px; margin: auto; line-height: 1.6; font-family: Georgia, serif; padding: 16px; }
    img { width: 90%; height: auto; margin: 10px auto; display: block; }
    h1, h2, h3 { margin: 1em 0 0.4em; line-height: 1.3; }
    p { margin: 0 0 0.8em; }
    ul { margin: 0; padding-left: 1.2em; }
    li { margin: 0 0 0.45em; }
    article { margin: 0 0 1.6em; }
  </style>
</head>
<body>
  <h1>Morgontidningen</h1>
  <p>Datum: {{ date_string }}</p>

  <h2>Det viktigaste idag</h2>
  {% if top_bullets %}
  <ul>
    {% for bullet in top_bullets %}
    <li>{{ bullet }}</li>
    {% endfor %}
  </ul>
  {% else %}
  <p>Ingen sammanfattning tillgänglig ännu.</p>
  {% endif %}

  <h2>Dagens siffror</h2>
  {% if daily_numbers %}
  <ul>
    {% for number in daily_numbers %}
    <li>{{ number }}</li>
    {% endfor %}
  </ul>
  {% else %}
  <p>Inga tydliga siffror tillgängliga ännu.</p>
  {% endif %}

  {% for section in sections %}
  <h2>{{ section.name }}</h2>
  {% for story in section.stories %}
  <article>
    <h3>{{ story.title }}</h3>
    <p><strong>Summary:</strong> {{ story.summary }}</p>
    <p><strong>Quote:</strong> {{ story.quote }}</p>
    <p><strong>Why it matters:</strong> {{ story.why_it_matters }}</p>
    <p><strong>ELI5:</strong> {{ story.eli5 }}</p>
    <p><strong>Reflection question:</strong> {{ story.reflection_question }}</p>
    <p><a href="{{ story.source_url }}">Source link</a></p>
  </article>
  {% endfor %}
  {% endfor %}
</body>
</html>
"""


def _clean_text(value: Any) -> str:
    return " ".join(str(value or "").replace("\n", " ").split())


def _summary_to_text(summary: Any) -> str:
    if isinstance(summary, list):
        parts = [_clean_text(item) for item in summary if _clean_text(item)]
        return " ".join(parts)
    return _clean_text(summary)


def _quote_to_text(quote: Any, fallback_text: str) -> str:
    if isinstance(quote, list):
        for item in quote:
            q = _clean_text(item)
            if q:
                return q
    q = _clean_text(quote)
    if q:
        return q

    sentence_parts = re.split(r"(?<=[.!?])\s+", fallback_text)
    for part in sentence_parts:
        cleaned = _clean_text(part)
        if 30 <= len(cleaned) <= 240:
            return cleaned
    return "Inget citat tillgängligt."


def _reflection_question(title: str) -> str:
    t = _clean_text(title)
    if not t:
        return "Vilka konsekvenser får detta framåt?"
    return f"Hur kan {t.lower()} påverka utvecklingen framåt?"


def _assign_section(article: dict[str, Any]) -> str:
    text = " ".join(
        [
            _clean_text(article.get("title", "")),
            _summary_to_text(article.get("summary", "")),
            _clean_text(article.get("why_it_matters", "")),
            _clean_text(article.get("source", "")),
        ]
    ).lower()

    if any(term in text for term in ["sverige", "svensk", "stockholm", "riksdag", "regering"]):
        return "SVERIGE"
    if any(term in text for term in ["ekonomi", "inflation", "ränta", "börs", "gdp", "budget", "bank"]):
        return "EKONOMI"
    if any(
        term in text
        for term in [
            "ai",
            "machine learning",
            "ml",
            "llm",
            "model",
            "inference",
            "framework",
            "open source",
            "pytorch",
            "tensorflow",
            "data pipeline",
            "feature store",
        ]
    ):
        return "AI FÖR ML-INGENJÖRER"
    return "VÄRLDEN"


def _build_top_bullets(stories: list[dict[str, Any]]) -> list[str]:
    priority_terms = [
        "krig",
        "konflikt",
        "global",
        "inflation",
        "ränta",
        "gdp",
        "ai",
        "inference",
        "säkerhet",
        "ekonomi",
    ]

    scored: list[tuple[int, dict[str, Any]]] = []
    for story in stories:
        text = " ".join(
            [
                _clean_text(story.get("title", "")),
                _clean_text(story.get("why_it_matters", "")),
            ]
        ).lower()
        score = sum(1 for term in priority_terms if term in text)
        scored.append((score, story))

    scored.sort(key=lambda item: item[0], reverse=True)
    top = [item[1] for item in scored[:5]]

    bullets: list[str] = []
    for story in top:
        title = _clean_text(story.get("title", ""))
        why = _clean_text(story.get("why_it_matters", ""))
        short = " ".join(why.split()[:8])
        if short and not short.endswith((".", "!", "?")):
            short += "."
        bullets.append(f"{title} – {short or 'Viktig utveckling idag.'}")

    return bullets[:5]


def _build_daily_numbers(stories: list[dict[str, Any]]) -> list[str]:
    number_pattern = re.compile(r"\b\d+[\d\s.,]*\s*(?:%|procent|kr|SEK|USD|EUR|dollar|punkter|miljoner|miljarder)?\b", re.IGNORECASE)
    collected: list[str] = []

    for story in stories:
        text = " ".join(
            [
                _clean_text(story.get("title", "")),
                _summary_to_text(story.get("summary", "")),
                _clean_text(story.get("why_it_matters", "")),
            ]
        )
        matches = [m.group(0).strip() for m in number_pattern.finditer(text)]
        for value in matches:
            if any(ch.isdigit() for ch in value):
                item = f"Nyckeltal: {value}"
                if item not in collected:
                    collected.append(item)
            if len(collected) >= 6:
                return collected

    return collected[:6]


def _normalize_article(article: dict[str, Any]) -> dict[str, Any]:
    title = _clean_text(article.get("title", "Utan rubrik")) or "Utan rubrik"
    summary = _summary_to_text(article.get("summary", article.get("summary_paragraphs", "")))
    why_it_matters = _clean_text(article.get("why_it_matters", article.get("why_important", "")))
    eli5 = _clean_text(article.get("eli5", "")) or "Ingen ELI5 tillgänglig."
    source_url = _clean_text(article.get("url", article.get("source_url", "#"))) or "#"
    source = _clean_text(article.get("source", ""))

    quote = _quote_to_text(article.get("quote", article.get("quotes", "")), summary)

    if not summary:
        summary = "Ingen sammanfattning tillgänglig."
    if not why_it_matters:
        why_it_matters = "Den här utvecklingen kan påverka nyhetsläget framåt."

    return {
        "title": title,
        "summary": summary,
        "quote": quote,
        "why_it_matters": why_it_matters,
        "eli5": eli5,
        "reflection_question": _reflection_question(title),
        "source_url": source_url,
        "source": source,
    }


def build_newspaper() -> Path:
    if not INPUT_PATH.exists():
        raise FileNotFoundError(f"Input file not found: {INPUT_PATH}")

    payload = json.loads(INPUT_PATH.read_text(encoding="utf-8"))
    if not isinstance(payload, list):
        raise ValueError("Input must be a JSON list of articles")

    stories = [_normalize_article(article) for article in payload if isinstance(article, dict)]

    sections_map: dict[str, list[dict[str, Any]]] = {name: [] for name in SECTION_ORDER}
    for story in stories:
        section_name = _assign_section(story)
        if section_name not in sections_map:
            section_name = "VÄRLDEN"
        sections_map[section_name].append(story)

    sections = [{"name": section_name, "stories": sections_map[section_name]} for section_name in SECTION_ORDER]
    sections = [section for section in sections if section["stories"]]

    top_bullets = _build_top_bullets(stories)
    daily_numbers = _build_daily_numbers(stories)

    html = Template(HTML_TEMPLATE).render(
        date_string=datetime.now().strftime("%Y-%m-%d"),
        top_bullets=top_bullets,
        daily_numbers=daily_numbers,
        sections=sections,
    )

    OUTPUT_HTML.parent.mkdir(parents=True, exist_ok=True)
    OUTPUT_HTML.write_text(html, encoding="utf-8")
    return OUTPUT_HTML


if __name__ == "__main__":
    output_file = build_newspaper()
    print(f"Wrote newspaper HTML to: {output_file}")
