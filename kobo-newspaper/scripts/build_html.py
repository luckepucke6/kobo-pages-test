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
    body {
      max-width: 700px;
      margin: auto;
      line-height: 1.6;
      padding: 16px;
      font-family: Georgia, serif;
      font-size: 17px;
    }

    img {
            width: 100%;
            max-width: 680px;
      height: auto;
      margin: 10px auto;
      display: block;
    }

    h1, h2, h3, h4 {
      margin: 1em 0 0.4em;
      line-height: 1.3;
    }

    h1 {
      margin-top: 0;
      font-size: 30px;
    }

    h2 {
      font-size: 24px;
    }

    h3 {
      font-size: 20px;
    }

    p {
      margin: 0 0 0.8em;
    }

    ul {
      margin: 0;
      padding-left: 1.2em;
    }

    li {
      margin: 0 0 0.45em;
    }

    article {
      margin: 0 0 1.6em;
    }
  </style>
</head>
<body>
  <h1>Morgontidningen</h1>
  <p>Datum: {{ date_string }}</p>

  <h2>Det viktigaste idag</h2>
  {% if overview_bullets %}
  <ul>
    {% for bullet in overview_bullets %}
    <li>{{ bullet }}</li>
    {% endfor %}
  </ul>
  {% else %}
  <p>Ingen sammanfattning tillgänglig ännu.</p>
  {% endif %}

  <h2>Dagens siffror</h2>
  {% if daily_numbers %}
  <ul>
    {% for item in daily_numbers %}
    <li>{{ item }}</li>
    {% endfor %}
  </ul>
  {% else %}
  <p>Inga tydliga nyckeltal tillgängliga ännu.</p>
  {% endif %}

  <h2>Världen i korthet</h2>
  {% if world_in_brief %}
  <ul>
    {% for line in world_in_brief %}
    <li>{{ line }}</li>
    {% endfor %}
  </ul>
  {% else %}
  <p>Ingen kortöversikt tillgänglig ännu.</p>
  {% endif %}

  <h2>Dagens citat</h2>
  {% if daily_quote %}
  <p>“{{ daily_quote.text }}”</p>
  <p>Från: {{ daily_quote.story_title }}</p>
  {% else %}
  <p>Inget citat tillgängligt ännu.</p>
  {% endif %}

  {% for section in sections %}
  <h2>{{ section.name }}</h2>
  {% for story in section.stories %}
  <article>
    <h3>{{ story.title }}</h3>

        {% if story.render_image and story.image_url %}
    <img src="{{ story.image_url }}" alt="">
    {% endif %}

    {% if story.ingress %}
    <p>{{ story.ingress }}</p>
    {% endif %}

    {% for paragraph in story.summary_paragraphs %}
    <p>{{ paragraph }}</p>
    {% endfor %}

    <p>Varför det är viktigt: {{ story.why_important }}</p>

    {% if story.what_happened %}
    <p>What happened: {{ story.what_happened }}</p>
    {% endif %}

    {% if story.why_it_matters_for_ml_engineers %}
    <p>Why it matters for ML engineers: {{ story.why_it_matters_for_ml_engineers }}</p>
    {% endif %}

    {% if story.eli5 %}
    <p>ELI5: {{ story.eli5 }}</p>
    {% endif %}

    <p>Källa: {{ story.source_url }}</p>
  </article>
  {% endfor %}
  {% endfor %}
</body>
</html>
"""


def build_html(data: dict[str, Any]) -> str:
    template = Template(HTML_TEMPLATE)
    date_string = data.get("date") or datetime.now().strftime("%Y-%m-%d")
    raw_sections = data.get("sections", [])
    sections = [
        section
        for section in raw_sections
        if isinstance(section, dict)
        and isinstance(section.get("stories"), list)
        and len(section.get("stories", [])) > 0
    ]

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

    def _extract_daily_numbers() -> list[str]:
        pattern = re.compile(r"\b\d+[\d\s.,]*\s*(?:%|procent|kr|SEK|USD|EUR|dollar|punkter|miljoner|miljarder)?\b", re.IGNORECASE)

        labeled_numbers: dict[str, str] = {}
        fallback_numbers: list[str] = []

        for section in sections:
            for story in section.get("stories", []):
                text_blocks: list[str] = []
                text_blocks.append(str(story.get("title", "")))
                text_blocks.append(str(story.get("ingress", "")))
                text_blocks.append(str(story.get("why_important", "")))
                paragraphs = story.get("summary_paragraphs", [])
                if isinstance(paragraphs, list):
                    text_blocks.extend(str(paragraph) for paragraph in paragraphs)

                combined = " ".join(text_blocks)
                lower = combined.lower()
                matches = [m.group(0).strip() for m in pattern.finditer(combined)]
                matches = [value for value in matches if any(char.isdigit() for char in value)]
                if not matches:
                    continue

                def _set_label(key: str, label: str) -> None:
                    if key not in labeled_numbers:
                        labeled_numbers[key] = label

                if "inflation" in lower:
                    _set_label("inflation", f"Svensk inflation: {matches[0]}")
                if "ränta" in lower or "styrränta" in lower or "riksbank" in lower:
                    _set_label("rate", f"Svensk ränta: {matches[0]}")
                if "olja" in lower or "oil" in lower or "brent" in lower:
                    _set_label("oil", f"Oljepris: {matches[0]}")
                if "index" in lower or "börs" in lower or "stock" in lower:
                    _set_label("index", f"Börsindex: {matches[0]}")
                if any(term in lower for term in ["gdp", "arbetslöshet", "tillväxt", "pmi", "bnp"]):
                    _set_label("indicator", f"Ekonomisk indikator: {matches[0]}")

                for match in matches:
                    if len(fallback_numbers) >= 8:
                        break
                    fallback_numbers.append(f"Nyckeltal: {match}")

        ordered_keys = ["inflation", "rate", "oil", "index", "indicator"]
        selected: list[str] = [labeled_numbers[key] for key in ordered_keys if key in labeled_numbers]

        for fallback in fallback_numbers:
            if len(selected) >= 6:
                break
            if fallback not in selected:
                selected.append(fallback)

        return selected[:6]

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

    sections_for_render: list[dict[str, Any]] = []
    for section in sections:
        stories = section.get("stories", [])
        image_count = 0
        rendered_stories: list[dict[str, Any]] = []

        for story in stories:
            story_copy = dict(story)
            image_url = story_copy.get("image_url")
            has_image = isinstance(image_url, str) and image_url.strip() != ""

            render_image = False
            if has_image and image_count < 3:
                render_image = True
                image_count += 1

            story_copy["render_image"] = render_image
            rendered_stories.append(story_copy)

        section_copy = dict(section)
        section_copy["stories"] = rendered_stories
        sections_for_render.append(section_copy)

    daily_quote = _extract_daily_quote()
    daily_numbers = _extract_daily_numbers()

    return template.render(
        title="Morgontidningen",
        date_string=date_string,
        overview_bullets=data.get("overview_bullets", []),
        daily_numbers=daily_numbers,
        world_in_brief=world_in_brief,
        daily_quote=daily_quote,
        sections=sections_for_render,
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
