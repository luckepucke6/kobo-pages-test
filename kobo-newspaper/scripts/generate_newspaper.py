from __future__ import annotations

import json
import os
import re
from datetime import datetime, timedelta
from difflib import SequenceMatcher
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


def _normalize_title(title: str) -> str:
    lowered = _clean_text(title).lower()
    no_punctuation = re.sub(r"[^\w\s]", " ", lowered)
    return " ".join(no_punctuation.split())


def _load_yesterday_titles() -> set[str]:
    yesterday = (datetime.now() - timedelta(days=1)).strftime("%Y-%m-%d")
    candidate_paths = [
        PROJECT_ROOT / "pages" / f"{yesterday}.json",
        OUTPUT_JSON,
    ]

    for candidate_path in candidate_paths:
        if not candidate_path.exists():
            continue

        try:
            payload = json.loads(candidate_path.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError):
            continue

        if payload.get("date") != yesterday:
            continue

        titles: set[str] = set()
        for section in payload.get("sections", []):
            stories = section.get("stories", []) if isinstance(section, dict) else []
            if not isinstance(stories, list):
                continue
            for story in stories:
                if not isinstance(story, dict):
                    continue
                normalized = _normalize_title(str(story.get("title", "")))
                if normalized:
                    titles.add(normalized)
        return titles

    return set()


def _is_duplicate_title(normalized_title: str, yesterday_titles: set[str]) -> bool:
    if not normalized_title or not yesterday_titles:
        return False

    if normalized_title in yesterday_titles:
        return True

    def _token_set(value: str) -> set[str]:
        return {token for token in value.split() if token}

    def _token_overlap(a: str, b: str) -> float:
        a_tokens = _token_set(a)
        b_tokens = _token_set(b)
        if not a_tokens or not b_tokens:
            return 0.0
        intersection = len(a_tokens & b_tokens)
        union = len(a_tokens | b_tokens)
        return intersection / union if union else 0.0

    for previous_title in yesterday_titles:
        sequence_similarity = SequenceMatcher(None, normalized_title, previous_title).ratio()
        overlap_similarity = _token_overlap(normalized_title, previous_title)

        # If headline is very close, treat as duplicate and skip.
        if sequence_similarity >= 0.88 or overlap_similarity >= 0.72:
            return True

    return False


def _filter_new_articles(articles: list[dict[str, str]], yesterday_titles: set[str]) -> list[dict[str, str]]:
    if not yesterday_titles:
        return articles

    filtered: list[dict[str, str]] = []
    for article in articles:
        normalized = _normalize_title(article.get("title", ""))
        if _is_duplicate_title(normalized, yesterday_titles):
            continue
        filtered.append(article)

    return filtered


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
    title_text = _clean_text(article.get("title", "")).lower()
    summary_text = _clean_text(article.get("summary", "")).lower()
    combined_text = f"{title_text} {summary_text}".strip()

    rules: list[tuple[str, list[str]]] = [
        ("SVERIGE", ["sverige", "svensk", "sweden", "stockholm", "göteborg", "malmö", "riksdag", "regering"]),
        ("VÄRLDEN", ["world", "världen", "internation", "global", "utrikes", "krig", "konflikt", "diplom", "nato", "ukraina", "usa", "eu", "mellanöstern"]),
        ("EKONOMI", ["ekonomi", "finance", "finans", "börs", "inflation", "ränta", "bank", "budget", "marknad", "gdp", "recession"]),
        ("AI", ["ai", "artificial intelligence", "machine learning", "ml", "llm", "modell", "model", "neural", "transformer", "inference"]),
        ("TECH INDUSTRY", ["apple", "google", "microsoft", "meta", "amazon", "nvidia", "big tech", "tech company", "semiconductor", "chip"]),
        ("VETENSKAP", ["science", "vetenskap", "climate", "klimat", "miljö", "environment", "utsläpp", "forskning", "väder", "biodiversity"]),
    ]

    canonical_to_project = {
        "AI": "AI för utvecklare",
        "VETENSKAP": "VETENSKAP & MILJÖ",
    }

    for canonical_section, keywords in rules:
        if any(keyword in combined_text for keyword in keywords):
            mapped_section = canonical_to_project.get(canonical_section, canonical_section)
            if mapped_section in section_names:
                return mapped_section

    if "VÄRLDEN" in section_names:
        return "VÄRLDEN"

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


def summarize_article(
    title: str,
    content: str,
    *,
    require_eli5: bool = False,
    include_dev_implication: bool = False,
) -> dict:
    content = _clean_text(content)
    combined = f"{title} {content}".lower()
    is_complex = any(topic in combined for topic in COMPLEX_TOPICS)
    json_dev_field = ',\n  "implication_for_developers": "1–2 meningar"' if include_dev_implication else ""
    rules_dev_line = "\n- Lägg till implication_for_developers med 1–2 korta meningar för utvecklare." if include_dev_implication else ""

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
                    '  "eli5": "valfritt, bara vid komplexa ämnen"'
                    f"{json_dev_field}\n"
                    "}\n\n"
                    "Regler:\n"
                    "- Skriv på svenska.\n"
                    "- Rubrik ska vara tydlig och journalistisk.\n"
                    "- Ingress ska ge snabb överblick.\n"
                    "- Brödtext ska vara 4–6 meningar totalt och lätt att läsa på e-läsare.\n"
                    "- Varför det är viktigt ska vara 1–2 meningar.\n"
                    f"- ELI5 ska {'inkluderas' if (is_complex or require_eli5) else 'utelämnas'} för den här artikeln."
                    f"{rules_dev_line}"
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
    implication_for_developers = _clean_text(payload.get("implication_for_developers", ""))

    if require_eli5 and not eli5:
        eli5 = "I korthet: nyheten handlar om hur AI-modeller och verktyg utvecklas och används i praktiken."

    if include_dev_implication and not implication_for_developers:
        implication_for_developers = "Detta påverkar val av modell, verktyg och driftmiljö för utvecklare."

    return {
        "title": _clean_text(payload.get("title", title)) or title,
        "ingress": _clean_text(payload.get("ingress", "")) or "En snabb överblick över dagens utveckling.",
        "summary_paragraphs": summary_paragraphs,
        "why_important": _clean_text(payload.get("why_important", "Det här är viktigt för att förstå dagens nyhetsläge.")),
        "eli5": eli5 if (is_complex or require_eli5) and eli5 else None,
        "implication_for_developers": implication_for_developers if include_dev_implication else None,
    }


def _build_story(article: dict[str, str], section_name: str) -> dict[str, Any]:
    title = _clean_text(article.get("title", "")) or "Utan rubrik"
    source_summary = _clean_text(article.get("summary", ""))
    is_ai_section = section_name in {"AI", "AI för utvecklare", "AI & MACHINE LEARNING"}
    summarized = summarize_article(
        title=title,
        content=source_summary,
        require_eli5=is_ai_section,
        include_dev_implication=is_ai_section,
    )
    image_url = article.get("image_url")

    story: dict[str, Any] = {
        "title": summarized["title"],
        "ingress": summarized["ingress"],
        "summary_paragraphs": summarized["summary_paragraphs"],
        "why_important": summarized["why_important"],
        "source_url": article.get("link", "#"),
        "image_url": image_url if isinstance(image_url, str) and image_url.strip() else None,
    }

    if summarized.get("eli5"):
        story["eli5"] = summarized["eli5"]

    if summarized.get("implication_for_developers"):
        story["implication_for_developers"] = summarized["implication_for_developers"]

    return story


def _build_general_article(article: dict[str, str], section_name: str) -> dict[str, Any]:
    return _build_story(article, section_name)


def _build_tech_article(article: dict[str, str], section_name: str) -> dict[str, Any]:
    return _build_story(article, section_name)


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

        mapped_stories = [mapper(article, section_name) for article in section_articles]
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

    def _short_explanation(text: str, max_words: int = 10) -> str:
        cleaned = _clean_text(text)
        if not cleaned:
            return "Viktig utveckling idag."

        words = cleaned.split()
        limited_words = words[:max_words]
        compact = " ".join(limited_words).rstrip(" ,;:-")
        if not compact:
            return "Viktig utveckling idag."
        if not compact.endswith((".", "!", "?")):
            compact += "."
        return compact

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
    top_candidates = ranked_candidates[:5]

    bullets: list[str] = []
    for candidate in top_candidates:
        headline = _clean_text(str(candidate.get("title", "")))
        explanation_source = _clean_text(str(candidate.get("why", "")))

        if not headline:
            continue

        explanation = _short_explanation(explanation_source, max_words=10)
        bullets.append(f"{headline} – {explanation}")

    return bullets[:5]


def _build_payload(raw_news: dict[str, list[dict[str, str]]]) -> dict[str, Any]:
    yesterday_titles = _load_yesterday_titles()

    general_articles = _filter_new_articles(raw_news.get("general", []), yesterday_titles)
    tech_articles = _filter_new_articles(raw_news.get("tech", []), yesterday_titles)

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
