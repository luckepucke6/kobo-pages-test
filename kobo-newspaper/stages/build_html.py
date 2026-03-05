from __future__ import annotations

from datetime import datetime
from pathlib import Path
from typing import Any

from jinja2 import Template

from app.models import HTML_OUTPUT, QUOTES_OUTPUT, clean_text, read_json, today_iso, write_json

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

  {% for article in articles %}
  <article>
    <h2>{{ article.title }}</h2>
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
                "reflection_question": _reflection_question(str(raw.get("title", ""))),
            }
        )

    date = today_iso()
    title = "Morgontidningen"
    html = Template(HTML_TEMPLATE).render(title=title, date=date, articles=articles)

    rendered_payload = {
        "date": date,
        "title": title,
        "edition_filename": f"{date}.html",
        "html": html,
        "article_count": len(articles),
    }
    return write_json(HTML_OUTPUT, rendered_payload)


if __name__ == "__main__":
    output = run()
    print(f"Saved rendered HTML payload to: {output}")
