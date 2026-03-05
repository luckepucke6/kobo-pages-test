from __future__ import annotations

import json
import re
from datetime import datetime
from pathlib import Path
from typing import Any
from urllib.parse import urlparse

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

SWEDISH_SOURCE_SCORE_BONUS = 2
HEADLINE_MAX_LENGTH = 90
PRIORITY_SOURCE_DOMAINS = {
    "svt.se",
    "sr.se",
    "svd.se",
    "dn.se",
    "di.se",
}

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

    {% if top_timeline %}
    <h2>{{ top_timeline.title }}</h2>
    {% if top_timeline.events %}
    <ul>
        {% for event in top_timeline.events %}
        <li>{{ event }}</li>
        {% endfor %}
    </ul>
    {% else %}
    <p>Ingen tydlig tidslinje tillgänglig ännu.</p>
    {% endif %}
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
        <p><strong>Reflektionsfråga:</strong></p>
        <p>{{ story.reflection_question }}</p>
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


def _extract_domain(url: str) -> str:
    parsed = urlparse(_clean_text(url).lower())
    domain = parsed.netloc or ""
    if domain.startswith("www."):
        domain = domain[4:]
    return domain


def _is_priority_swedish_source(story: dict[str, Any]) -> bool:
    domain = _extract_domain(str(story.get("source_url", "")))
    if domain and any(domain == priority or domain.endswith(f".{priority}") for priority in PRIORITY_SOURCE_DOMAINS):
        return True

    source_text = _clean_text(story.get("source", "")).lower()
    fallback_markers = {"svt", "sveriges radio", "svd", "dn", "di"}
    return any(marker in source_text for marker in fallback_markers)


def _article_score(story: dict[str, Any]) -> int:
    base_score = int(story.get("score", 0))
    if _is_priority_swedish_source(story):
        base_score += SWEDISH_SOURCE_SCORE_BONUS
    return base_score


def _shorten_headline(headline: str, max_length: int = HEADLINE_MAX_LENGTH) -> str:
    cleaned = _clean_text(headline)
    if len(cleaned) <= max_length:
        return cleaned

    shortened = cleaned[:max_length].rstrip()
    if " " in shortened:
        shortened = shortened.rsplit(" ", 1)[0]
    if not shortened:
        shortened = cleaned[:max_length].rstrip()
    return f"{shortened}…"


def _format_headline(source_headline: Any) -> str:
    original = _clean_text(source_headline)
    if not original:
        return "Utan rubrik"
    return _shorten_headline(original)


def _split_sentences(text: str) -> list[str]:
    cleaned = _clean_text(text)
    if not cleaned:
        return []
    parts = re.split(r"(?<=[.!?])\s+", cleaned)
    return [part.strip() for part in parts if part.strip()]


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
        return "Vad är viktigast att följa nu?"

    normalized = t.lower()
    if any(term in normalized for term in ["ränta", "inflation", "ekonomi", "börs", "budget"]):
        return "Vad kan detta betyda för ekonomin framåt?"
    if any(term in normalized for term in ["ai", "ml", "modell", "inference", "pytorch", "tensorflow"]):
        return "Vilken praktisk effekt kan detta få i vardagen?"
    if any(term in normalized for term in ["krig", "konflikt", "nato", "ukraina", "säkerhet"]):
        return "Hur kan detta påverka läget de kommande veckorna?"
    if any(term in normalized for term in ["sverige", "regering", "riksdag", "lag", "domstol"]):
        return "Vilken följd kan detta få för Sverige?"

    return "Vilken konsekvens tycker du är viktigast här?"


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
    seen_keys: set[str] = set()

    def _shorten_explanation(text: str, max_words: int = 16) -> str:
        words = _clean_text(text).split()
        if len(words) <= max_words:
            return " ".join(words)
        return " ".join(words[:max_words]).rstrip(" ,;:-") + "…"

    for story in stories:
        title = _clean_text(story.get("title", ""))
        combined_text = " ".join(
            [
                title,
                _summary_to_text(story.get("summary", "")),
                _clean_text(story.get("why_it_matters", "")),
            ]
        )

        for sentence in _split_sentences(combined_text):
            cleaned_sentence = _clean_text(sentence)
            if not cleaned_sentence:
                continue

            for match in number_pattern.finditer(cleaned_sentence):
                number_value = _clean_text(match.group(0))
                if not number_value or not any(ch.isdigit() for ch in number_value):
                    continue

                explanation_base = cleaned_sentence.replace(match.group(0), "", 1).strip(" ,;:-")
                if not explanation_base:
                    explanation_base = "Nyckeltalet beskriver utvecklingen i artikeln"

                short_explanation = _shorten_explanation(explanation_base)
                context_text = _shorten_explanation(title, max_words=8) or "artikeln"
                explanation = f"{short_explanation} (kontekst: {context_text})"

                key = f"{number_value.lower()}::{explanation.lower()}"
                if key in seen_keys:
                    continue
                seen_keys.add(key)

                item = f"{number_value} – {explanation}"
                collected.append(item)

                if len(collected) >= 6:
                    return collected

    return collected[:6]


def _to_swedish_date_label(date_obj: datetime) -> str:
    months = [
        "jan",
        "feb",
        "mars",
        "apr",
        "maj",
        "juni",
        "juli",
        "aug",
        "sep",
        "okt",
        "nov",
        "dec",
    ]
    return f"{date_obj.day} {months[date_obj.month - 1]}"


def _parse_date_label_from_sentence(sentence: str) -> str | None:
    text = _clean_text(sentence).lower()
    if not text:
        return None

    month_map = {
        "jan": 1,
        "januari": 1,
        "feb": 2,
        "februari": 2,
        "mar": 3,
        "mars": 3,
        "apr": 4,
        "april": 4,
        "maj": 5,
        "jun": 6,
        "juni": 6,
        "jul": 7,
        "juli": 7,
        "aug": 8,
        "sep": 9,
        "sept": 9,
        "september": 9,
        "okt": 10,
        "oktober": 10,
        "nov": 11,
        "november": 11,
        "dec": 12,
        "december": 12,
    }

    day_month_match = re.search(
        r"\b(\d{1,2})\s*(jan|januari|feb|februari|mar|mars|apr|april|maj|jun|juni|jul|juli|aug|sep|sept|september|okt|oktober|nov|november|dec|december)\b",
        text,
    )
    if day_month_match:
        day = int(day_month_match.group(1))
        month = month_map.get(day_month_match.group(2), 0)
        if 1 <= day <= 31 and 1 <= month <= 12:
            return f"{day} {_to_swedish_date_label(datetime(2026, month, 1)).split(' ', 1)[1]}"

    iso_match = re.search(r"\b(20\d{2})-(\d{2})-(\d{2})\b", text)
    if iso_match:
        try:
            date_obj = datetime.strptime(iso_match.group(0), "%Y-%m-%d")
            return _to_swedish_date_label(date_obj)
        except ValueError:
            return None

    return None


def _shorten_event_text(text: str, max_words: int = 12) -> str:
    words = _clean_text(text).split()
    if len(words) <= max_words:
        return " ".join(words)
    return " ".join(words[:max_words]).rstrip(" ,;:-") + "…"


def _build_top_timeline(stories: list[dict[str, Any]]) -> dict[str, Any] | None:
    if not stories:
        return None

    top_story = stories[0]
    top_title = _clean_text(top_story.get("title", "Dagens största nyhet")) or "Dagens största nyhet"
    timeline_title = f"Tidslinje – {top_title}"

    sentence_pool: list[str] = []
    for field in ["summary", "why_it_matters", "quote", "eli5"]:
        sentence_pool.extend(_split_sentences(_clean_text(top_story.get(field, ""))))

    events: list[str] = []
    seen_event_texts: set[str] = set()
    published_raw = _clean_text(top_story.get("published", ""))
    fallback_date_label = ""
    if published_raw:
        try:
            fallback_date_label = _to_swedish_date_label(datetime.fromisoformat(published_raw.replace("Z", "+00:00")))
        except ValueError:
            fallback_date_label = _to_swedish_date_label(datetime.now())
    else:
        fallback_date_label = _to_swedish_date_label(datetime.now())

    for sentence in sentence_pool:
        cleaned_sentence = _clean_text(sentence)
        if len(cleaned_sentence) < 20:
            continue

        date_label = _parse_date_label_from_sentence(cleaned_sentence) or fallback_date_label

        event_text = _shorten_event_text(cleaned_sentence)
        normalized_text = event_text.lower()
        if normalized_text in seen_event_texts:
            continue

        seen_event_texts.add(normalized_text)
        events.append(f"{date_label} – {event_text}")

        if len(events) >= 4:
            break

    if not events:
        events = [f"{fallback_date_label} – {_shorten_event_text(top_story.get('summary', '') or top_story.get('why_it_matters', '') or top_title)}"]

    return {
        "title": timeline_title,
        "events": events,
    }


def _normalize_article(article: dict[str, Any]) -> dict[str, Any]:
    title = _format_headline(article.get("title", ""))
    summary = _summary_to_text(article.get("summary", article.get("summary_paragraphs", "")))
    why_it_matters = _clean_text(article.get("why_it_matters", article.get("why_important", "")))
    eli5 = _clean_text(article.get("eli5", "")) or "Ingen ELI5 tillgänglig."
    source_url = _clean_text(article.get("url", article.get("source_url", "#"))) or "#"
    source = _clean_text(article.get("source", ""))
    image_url = _clean_text(article.get("image_url", article.get("image", "")))
    published = _clean_text(article.get("published", ""))

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
        "image_url": image_url,
        "published": published,
        "score": 0,
    }


def build_newspaper() -> Path:
    if not INPUT_PATH.exists():
        raise FileNotFoundError(f"Input file not found: {INPUT_PATH}")

    payload = json.loads(INPUT_PATH.read_text(encoding="utf-8"))
    if not isinstance(payload, list):
        raise ValueError("Input must be a JSON list of articles")

    stories = [_normalize_article(article) for article in payload if isinstance(article, dict)]
    stories = sorted(stories, key=_article_score, reverse=True)

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
    top_timeline = _build_top_timeline(stories)

    html = Template(HTML_TEMPLATE).render(
        date_string=datetime.now().strftime("%Y-%m-%d"),
        top_bullets=top_bullets,
        daily_numbers=daily_numbers,
        top_timeline=top_timeline,
        sections=sections,
    )

    OUTPUT_HTML.parent.mkdir(parents=True, exist_ok=True)
    OUTPUT_HTML.write_text(html, encoding="utf-8")
    return OUTPUT_HTML


if __name__ == "__main__":
    output_file = build_newspaper()
    print(f"Wrote newspaper HTML to: {output_file}")
