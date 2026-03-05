from __future__ import annotations

import json
import re
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
      max-width: 720px;
      margin: auto;
      padding: 24px;
      background: #ffffff;
      color: #111111;
      font-family: Georgia, serif;
      line-height: 1.65;
      font-size: 18px;
    }

    .page {
      max-width: 100%;
      margin: 0;
      padding: 0;
    }

    h1, h2, h3 {
      margin: 0;
      line-height: 1.25;
      font-weight: 700;
      color: #111111;
    }

    h1 {
      font-size: 34px;
    }

    h2 {
      font-size: 26px;
      margin-top: 40px;
    }

    h3 {
      font-size: 20px;
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

    .brief-list {
      margin: 0;
      padding-left: 1.2rem;
    }

    .brief-list li {
      margin: 0 0 0.4rem;
    }

    .quote-text {
      margin: 0;
      padding-left: 12px;
      border-left: 3px solid #cfcfcf;
      font-style: italic;
      color: #1f1f1f;
    }

    .quote-source {
      margin-top: 0.55rem;
      font-size: 0.96rem;
      color: #333;
    }

    .section-divider {
      margin: 40px 0;
      border: none;
      border-top: 1px solid #ccc;
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

    .article {
      margin-bottom: 36px;
      padding-bottom: 1.3rem;
      border-bottom: 1px solid #e8e8e8;
    }

    .story-title {
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

    .eli5 {
      border-left: 4px solid #ccc;
      padding-left: 12px;
      margin-top: 8px;
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
      <h2 class="intro-title">Världen i korthet</h2>
      {% if world_in_brief %}
      <ul class="brief-list">
        {% for line in world_in_brief %}
        <li>{{ line }}</li>
        {% endfor %}
      </ul>
      {% else %}
      <p>Ingen kortöversikt tillgänglig ännu.</p>
      {% endif %}
    </section>

    <section class="intro-block">
      <h2 class="intro-title">Dagens citat</h2>
      {% if daily_quote %}
      <p class="quote-text">“{{ daily_quote.text }}”</p>
      <p class="quote-source">Från: {{ daily_quote.story_title }}</p>
      {% else %}
      <p>Inget citat tillgängligt ännu.</p>
      {% endif %}
    </section>

    {% for section in sections %}
    {% if not loop.first %}
    <hr class="section-divider">
    {% endif %}
    <section class="news-section">
      <h2 class="section-title">{{ section.name }}</h2>

      {% for story in section.stories %}
      <article class="article">
        <h3 class="story-title">{{ story.title }}</h3>

        {% if story.ingress %}
        <p class="ingress">{{ story.ingress }}</p>
        {% endif %}

        {% for paragraph in story.summary_paragraphs %}
        <p class="summary-paragraph">{{ paragraph }}</p>
        {% endfor %}

        <p class="importance"><strong>Varför det är viktigt:</strong> {{ story.why_important }}</p>

        {% if story.eli5 %}
        <div class="eli5">
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

    def _to_one_short_sentence(text: str, max_len: int = 120) -> str:
        clean = re.sub(r"\s+", " ", text or "").strip()
        if not clean:
            return ""

        parts = re.split(r"(?<=[.!?])\s+", clean)
        sentence = parts[0].strip() if parts else clean
        if not sentence.endswith((".", "!", "?")):
            sentence = f"{sentence}."

        if len(sentence) <= max_len:
            return sentence

        truncated = sentence[: max_len - 1].rstrip(" ,;:-")
        return f"{truncated}."

    def _extract_daily_quote() -> dict[str, str] | None:
        def _candidate_sentences(text: str) -> list[str]:
            clean = re.sub(r"\s+", " ", text or "").strip()
            if not clean:
                return []
            parts = re.split(r"(?<=[.!?])\s+", clean)
            return [part.strip() for part in parts if part.strip()]

        best_quote = ""
        best_story_title = ""

        for section in sections:
            stories = section.get("stories", [])
            for story in stories:
                story_title = str(story.get("title", "")).strip()
                paragraph_candidates = story.get("summary_paragraphs", [])

                text_blocks: list[str] = []
                if isinstance(paragraph_candidates, list):
                    text_blocks.extend(str(p) for p in paragraph_candidates if p)

                ingress = str(story.get("ingress", "")).strip()
                if ingress:
                    text_blocks.append(ingress)

                for block in text_blocks:
                    for sentence in _candidate_sentences(block):
                        sentence_clean = sentence.strip('"“” ')
                        if len(sentence_clean) < 45 or len(sentence_clean) > 220:
                            continue
                        if len(sentence_clean) > len(best_quote):
                            best_quote = sentence_clean
                            best_story_title = story_title or "Okänd artikel"

        if not best_quote:
            return None

        if not best_quote.endswith((".", "!", "?")):
            best_quote = f"{best_quote}."

        return {"text": best_quote, "story_title": best_story_title}

    world_in_brief: list[str] = []
    for section in sections:
        if len(world_in_brief) >= 6:
            break

        section_name = str(section.get("name", "")).strip()
        stories = section.get("stories", [])
        if not section_name or not stories:
            continue

        top_story = stories[0]
        title = str(top_story.get("title", "")).strip()
        if not title:
            continue

        headline_sentence = _to_one_short_sentence(title)
        if headline_sentence:
            world_in_brief.append(f"{section_name}: {headline_sentence}")

    daily_quote = _extract_daily_quote()

    return template.render(
        title="Morgontidningen",
        date_string=date_string,
        overview_bullets=data.get("overview_bullets", []),
        world_in_brief=world_in_brief,
        daily_quote=daily_quote,
        sections=sections,
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
