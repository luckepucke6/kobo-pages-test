from __future__ import annotations

import json
import os
import re
from pathlib import Path
from typing import Any

from app.models import CLUSTERED_OUTPUT, SUMMARIZED_OUTPUT, clean_text, read_json, write_json

try:
    from openai import OpenAI
except Exception:
    OpenAI = None  # type: ignore

SYSTEM_PROMPT = (
    "Du är en svensk nyhetsredaktör. "
    "Skriv sakligt, tydligt och kortfattat utan upprepningar. "
    "Sammanfattningar ska vara pedagogiska för e-läsare."
)


def _split_sentences(text: str) -> list[str]:
    cleaned = clean_text(text)
    if not cleaned:
        return []
    return [part.strip() for part in re.split(r"(?<=[.!?])\s+", cleaned) if part.strip()]


def remove_duplicate_sentences(text: str) -> str:
    seen: set[str] = set()
    unique: list[str] = []
    for sentence in _split_sentences(text):
        normalized = sentence.strip()
        if not normalized or normalized in seen:
            continue
        seen.add(normalized)
        unique.append(normalized)
    return " ".join(unique)


def _remove_duplicate_sentences(text: str) -> str:
    return remove_duplicate_sentences(text)


def _fallback_summary(text: str, min_sentences: int = 5, max_sentences: int = 8) -> list[str]:
    sentences = _split_sentences(_remove_duplicate_sentences(text))
    if not sentences:
        return ["Ingen text tillgänglig för sammanfattning."] * min_sentences
    result = sentences[:max_sentences]
    if len(result) < min_sentences:
        result.extend([result[-1]] * (min_sentences - len(result)))
    return result


def _normalize_summary_sentences(summary_sentences: list[str], min_sentences: int = 5, max_sentences: int = 8) -> list[str]:
    unique: list[str] = []
    seen: set[str] = set()

    for sentence in summary_sentences:
        cleaned = clean_text(sentence)
        if not cleaned:
            continue
        for split_sentence in _split_sentences(cleaned):
            normalized = split_sentence.lower().strip()
            if normalized in seen:
                continue
            seen.add(normalized)
            unique.append(split_sentence)

    if not unique:
        return []

    result = unique[:max_sentences]
    if len(result) < min_sentences:
        result.extend([result[-1]] * (min_sentences - len(result)))
    return result


def _summarize_with_openai(client: Any, title: str, text: str) -> dict[str, Any]:
    response = client.chat.completions.create(
        model="gpt-4o-mini",
        response_format={"type": "json_object"},
        messages=[
            {"role": "system", "content": SYSTEM_PROMPT},
            {
                "role": "user",
                "content": (
                    "Returnera endast JSON med schema:\n"
                    "{\n"
                    '  "summary": ["5-8 meningar"],\n'
                    '  "why_it_matters": "1-2 meningar",\n'
                    '  "eli5": "1-2 meningar"\n'
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
        summary = _normalize_summary_sentences(_split_sentences(_remove_duplicate_sentences(summary_raw)))
    elif isinstance(summary_raw, list):
        summary = _normalize_summary_sentences([str(item) for item in summary_raw])
    else:
        summary = []

    if not summary:
        summary = _fallback_summary(text)

    summary = _normalize_summary_sentences(summary)
    if not summary:
        summary = _fallback_summary(text)

    why = clean_text(payload.get("why_it_matters", "")) or "Det här påverkar nyhetsläget och vardagen på kort sikt."
    eli5 = clean_text(payload.get("eli5", "")) or "Kort sagt: detta är en viktig förändring och därför bör man följa utvecklingen."

    return {
        "summary": summary,
        "why_it_matters": why,
        "eli5": eli5,
    }


def run() -> Path:
    payload = read_json(CLUSTERED_OUTPUT, default=[])
    if not isinstance(payload, list):
        raise ValueError("Expected list input from cluster_articles")

    api_key = os.environ.get("OPENAI_API_KEY")
    client = OpenAI(api_key=api_key) if (OpenAI is not None and api_key) else None

    output: list[dict[str, Any]] = []
    for raw_article in payload:
        if not isinstance(raw_article, dict):
            continue

        article = dict(raw_article)
        title = clean_text(article.get("title", ""))
        text = _remove_duplicate_sentences(clean_text(article.get("text", "")))

        if not title or not article.get("url"):
            continue

        if client is None:
            summarized = {
                "summary": _fallback_summary(text),
                "why_it_matters": "Det här påverkar nyhetsläget och vardagen på kort sikt.",
                "eli5": "Kort sagt: detta är en viktig förändring och därför bör man följa utvecklingen.",
            }
        else:
            try:
                summarized = _summarize_with_openai(client, title, text)
            except Exception:
                summarized = {
                    "summary": _fallback_summary(text),
                    "why_it_matters": "Det här påverkar nyhetsläget och vardagen på kort sikt.",
                    "eli5": "Kort sagt: detta är en viktig förändring och därför bör man följa utvecklingen.",
                }

        summary_text = " ".join(clean_text(item) for item in summarized.get("summary", []) if clean_text(item))
        article["summary"] = _split_sentences(remove_duplicate_sentences(summary_text))
        article["why_it_matters"] = summarized["why_it_matters"]
        article["eli5"] = summarized["eli5"]
        article["text"] = text
        output.append(article)

    return write_json(SUMMARIZED_OUTPUT, output)


if __name__ == "__main__":
    output = run()
    print(f"Saved summarized articles to: {output}")
