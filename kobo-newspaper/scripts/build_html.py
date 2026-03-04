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
    :root {
      color-scheme: light;
    }

    body {
      margin: 0;
      padding: 0;
      background: #ffffff;
      color: #111111;
      font-family: Georgia, "Times New Roman", Times, serif;
      line-height: 1.7;
      font-size: 18px;
    }

    .page {
      max-width: 720px;
      margin: 0 auto;
      padding: 2.2rem 1.5rem 3.5rem;
    }

    h1, h2, h3 {
      margin: 0;
      line-height: 1.25;
      font-weight: 700;
      color: #111111;
    }

    p {
      margin: 0 0 0.85rem;
    }

    a {
      color: #111111;
      text-decoration: underline;
    }

    .title-page {
      margin-bottom: 2.2rem;
      padding-bottom: 1.1rem;
      border-bottom: 1px solid #d5d5d5;
    }

    .paper-title {
      font-size: 2.35rem;
      margin-bottom: 0.45rem;
      letter-spacing: 0.02em;
    }

    .date-line {
      font-size: 1.04rem;
      color: #2b2b2b;
      margin: 0;
    }

    .intro-block {
      margin-top: 1.4rem;
      margin-bottom: 1.4rem;
      padding-bottom: 1.1rem;
      border-bottom: 1px solid #dedede;
    }

    .intro-title {
      font-size: 1.5rem;
      margin-bottom: 0.55rem;
    }

    .overview-list {
      margin: 0;
      padding-left: 1.2rem;
    }

    .overview-list li {
      margin: 0 0 0.45rem;
    }

    .facts-list {
      margin: 0;
      padding-left: 1.2rem;
      color: #222222;
      font-size: 0.98rem;
    }

    .facts-list li {
      margin: 0 0 0.35rem;
    }

    .news-section {
      margin-top: 2rem;
      margin-bottom: 2.2rem;
    }

    .section-title {
      font-size: 1.85rem;
      margin-bottom: 1rem;
      border-top: 1px solid #c9c9c9;
      padding-top: 0.8rem;
      letter-spacing: 0.02em;
    }

    .story {
      margin-bottom: 2.2rem;
      padding-bottom: 1.3rem;
      border-bottom: 1px solid #e8e8e8;
    }

    .story-title {
      font-size: 1.35rem;
      margin-bottom: 0.55rem;
    }

    .ingress {
      font-style: italic;
      color: #202020;
      margin-bottom: 0.75rem;
    }

    .summary-paragraph {
      margin-bottom: 0.7rem;
    }

    .importance {
      margin-top: 0.75rem;
      margin-bottom: 0.8rem;
    }

    .eli5-box {
      border: 1px solid #cfcfcf;
      padding: 0.7rem 0.8rem;
      background: #f7f7f7;
      margin-bottom: 0.8rem;
    }

    .source {
      margin-top: 0.25rem;
      font-size: 0.97rem;
    }
  </style>
</head>
<body>
  <main class="page">
    <header class="title-page">
      <h1 class="paper-title">Morgontidningen</h1>
      <p class="date-line">Datum: {{ date_string }}</p>
    </header>

    <section class="intro-block">
      <h2 class="intro-title">Det viktigaste idag</h2>
      {% if overview_bullets %}
      <ul class="overview-list">
        {% for bullet in overview_bullets %}
        <li>{{ bullet }}</li>
        {% endfor %}
      </ul>
      {% else %}
      <p>Ingen sammanfattning tillgänglig ännu.</p>
      {% endif %}
    </section>

    <section class="intro-block">
      <h2 class="intro-title">Dagens fakta</h2>
      <ul class="facts-list">
        <li>Totalt antal sektioner: {{ total_sections }}</li>
        <li>Totalt antal artiklar: {{ total_stories }}</li>
        <li>Senast uppdaterad: {{ date_string }}</li>
        <li>Format: Optimerat för e-bläckläsning</li>
      </ul>
    </section>

    {% for section in sections %}
    <section class="news-section">
      <h2 class="section-title">{{ section.name }}</h2>

      {% for story in section.stories %}
      <article class="story">
        <h3 class="story-title">{{ story.title }}</h3>

        {% if story.ingress %}
        <p class="ingress">{{ story.ingress }}</p>
        {% endif %}

        {% for paragraph in story.summary_paragraphs %}
        <p class="summary-paragraph">{{ paragraph }}</p>
        {% endfor %}

        <p class="importance"><strong>Varför det är viktigt:</strong> {{ story.why_important }}</p>

        {% if story.eli5 %}
        <div class="eli5-box">
          <strong>ELI5:</strong> {{ story.eli5 }}
        </div>
        {% endif %}

        <p class="source"><a href="{{ story.source_url }}">Läs original</a></p>
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
    sections = data.get("sections", [])

    total_stories = sum(len(section.get("stories", [])) for section in sections)

    return template.render(
        title="Morgontidningen",
        date_string=date_string,
        overview_bullets=data.get("overview_bullets", []),
        sections=sections,
        total_sections=len(sections),
        total_stories=total_stories,
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
            "date": datetime.now().strftime("%Y-%m-%d"),
            "overview_bullets": [],
            "sections": [],
        }

    path = write_html_file(payload)
    print(f"Wrote HTML page to: {path}")
