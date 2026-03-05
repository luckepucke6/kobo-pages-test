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
TECH_SECTIONS = ["AI för utvecklare", "TECH INDUSTRY", "VERKTYG & OPEN SOURCE", "FORSKNING"]
SECTION_LIMITS = {
    "SVERIGE": 5,
    "VÄRLDEN": 6,
    "EKONOMI": 4,
    "VETENSKAP & MILJÖ": 3,
    "AI för utvecklare": 6,
    "TECH INDUSTRY": 4,
}
SECTION_PRIORITY = {
    "VÄRLDEN": 1,
    "EKONOMI": 2,
    "AI för utvecklare": 3,
    "TECH INDUSTRY": 3,
    "VERKTYG & OPEN SOURCE": 3,
    "FORSKNING": 4,
    "VETENSKAP & MILJÖ": 4,
    "SVERIGE": 5,
}
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
    "Du är en svensk tidningsredaktör för en morgontidning på e-läsare. "
    "Skriv klar och journalistisk svenska med saklig ton. "
    "Undvik utfyllnadsfraser och undvik generiska formuleringar. "
    "Prioritera konkreta fakta och använd siffror endast när de finns i underlaget. "
    "Skriv korta stycken som fungerar bra på e-bläckskärm. "
    "Variera meningsbyggnaden så att samma struktur inte upprepas. "
    "Undvik sensationellt språk och använd inga emojis."
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
        "AI för utvecklare": [
            "machine learning",
            "mlops",
            "python",
            "pytorch",
            "tensorflow",
            "scikit",
            "ai infrastructure",
            "inference",
            "serving",
            "model serving",
            "vector database",
            "cuda",
            "kubernetes",
            "open source",
            "llm",
            "model",
            "hugging face",
            "vllm",
            "triton",
            "ray",
        ],
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


def _select_most_important_articles(
    section_name: str,
    articles: list[dict[str, str]],
    limit: int,
) -> list[dict[str, str]]:
    if len(articles) <= limit:
        return articles

    candidates = []
    for index, article in enumerate(articles):
        title = _clean_text(article.get("title", ""))
        summary = _clean_text(article.get("summary", ""))
        candidates.append({"index": index, "title": title, "summary": summary[:320]})

    response = client.chat.completions.create(
        model="gpt-4o-mini",
        response_format={"type": "json_object"},
        messages=[
            {"role": "system", "content": SYSTEM_PROMPT},
            {
                "role": "user",
                "content": (
                    f"Välj de {limit} viktigaste nyheterna för sektionen '{section_name}'. "
                    "Prioritera samhällspåverkan, nyhetsvärde, konsekvenser och aktualitet.\n\n"
                    f"Kandidater:\n{json.dumps(candidates, ensure_ascii=False)}\n\n"
                    "Returnera ENDAST JSON i formatet: {\"selected_indices\": [1, 2, 3]}"
                ),
            },
        ],
    )

    payload = json.loads(response.choices[0].message.content or "{}")
    selected_indices = payload.get("selected_indices", [])
    if not isinstance(selected_indices, list):
        selected_indices = []

    valid_indices: list[int] = []
    for value in selected_indices:
        if isinstance(value, int) and 0 <= value < len(articles) and value not in valid_indices:
            valid_indices.append(value)

    if len(valid_indices) < limit:
        for fallback_index in range(len(articles)):
            if fallback_index not in valid_indices:
                valid_indices.append(fallback_index)
            if len(valid_indices) >= limit:
                break

    return [articles[index] for index in valid_indices[:limit]]


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
                    '  "summary_paragraphs": ["Brödtext, totalt 4–6 meningar i korta stycken"],\n'
                    '  "why_important": "1–2 meningar",\n'
                    '  "eli5": "valfritt, bara vid komplexa ämnen"\n'
                    "}\n\n"
                    "Regler:\n"
                    "- Skriv på svenska.\n"
                    "- Rubrik ska vara tydlig och journalistisk.\n"
                    "- Ingress ska ge snabb överblick.\n"
                    "- Brödtext ska vara 4–6 meningar totalt och lätt att läsa på e-läsare.\n"
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

    summary_paragraphs = summary_paragraphs[:6]
    if len(summary_paragraphs) < 4 and summary_paragraphs:
        summary_paragraphs = summary_paragraphs + [summary_paragraphs[-1]] * (4 - len(summary_paragraphs))

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


def _story_priority_bucket(story: dict[str, Any], section_name: str) -> int:
    text = " ".join(
        [
            _clean_text(story.get("title", "")),
            _clean_text(story.get("ingress", "")),
            _clean_text(story.get("why_important", "")),
            section_name,
        ]
    ).lower()

    if any(word in text for word in ["krig", "konflikt", "geopolit", "nato", "sanktion", "invasion"]):
        return 1
    if any(word in text for word in ["inflation", "ränta", "gdp", "börs", "ekonomi", "recession", "handel"]):
        return 2
    if any(word in text for word in ["ai", "tech", "teknik", "chip", "model", "open source", "startup"]):
        return 3
    if any(word in text for word in ["forskning", "science", "klimat", "miljö", "forsknings", "vetenskap"]):
        return 4
    return SECTION_PRIORITY.get(section_name, 5)


def _sort_stories_by_importance(stories: list[dict[str, Any]], section_name: str) -> list[dict[str, Any]]:
    return sorted(stories, key=lambda story: (_story_priority_bucket(story, section_name), story.get("title", "")))


def _sectioned_newspaper(
    articles: list[dict[str, str]],
    section_names: list[str],
    min_count: int,
    max_count: int,
    preferred_count: int,
    mapper: Any,
) -> list[dict[str, Any]]:
    selected_articles = articles

    grouped_raw: dict[str, list[dict[str, str]]] = {name: [] for name in section_names}
    for article in selected_articles:
        section = _pick_section(article, section_names)
        grouped_raw[section].append(article)

    grouped: dict[str, list[dict[str, Any]]] = {name: [] for name in section_names}
    for section_name in section_names:
        section_articles = grouped_raw[section_name]
        limit = SECTION_LIMITS.get(section_name)
        if limit is not None:
            section_articles = _select_most_important_articles(section_name, section_articles, limit)

        mapped_stories = [mapper(article) for article in section_articles]
        grouped[section_name] = _sort_stories_by_importance(mapped_stories, section_name)

    return [{"name": name, "stories": grouped[name]} for name in section_names]


def _generate_overview_bullets(sections: list[dict[str, Any]]) -> list[str]:
    story_candidates: list[dict[str, str | int]] = []
    priority_terms = {
        "geopolitics",
        "geopolitik",
        "krig",
        "war",
        "ekonomi",
        "economy",
        "inflation",
        "ränta",
        "trade",
        "technology",
        "tech",
        "ai",
        "climate",
        "klimat",
        "energy",
    }
    deprioritized_terms = {
        "lokal",
        "kommun",
        "trafikstörning",
        "sport",
        "kändis",
    }

    for section in sections:
        section_name = section.get("name", "")
        for story in section.get("stories", []):
            title = _clean_text(story.get("title", ""))
            why = _clean_text(story.get("why_important", ""))
            text = f"{section_name} {title} {why}".lower()

            score = 0
            score += sum(2 for term in priority_terms if term in text)
            score -= sum(2 for term in deprioritized_terms if term in text)

            if section_name in {"VÄRLDEN", "EKONOMI", "AI för utvecklare", "TECH INDUSTRY", "VETENSKAP & MILJÖ"}:
                score += 2

            story_candidates.append(
                {
                    "section": section_name,
                    "title": title,
                    "why": why,
                    "score": score,
                }
            )

    if not story_candidates:
        return []

    ranked_candidates = sorted(story_candidates, key=lambda item: int(item.get("score", 0)), reverse=True)
    top_candidates = ranked_candidates[:16]

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
                    "Varje punkt ska vara exakt en kort mening. "
                    "Prioritera globalt viktiga nyheter inom geopolitik, ekonomi, teknik och klimat. "
                    "Undvik lokala småhändelser.\n\n"
                    "Kandidater:\n"
                    f"{json.dumps(top_candidates, ensure_ascii=False)}\n\n"
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

    combined_sections = sorted(
        general_sections + tech_sections,
        key=lambda section: (SECTION_PRIORITY.get(section.get("name", ""), 5), section.get("name", "")),
    )
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
