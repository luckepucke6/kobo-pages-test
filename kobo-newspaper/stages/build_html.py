from __future__ import annotations

from pathlib import Path
from typing import Any

from jinja2 import Template

from app.models import HTML_OUTPUT, QUOTES_OUTPUT, clean_text, read_json, today_iso, write_json

SECTION_ORDER = [
    "Sweden",
    "World",
    "Economy",
    "AI & Technology",
    "Science & Environment",
]

SECTION_KEYWORDS: dict[str, list[str]] = {
    "Sweden": [
        "sverige",
        "sweden",
        "regering",
        "riksdag",
        "stockholm",
        "svensk",
        "myndighet",
    ],
    "World": [
        "world",
        "världen",
        "krig",
        "konflikt",
        "nato",
        "ukraina",
        "ryssland",
        "usa",
        "eu",
    ],
    "Economy": [
        "ekonomi",
        "economy",
        "inflation",
        "ränta",
        "riksbank",
        "börs",
        "bank",
        "budget",
        "marknad",
    ],
    "AI & Technology": [
        "ai",
        "artificial intelligence",
        "machine learning",
        "llm",
        "nvidia",
        "chip",
        "semiconductor",
        "openai",
        "anthropic",
        "tech",
        "software",
    ],
    "Science & Environment": [
        "science",
        "forskning",
        "miljö",
        "environment",
        "climate",
        "klimat",
        "utsläpp",
        "naturen",
        "energi",
    ],
}

MIN_ARTICLES_PER_SECTION = 2
MAX_ARTICLES_PER_SECTION = 4
TOP_STORIES_COUNT = 5

HTML_TEMPLATE = """<!doctype html>
<html lang=\"sv\">
<head>
  <meta charset=\"utf-8\" />
  <meta name=\"viewport\" content=\"width=device-width, initial-scale=1\" />
  <title>{{ title }}</title>
  <style>
    body { max-width: 700px; margin: auto; line-height: 1.6; font-family: Georgia, serif; padding: 16px; }
    img { width: 90%; max-width: 680px; height: auto; margin: 10px auto; display: block; }
    h1, h2, h3 { margin: 1em 0 0.4em; line-height: 1.3; }
    p { margin: 0 0 0.8em; }
    ul { margin: 0; padding-left: 1.2em; }
    li { margin: 0 0 0.45em; }
    article { margin: 0 0 1.6em; }
  </style>
</head>
<body>
  <h1>{{ title }}</h1>
  <p>Datum: {{ date }}</p>

    {% if top_stories %}
    <h2>Top Stories</h2>
    {% for article in top_stories %}
    <article>
        <h3>{{ article.title }}</h3>
        {% if article.image_url %}<img src="{{ article.image_url }}" alt="" />{% endif %}
        {% for sentence in article.summary %}
        <p>{{ sentence }}</p>
        {% endfor %}
        <p><strong>Citat:</strong> {{ article.quote }}</p>
        <p><strong>Varför det är viktigt:</strong> {{ article.why_it_matters }}</p>
        <p><strong>ELI5:</strong> {{ article.eli5 }}</p>
        <p><strong>Reflektionsfråga:</strong></p>
        <p>{{ article.reflection_question }}</p>
        <p><a href="{{ article.url }}">Källa</a></p>
    </article>
    {% endfor %}
    {% endif %}

    {% for section in sections %}
    <h2>{{ section.name }}</h2>
    {% for article in section.articles %}
  <article>
        <h3>{{ article.title }}</h3>
    {% if article.image_url %}<img src=\"{{ article.image_url }}\" alt=\"\" />{% endif %}
    {% for sentence in article.summary %}
    <p>{{ sentence }}</p>
    {% endfor %}
    <p><strong>Citat:</strong> {{ article.quote }}</p>
    <p><strong>Varför det är viktigt:</strong> {{ article.why_it_matters }}</p>
    <p><strong>ELI5:</strong> {{ article.eli5 }}</p>
    <p><strong>Reflektionsfråga:</strong></p>
    <p>{{ article.reflection_question }}</p>
    <p><a href=\"{{ article.url }}\">Källa</a></p>
  </article>
  {% endfor %}
    {% endfor %}
</body>
</html>
"""


def _reflection_question(title: str) -> str:
    normalized = clean_text(title).lower()
    if not normalized:
        return "Vad är viktigast att följa nu?"
    if any(term in normalized for term in ["ränta", "inflation", "ekonomi", "börs", "budget"]):
        return "Vad kan detta betyda för ekonomin framåt?"
    if any(term in normalized for term in ["ai", "ml", "modell", "inference", "pytorch", "tensorflow"]):
        return "Vilken praktisk effekt kan detta få i vardagen?"
    if any(term in normalized for term in ["krig", "konflikt", "nato", "ukraina", "säkerhet"]):
        return "Hur kan detta påverka läget de kommande veckorna?"
    if any(term in normalized for term in ["sverige", "regering", "riksdag", "lag", "domstol"]):
        return "Vilken följd kan detta få för Sverige?"
    return "Vilken konsekvens tycker du är viktigast här?"


def _format_headline(title: str, max_len: int = 90) -> str:
    headline = clean_text(title)
    if not headline:
        return "Utan rubrik"
    if len(headline) <= max_len:
        return headline
    clipped = headline[:max_len].rstrip()
    if " " in clipped:
        clipped = clipped.rsplit(" ", 1)[0]
    return f"{clipped}…"


def _to_float(value: Any) -> float:
    try:
        return float(value)
    except (TypeError, ValueError):
        return 0.0


def _to_int(value: Any, default: int = 0) -> int:
    try:
        return int(value)
    except (TypeError, ValueError):
        return default


def _pick_section(article: dict[str, Any]) -> str:
    category = clean_text(article.get("category", ""))
    if category == "Sweden":
        return "Sweden"
    if category == "World":
        return "World"
    if category in {"Economy", "Business"}:
        return "Economy"
    if category in {"AI_Tech", "AI & Technology", "Technology", "Tech"}:
        return "AI & Technology"
    if category in {"Science", "Science & Environment", "Environment"}:
        return "Science & Environment"

    summary_value = article.get("summary", [])
    summary_text = " ".join(summary_value) if isinstance(summary_value, list) else clean_text(summary_value)

    text = " ".join(
        [
            clean_text(article.get("title", "")),
            summary_text,
            clean_text(article.get("why_it_matters", "")),
        ]
    ).lower()

    best_section = "World"
    best_score = 0
    for section_name in SECTION_ORDER:
        score = sum(1 for keyword in SECTION_KEYWORDS.get(section_name, []) if keyword in text)
        if score > best_score:
            best_score = score
            best_section = section_name

    return best_section


def _balance_sections(section_map: dict[str, list[dict[str, Any]]]) -> dict[str, list[dict[str, Any]]]:
    overflow: list[dict[str, Any]] = []

    for section_name in SECTION_ORDER:
        section_articles = section_map[section_name]
        if len(section_articles) > MAX_ARTICLES_PER_SECTION:
            overflow.extend(section_articles[MAX_ARTICLES_PER_SECTION:])
            section_map[section_name] = section_articles[:MAX_ARTICLES_PER_SECTION]

    for section_name in SECTION_ORDER:
        while len(section_map[section_name]) < MIN_ARTICLES_PER_SECTION and overflow:
            section_map[section_name].append(overflow.pop(0))

    for section_name in SECTION_ORDER:
        while overflow and len(section_map[section_name]) < MAX_ARTICLES_PER_SECTION:
            section_map[section_name].append(overflow.pop(0))

    return section_map


def run() -> Path:
    payload = read_json(QUOTES_OUTPUT, default=[])
    if not isinstance(payload, list):
        raise ValueError("Expected list input from extract_quotes")

    articles: list[dict[str, Any]] = []
    for raw in payload:
        if not isinstance(raw, dict):
            continue
        summary_raw = raw.get("summary", [])
        if isinstance(summary_raw, list):
            summary = [clean_text(item) for item in summary_raw if clean_text(item)]
        else:
            summary = [clean_text(summary_raw)] if clean_text(summary_raw) else []

        articles.append(
            {
                "title": _format_headline(str(raw.get("title", ""))),
                "summary": summary[:8],
                "quote": clean_text(raw.get("quote", "")) or "Inget citat tillgängligt.",
                "why_it_matters": clean_text(raw.get("why_it_matters", "")),
                "eli5": clean_text(raw.get("eli5", "")),
                "url": clean_text(raw.get("url", "")),
                "image_url": clean_text(raw.get("image_url", "")),
                "importance_score": _to_float(raw.get("importance_score", 0.0)),
                "cluster_size": _to_int(raw.get("cluster_size", 1), default=1),
                "sources_covering_event": raw.get("sources_covering_event", []) if isinstance(raw.get("sources_covering_event", []), list) else [],
                "category": clean_text(raw.get("category", "")),
                "reflection_question": _reflection_question(str(raw.get("title", ""))),
            }
        )

    ranked_articles = sorted(articles, key=lambda item: item.get("importance_score", 0.0), reverse=True)
    top_stories = ranked_articles[:TOP_STORIES_COUNT]
    remaining_articles = ranked_articles[TOP_STORIES_COUNT:]

    section_map: dict[str, list[dict[str, Any]]] = {name: [] for name in SECTION_ORDER}
    for article in remaining_articles:
        section_name = _pick_section(article)
        section_map[section_name].append(article)

    section_map = _balance_sections(section_map)
    sections = [
        {"name": section_name, "articles": section_map[section_name]}
        for section_name in SECTION_ORDER
        if section_map[section_name]
    ]

    date = today_iso()
    title = "Morgontidningen"
    html = Template(HTML_TEMPLATE).render(title=title, date=date, top_stories=top_stories, sections=sections)

    rendered_payload = {
        "date": date,
        "title": title,
        "edition_filename": f"{date}.html",
        "html": html,
        "article_count": len(top_stories) + sum(len(section["articles"]) for section in sections),
        "sections": (
            [{"name": "Top Stories", "article_count": len(top_stories)}] if top_stories else []
        )
        + [{"name": section["name"], "article_count": len(section["articles"])} for section in sections],
    }
    return write_json(HTML_OUTPUT, rendered_payload)


if __name__ == "__main__":
    output = run()
    print(f"Saved rendered HTML payload to: {output}")
