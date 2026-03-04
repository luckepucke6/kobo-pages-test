from __future__ import annotations

import json
import os
from datetime import datetime
from pathlib import Path
from typing import Any

from openai import OpenAI

from build_html import write_html_file
from fetch_rss import fetch_all_news

PROJECT_ROOT = Path(__file__).resolve().parents[1]
OUTPUT_JSON = PROJECT_ROOT / "pages" / "newspaper.json"

GENERAL_SECTIONS = ["SVERIGE", "VÄRLDEN", "EKONOMI", "VETENSKAP & MILJÖ"]
TECH_SECTIONS = ["AI & MACHINE LEARNING", "TECH INDUSTRY", "VERKTYG & OPEN SOURCE", "FORSKNING"]
COMPLEX_TOPICS = {
    "war",
    "krig",
    "economy",
    "ekonomi",
    "law",
    "juridik",
    "ai",
    "regulation",
    "reglering",
    "geopolitics",
    "geopolitik",
}

SYSTEM_PROMPT = (
    "Du är en svensk morgontidningsredaktör som skriver för e-bläcksläsare. "
    "Skriv på klar och tydlig svenska i journalistisk ton. "
    "Hitta aldrig på fakta; om något är oklart ska du skriva exakt: 'Det framgår inte av källan'. "
    "Undvik sensationellt språk. "
    "Håll stycken korta för e-läsning. "
    "Använd konkreta siffror endast om de faktiskt finns i källtexten. "
    "Inga emojis."
)

client = OpenAI(api_key=os.environ["OPENAI_API_KEY"])


def _clean_text(raw: str) -> str:
    return " ".join(raw.replace("\n", " ").split())


def _keyword_map() -> dict[str, list[str]]:
    return {
        "SVERIGE": ["sverige", "svensk", "sweden", "svt", "stockholm", "göteborg", "malmö"],
        "VÄRLDEN": ["world", "världen", "ukraina", "usa", "eu", "global", "krig", "konflikt"],
        "EKONOMI": ["ekonomi", "börs", "inflation", "ränta", "bank", "budget", "marknad", "gdp"],
        "VETENSKAP & MILJÖ": ["klimat", "miljö", "forskning", "science", "hälsa", "väder", "utsläpp"],
        "AI & MACHINE LEARNING": ["ai", "machine learning", "llm", "model", "transformer", "neural"],
        "TECH INDUSTRY": ["startup", "company", "acquisition", "product", "apple", "google", "microsoft"],
        "VERKTYG & OPEN SOURCE": ["open source", "github", "tool", "sdk", "framework", "library", "release"],
        "FORSKNING": ["paper", "study", "research", "benchmark", "dataset", "arxiv", "lab"],
    }


def _pick_section(article: dict[str, str], section_names: list[str]) -> str:
    text = f"{article.get('title', '')} {article.get('summary', '')}".lower()
    keywords = _keyword_map()

    for section in section_names:
        for keyword in keywords.get(section, []):
            if keyword in text:
                return section
    return section_names[0]


def _target_count(total_available: int, min_count: int, max_count: int, preferred: int) -> int:
    if total_available <= 0:
        return 0
    desired = max(min_count, min(max_count, preferred))
    return min(total_available, desired)


def summarize_article(title: str, content: str) -> dict:
    content = _clean_text(content)
    combined = f"{title} {content}".lower()
    is_complex = any(topic in combined for topic in COMPLEX_TOPICS)

    response = client.chat.completions.create(
        model="gpt-4o-mini",
        response_format={"type": "json_object"},
        messages=[
            {
                "role": "system",
                "content": SYSTEM_PROMPT,
            },
            {
                "role": "user",
                "content": (
                    "Input:\n"
                    f"Titel: {title}\n"
                    f"Artikelinnehåll: {content}\n\n"
                    "Returnera ENDAST JSON med denna struktur:\n"
                    "{\n"
                    '  "title": "Rubrik",\n'
                    '  "ingress": "1–2 meningar",\n'
                    '  "summary_paragraphs": ["5–8 korta meningar uppdelade i korta stycken"],\n'
                    '  "why_important": "1–2 meningar",\n'
                    '  "eli5": "valfritt, bara vid komplexa ämnen"\n'
                    "}\n\n"
                    "Regler:\n"
                    "- Skriv på svenska.\n"
                    "- Rubrik ska vara tydlig och journalistisk.\n"
                    "- Ingress ska ge snabb överblick.\n"
                    "- Sammanfattning ska vara 5–8 meningar totalt och lätt att läsa på e-läsare.\n"
                    "- Varför det är viktigt ska vara 1–2 meningar.\n"
                    f"- ELI5 ska {'inkluderas' if is_complex else 'utelämnas'} för den här artikeln."
                ),
            },
        ],
    )

    payload = json.loads(response.choices[0].message.content or "{}")
    paragraphs = payload.get("summary_paragraphs", [])

    if isinstance(paragraphs, str):
        summary_paragraphs = [p.strip() for p in paragraphs.split("\n") if p.strip()]
    elif isinstance(paragraphs, list):
        summary_paragraphs = [_clean_text(str(p)) for p in paragraphs if str(p).strip()]
    else:
        summary_paragraphs = []

    if not summary_paragraphs:
        fallback = _clean_text(content)
        if fallback:
            summary_paragraphs = [fallback]

    summary_paragraphs = summary_paragraphs[:8]
    if len(summary_paragraphs) < 5 and summary_paragraphs:
        summary_paragraphs = summary_paragraphs + [summary_paragraphs[-1]] * (5 - len(summary_paragraphs))

    eli5 = _clean_text(payload.get("eli5", ""))

    return {
        "title": _clean_text(payload.get("title", title)) or title,
        "ingress": _clean_text(payload.get("ingress", "")) or "En snabb överblick över dagens utveckling.",
        "summary_paragraphs": summary_paragraphs,
        "why_important": _clean_text(payload.get("why_important", "Det här är viktigt för att förstå dagens nyhetsläge.")),
        "eli5": eli5 if is_complex and eli5 else None,
    }


def _build_story(article: dict[str, str]) -> dict[str, Any]:
    title = _clean_text(article.get("title", "")) or "Utan rubrik"
    source_summary = _clean_text(article.get("summary", ""))
    summarized = summarize_article(title=title, content=source_summary)

    story: dict[str, Any] = {
        "title": summarized["title"],
        "ingress": summarized["ingress"],
        "summary_paragraphs": summarized["summary_paragraphs"],
        "why_important": summarized["why_important"],
        "source_url": article.get("link", "#"),
    }

    if summarized.get("eli5"):
        story["eli5"] = summarized["eli5"]

    return story


def _build_general_article(article: dict[str, str]) -> dict[str, Any]:
    return _build_story(article)


def _build_tech_article(article: dict[str, str]) -> dict[str, Any]:
    return _build_story(article)


def _sectioned_newspaper(
    articles: list[dict[str, str]],
    section_names: list[str],
    min_count: int,
    max_count: int,
    preferred_count: int,
    mapper: Any,
) -> list[dict[str, Any]]:
    selected_articles = articles

    grouped: dict[str, list[dict[str, Any]]] = {name: [] for name in section_names}
    for article in selected_articles:
        section = _pick_section(article, section_names)
        grouped[section].append(mapper(article))

    return [{"name": name, "stories": grouped[name]} for name in section_names]


def _generate_overview_bullets(sections: list[dict[str, Any]]) -> list[str]:
    story_lines: list[str] = []
    for section in sections:
        for story in section.get("stories", []):
            story_lines.append(f"[{section['name']}] {story['title']}: {story['why_important']}")

    if not story_lines:
        return []

    joined = "\n".join(story_lines[:12])
    response = client.chat.completions.create(
        model="gpt-4o-mini",
        response_format={"type": "json_object"},
        messages=[
            {
                "role": "system",
                "content": SYSTEM_PROMPT,
            },
            {
                "role": "user",
                "content": (
                    "Skapa avsnittet 'Det viktigaste idag' med 4–6 punktlistor. "
                    "Varje punkt ska vara en kort mening utan emojis.\n\n"
                    "Underlag:\n"
                    f"{joined}\n\n"
                    "Returnera endast JSON: {\"overview_bullets\": [\"...\", \"...\"]}"
                ),
            },
        ],
    )

    payload = json.loads(response.choices[0].message.content or "{}")
    bullets = payload.get("overview_bullets", [])
    if not isinstance(bullets, list):
        return []

    clean_bullets = [_clean_text(str(item)) for item in bullets if _clean_text(str(item))]
    return clean_bullets[:6]


def _build_payload(raw_news: dict[str, list[dict[str, str]]]) -> dict[str, Any]:
    general_articles = raw_news.get("general", [])
    tech_articles = raw_news.get("tech", [])

    general_sections = _sectioned_newspaper(
        general_articles,
        section_names=GENERAL_SECTIONS,
        min_count=len(general_articles),
        max_count=len(general_articles),
        preferred_count=len(general_articles),
        mapper=_build_general_article,
    )
    tech_sections = _sectioned_newspaper(
        tech_articles,
        section_names=TECH_SECTIONS,
        min_count=len(tech_articles),
        max_count=len(tech_articles),
        preferred_count=len(tech_articles),
        mapper=_build_tech_article,
    )

    combined_sections = general_sections + tech_sections
    overview_bullets = _generate_overview_bullets(combined_sections)

    return {
        "date": datetime.now().strftime("%Y-%m-%d"),
        "overview_bullets": overview_bullets,
        "sections": combined_sections,
    }


def _build_html_payload(payload: dict[str, Any]) -> dict[str, Any]:
    general_sections = [section for section in payload["sections"] if section["name"] in GENERAL_SECTIONS]
    tech_sections = [section for section in payload["sections"] if section["name"] in TECH_SECTIONS]

    def _to_legacy_articles(stories: list[dict[str, Any]]) -> list[dict[str, str]]:
        legacy_articles: list[dict[str, str]] = []
        for story in stories:
            summary = " ".join(story.get("summary_paragraphs", []))
            legacy_articles.append(
                {
                    "rubrik": story.get("title", "Utan rubrik"),
                    "kort_sammanfattning": summary,
                    "varfor_det_ar_viktigt": story.get("why_important", ""),
                    "link": story.get("source_url", "#"),
                }
            )
        return legacy_articles

    return {
        "title": "Kobo Morgonnyheter",
        "date": payload["date"],
        "general_newspaper": {
            "name": "Morgontidningen",
            "sections": [
                {"name": section["name"], "articles": _to_legacy_articles(section["stories"])}
                for section in general_sections
            ],
        },
        "tech_newspaper": {
            "name": "Tech & AI-morgonbrief",
            "sections": [
                {"name": section["name"], "articles": _to_legacy_articles(section["stories"])}
                for section in tech_sections
            ],
        },
    }


def generate() -> Path:
    raw_news = fetch_all_news()
    payload = _build_payload(raw_news)
    html_payload = _build_html_payload(payload)

    OUTPUT_JSON.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")
    html_path = write_html_file(html_payload)
    return html_path


if __name__ == "__main__":
    result = generate()
    print(f"Generated newspaper HTML: {result}")
