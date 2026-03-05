from __future__ import annotations

import json
import os
import re
from pathlib import Path
from typing import Any

try:
    from openai import OpenAI
except Exception:
    OpenAI = None  # type: ignore

PROJECT_ROOT = Path(__file__).resolve().parents[1]
INPUT_PATH = PROJECT_ROOT / "pages" / "clustered_articles.json"
OUTPUT_PATH = PROJECT_ROOT / "pages" / "summarized_articles.json"

SYSTEM_PROMPT = (
    "Du är en svensk nyhetsredaktör. "
    "Skriv sakligt, tydligt och kortfattat. "
    "Undvik överdrifter och håll texten lättläst."
)


def _clean_text(raw: str) -> str:
    return " ".join((raw or "").replace("\n", " ").split())


def _split_sentences(text: str) -> list[str]:
    cleaned = _clean_text(text)
    if not cleaned:
        return []
    parts = re.split(r"(?<=[.!?])\s+", cleaned)
    return [p.strip() for p in parts if p.strip()]


def remove_duplicate_sentences(text: str) -> str:
    sentences = _split_sentences(text)
    if not sentences:
        return _clean_text(text)

    seen: set[str] = set()
    unique_sentences: list[str] = []

    for sentence in sentences:
        normalized = sentence.lower().strip()
        if normalized in seen:
            continue
        seen.add(normalized)
        unique_sentences.append(sentence)

    return " ".join(unique_sentences)


def _fallback_summary(text: str, min_sentences: int = 5, max_sentences: int = 8) -> list[str]:
    sentences = _split_sentences(remove_duplicate_sentences(text))
    if not sentences:
        return ["Ingen text tillgänglig för sammanfattning."] * min_sentences

    selected = sentences[:max_sentences]
    if len(selected) < min_sentences:
        selected.extend([selected[-1]] * (min_sentences - len(selected)))
    return selected


def _summarize_with_openai(client: Any, title: str, text: str) -> dict[str, Any]:
    response = client.chat.completions.create(
        model="gpt-4o-mini",
        response_format={"type": "json_object"},
        messages=[
            {"role": "system", "content": SYSTEM_PROMPT},
            {
                "role": "user",
                "content": (
                    "Sammanfatta artikeln på svenska. Returnera ENDAST JSON med format:\n"
                    "{\n"
                    '  "summary": ["5–8 meningar"],\n'
                    '  "why_it_matters": "1–2 meningar",\n'
                    '  "eli5": "1–2 meningar"\n'
                    "}\n\n"
                    f"Titel: {title}\n"
                    f"Text: {text}"
                ),
            },
        ],
    )

    payload = json.loads(response.choices[0].message.content or "{}")
    summary_raw = payload.get("summary", [])

    if isinstance(summary_raw, str):
        summary = [s.strip() for s in _split_sentences(remove_duplicate_sentences(summary_raw)) if s.strip()]
    elif isinstance(summary_raw, list):
        summary = []
        for item in summary_raw:
            cleaned_item = remove_duplicate_sentences(_clean_text(str(item)))
            if cleaned_item:
                summary.append(cleaned_item)
    else:
        summary = []

    if not summary:
        summary = _fallback_summary(text)

    summary = summary[:8]
    if len(summary) < 5:
        summary.extend([summary[-1]] * (5 - len(summary)))

    why_it_matters = _clean_text(payload.get("why_it_matters", ""))
    eli5 = _clean_text(payload.get("eli5", ""))

    if not why_it_matters:
        why_it_matters = "Det här hjälper läsaren att förstå varför nyheten spelar roll idag."
    if not eli5:
        eli5 = "Kort sagt handlar nyheten om en viktig förändring och vad den kan leda till."

    return {
        "summary": summary,
        "why_it_matters": why_it_matters,
        "eli5": eli5,
    }


def _summarize_article(client: Any, title: str, text: str) -> dict[str, Any]:
    if client is None:
        summary = _fallback_summary(text)
        return {
            "summary": summary,
            "why_it_matters": "Det här hjälper läsaren att förstå varför nyheten spelar roll idag.",
            "eli5": "Kort sagt handlar nyheten om en viktig förändring och vad den kan leda till.",
        }

    try:
        return _summarize_with_openai(client, title, text)
    except Exception:
        summary = _fallback_summary(text)
        return {
            "summary": summary,
            "why_it_matters": "Det här hjälper läsaren att förstå varför nyheten spelar roll idag.",
            "eli5": "Kort sagt handlar nyheten om en viktig förändring och vad den kan leda till.",
        }


def summarize_articles() -> Path:
    if not INPUT_PATH.exists():
        raise FileNotFoundError(f"Input file not found: {INPUT_PATH}")

    input_articles = json.loads(INPUT_PATH.read_text(encoding="utf-8"))
    if not isinstance(input_articles, list):
        raise ValueError("Input file must contain a JSON array of articles")

    api_key = os.environ.get("OPENAI_API_KEY")
    client = OpenAI(api_key=api_key) if (OpenAI is not None and api_key) else None

    output: list[dict[str, Any]] = []
    for article in input_articles:
        if not isinstance(article, dict):
            continue

        title = _clean_text(str(article.get("title", "")))
        text = remove_duplicate_sentences(_clean_text(str(article.get("text", ""))))
        url = _clean_text(str(article.get("url", "")))
        source = _clean_text(str(article.get("source", "")))

        if not title or not url:
            continue

        summarized = _summarize_article(client, title, text)

        output.append(
            {
                "title": title,
                "summary": summarized["summary"],
                "why_it_matters": summarized["why_it_matters"],
                "eli5": summarized["eli5"],
                "url": url,
                "source_url": _clean_text(str(article.get("source_url", url))),
                "source": source,
                "source_domain": _clean_text(str(article.get("source_domain", ""))),
                "image_url": _clean_text(str(article.get("image_url", ""))),
                "published": _clean_text(str(article.get("published", ""))),
                "text": text,
            }
        )

    OUTPUT_PATH.parent.mkdir(parents=True, exist_ok=True)
    OUTPUT_PATH.write_text(json.dumps(output, ensure_ascii=False, indent=2), encoding="utf-8")
    return OUTPUT_PATH


if __name__ == "__main__":
    output_path = summarize_articles()
    print(f"Saved summarized articles to: {output_path}")
