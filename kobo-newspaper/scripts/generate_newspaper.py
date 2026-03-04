from __future__ import annotations

import json
from datetime import datetime
from pathlib import Path
from typing import Any

from build_html import write_html_file
from fetch_rss import fetch_all_news

PROJECT_ROOT = Path(__file__).resolve().parents[1]
OUTPUT_JSON = PROJECT_ROOT / "pages" / "newspaper.json"

GENERAL_SECTIONS = ["SVERIGE", "VÄRLDEN", "EKONOMI", "VETENSKAP & MILJÖ"]
TECH_SECTIONS = ["AI & MACHINE LEARNING", "TECH INDUSTRY", "VERKTYG & OPEN SOURCE", "FORSKNING"]


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


def _build_general_article(article: dict[str, str]) -> dict[str, str]:
    title = _clean_text(article.get("title", "")) or "Utan rubrik"
    source_summary = _clean_text(article.get("summary", ""))
    published = article.get("published", "okänd tid")

    sentence_1 = f"Artikeln '{title}' beskriver en aktuell händelse under det senaste dygnet."
    sentence_2 = f"Den rapporterade kärnan är: {source_summary[:220] if source_summary else 'RSS-källan gav begränsad bakgrund.'}"
    sentence_3 = f"Publiceringstid enligt källan är {published}."
    short_summary = " ".join([sentence_1, sentence_2, sentence_3])
    importance = "Det är viktigt eftersom nyheten påverkar samhällsläget och hjälper läsaren att fatta informerade beslut."

    return {
        "rubrik": title,
        "kort_sammanfattning": short_summary,
        "varfor_det_ar_viktigt": importance,
        "link": article.get("link", "#"),
        "published": published,
    }


def _build_tech_article(article: dict[str, str]) -> dict[str, str]:
    title = _clean_text(article.get("title", "")) or "Utan rubrik"
    source_summary = _clean_text(article.get("summary", ""))
    published = article.get("published", "okänd tid")

    sentence_1 = f"Nyheten '{title}' rör teknikområdet och har tydlig koppling till dagens utveckling."
    sentence_2 = f"Kärninnehåll: {source_summary[:220] if source_summary else 'begränsad beskrivning från RSS-källan.'}"
    sentence_3 = f"Uppgiften publicerades {published} och ger en aktuell bild av marknaden."
    short_explanation = " ".join([sentence_1, sentence_2, sentence_3])
    relevance = "Det är relevant för AI/tech eftersom förändringen kan påverka verktyg, modeller eller hur team bygger produkter."

    return {
        "rubrik": title,
        "kort_forklaring": short_explanation,
        "varfor_relevant_ai_tech": relevance,
        "link": article.get("link", "#"),
        "published": published,
    }


def _sectioned_newspaper(
    articles: list[dict[str, str]],
    section_names: list[str],
    min_count: int,
    max_count: int,
    preferred_count: int,
    mapper: Any,
) -> list[dict[str, Any]]:
    selected_count = _target_count(len(articles), min_count=min_count, max_count=max_count, preferred=preferred_count)
    selected_articles = articles[:selected_count]

    grouped: dict[str, list[dict[str, str]]] = {name: [] for name in section_names}
    for article in selected_articles:
        section = _pick_section(article, section_names)
        grouped[section].append(mapper(article))

    return [{"name": name, "articles": grouped[name]} for name in section_names]


def _build_payload(raw_news: dict[str, list[dict[str, str]]]) -> dict[str, Any]:
    general_articles = raw_news.get("general", [])
    tech_articles = raw_news.get("tech", [])

    general_sections = _sectioned_newspaper(
        general_articles,
        section_names=GENERAL_SECTIONS,
        min_count=8,
        max_count=12,
        preferred_count=10,
        mapper=_build_general_article,
    )
    tech_sections = _sectioned_newspaper(
        tech_articles,
        section_names=TECH_SECTIONS,
        min_count=6,
        max_count=10,
        preferred_count=8,
        mapper=_build_tech_article,
    )

    html_sections: list[dict[str, Any]] = [
        {"name": "Morgontidningen", "articles": []},
        {"name": "Tech & AI-morgonbrief", "articles": []},
    ]

    for section in general_sections:
        for article in section["articles"]:
            html_sections[0]["articles"].append(
                {
                    "title": f"[{section['name']}] {article['rubrik']}",
                    "summary": f"{article['kort_sammanfattning']} {article['varfor_det_ar_viktigt']}",
                    "link": article["link"],
                }
            )

    for section in tech_sections:
        for article in section["articles"]:
            html_sections[1]["articles"].append(
                {
                    "title": f"[{section['name']}] {article['rubrik']}",
                    "summary": f"{article['kort_forklaring']} {article['varfor_relevant_ai_tech']}",
                    "link": article["link"],
                }
            )

    return {
        "title": "Kobo Morgonnyheter",
        "date": datetime.now().strftime("%Y-%m-%d"),
        "general_newspaper": {
            "name": "Morgontidningen",
            "sections": general_sections,
            "article_count": sum(len(section["articles"]) for section in general_sections),
        },
        "tech_newspaper": {
            "name": "Tech & AI-morgonbrief",
            "sections": tech_sections,
            "article_count": sum(len(section["articles"]) for section in tech_sections),
        },
        "sections": html_sections,
    }


def generate() -> Path:
    raw_news = fetch_all_news()
    payload = _build_payload(raw_news)

    OUTPUT_JSON.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")
    html_path = write_html_file(payload)
    return html_path


if __name__ == "__main__":
    result = generate()
    print(f"Generated newspaper HTML: {result}")
