from __future__ import annotations

import json
from datetime import datetime
from pathlib import Path
from typing import Any

from jinja2 import Template

PROJECT_ROOT = Path(__file__).resolve().parents[1]
OUTPUT_HTML = PROJECT_ROOT / "pages" / "index.html"

HTML_TEMPLATE = """<!doctype html>
<html lang="sv">
<head>
  <meta charset="utf-8" />
  <meta name="viewport" content="width=device-width, initial-scale=1" />
  <title>{{ title }}</title>
  <style>
    body {
      margin: 0;
      padding: 0;
      background: #ffffff;
      color: #111111;
      font-family: Georgia, "Times New Roman", serif;
      line-height: 1.6;
      font-size: 18px;
    }

    .page {
      max-width: 42em;
      margin: 0 auto;
      padding: 2em 1.5em 3em;
    }

    h1, h2, h3 {
      line-height: 1.25;
      margin: 0;
    }

    .title-page {
      margin-bottom: 2.6em;
    }

    .newspaper-title {
      font-size: 2.4rem;
      margin-bottom: 0.35em;
    }

    .newspaper-date {
      font-size: 1.05rem;
      margin: 0;
    }

    .section-block {
      margin-bottom: 2.4em;
    }

    .section-title {
      font-size: 1.6rem;
      margin-bottom: 0.7em;
      letter-spacing: 0.02em;
      border-top: 1px solid #cfcfcf;
      padding-top: 0.7em;
    }

    .article {
      margin-bottom: 2em;
    }

    .article-title {
      font-size: 1.25rem;
      margin-bottom: 0.45em;
    }

    p {
      margin: 0 0 0.8em;
    }

    a {
      color: #111111;
      text-decoration: underline;
    }

    .meta {
      font-size: 0.95rem;
      margin-top: 0.4em;
    }

    .newspaper-divider {
      margin: 2.4em 0;
      border: 0;
      border-top: 1px solid #bfbfbf;
    }
  </style>
</head>
<body>
  <main class="page">
    <section class="title-page">
      <h1 class="newspaper-title">Morgontidningen</h1>
      <p class="newspaper-date">Datum: {{ date_string }}</p>
    </section>

    {% for section in general_newspaper.sections %}
    <section class="section-block">
      <h2 class="section-title">{{ section.name }}</h2>
      {% for article in section.articles %}
      <article class="article">
        <h3 class="article-title">{{ article.rubrik }}</h3>
        <p>{{ article.kort_sammanfattning }}</p>
        <p><strong>Varför det är viktigt:</strong> {{ article.varfor_det_ar_viktigt }}</p>
        <p class="meta"><a href="{{ article.link }}">Läs original</a></p>
      </article>
      {% endfor %}
    </section>
    {% endfor %}

    <hr class="newspaper-divider" />

    <section class="title-page">
      <h1 class="newspaper-title">Tech &amp; AI-morgonbrief</h1>
      <p class="newspaper-date">Datum: {{ date_string }}</p>
    </section>

    {% for section in tech_newspaper.sections %}
    <section class="section-block">
      <h2 class="section-title">{{ section.name }}</h2>
      {% for article in section.articles %}
      <article class="article">
        <h3 class="article-title">{{ article.rubrik }}</h3>
        <p>{{ article.kort_forklaring }}</p>
        <p><strong>Varför det är relevant för AI/tech:</strong> {{ article.varfor_relevant_ai_tech }}</p>
        <p class="meta"><a href="{{ article.link }}">Läs original</a></p>
      </article>
      {% endfor %}
    </section>
    {% endfor %}
  </main>
</body>
</html>
"""


def build_html(data: dict[str, Any]) -> str:
    template = Template(HTML_TEMPLATE)
    date_string = data.get("date") or datetime.now().strftime("%Y-%m-%d")

    return template.render(
        title=data.get("title", "Kobo Morgonnyheter"),
        date_string=date_string,
        general_newspaper=data.get("general_newspaper", {"sections": []}),
        tech_newspaper=data.get("tech_newspaper", {"sections": []}),
    )


def write_html_file(data: dict[str, Any], output_path: Path = OUTPUT_HTML) -> Path:
    html = build_html(data)
    output_path.parent.mkdir(parents=True, exist_ok=True)
    output_path.write_text(html, encoding="utf-8")
    return output_path


if __name__ == "__main__":
    newspaper_json_path = PROJECT_ROOT / "pages" / "newspaper.json"
    if newspaper_json_path.exists():
        payload = json.loads(newspaper_json_path.read_text(encoding="utf-8"))
    else:
        payload = {
            "title": "Kobo Morgonnyheter",
            "date": datetime.now().strftime("%Y-%m-%d"),
            "general_newspaper": {"sections": []},
            "tech_newspaper": {"sections": []},
        }

    path = write_html_file(payload)
    print(f"Wrote HTML page to: {path}")
