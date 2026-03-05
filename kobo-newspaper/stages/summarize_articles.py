from __future__ import annotations

import json
import os
import re
from difflib import SequenceMatcher
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

MIN_SUMMARY_SENTENCES = 4
MAX_SUMMARY_SENTENCES = 6
TARGET_SUMMARY_SENTENCES = 5

SUMMARY_KEYWORDS = [
    "geopolitics",
    "economy",
    "ai",
    "technology",
    "war",
    "election",
    "iran",
    "ukraine",
    "inflation",
    "market",
    "nvidia",
    "openai",
]


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
        dedupe_key = normalized.lower()
        if not normalized or dedupe_key in seen:
            continue
        seen.add(dedupe_key)
        unique.append(normalized)
    return " ".join(unique)


def _remove_duplicate_sentences(text: str) -> str:
    return remove_duplicate_sentences(text)


def _fallback_summary(text: str) -> list[str]:
    sentences = [clean_text(sentence) for sentence in _split_sentences(_remove_duplicate_sentences(text)) if clean_text(sentence)]
    if not sentences:
        return ["Ingen text tillgänglig för sammanfattning."] * MIN_SUMMARY_SENTENCES

    result = sentences[:MAX_SUMMARY_SENTENCES]
    if len(result) < MIN_SUMMARY_SENTENCES and result:
        result.extend([result[-1]] * (MIN_SUMMARY_SENTENCES - len(result)))
    return result[:MAX_SUMMARY_SENTENCES]


def _sentence_keyword_hits(sentence: str) -> int:
    normalized = clean_text(sentence).lower()
    normalized = re.sub(r"[^\w\s]", " ", normalized)
    normalized = " ".join(normalized.split())

    hits = 0
    for keyword in SUMMARY_KEYWORDS:
        pattern = r"\b" + re.escape(keyword.lower()) + r"\b"
        if re.search(pattern, normalized):
            hits += 1
    return hits


def _contains_name(sentence: str) -> bool:
    return re.search(r"\b[A-ZÅÄÖ][a-zåäö]+(?:\s+[A-ZÅÄÖ][a-zåäö]+){0,2}\b", sentence) is not None


def _is_near_duplicate(sentence: str, selected: list[str], threshold: float = 0.9) -> bool:
    candidate = clean_text(sentence).lower()
    if not candidate:
        return True

    for existing in selected:
        existing_norm = clean_text(existing).lower()
        if not existing_norm:
            continue
        if candidate == existing_norm:
            return True
        if SequenceMatcher(None, candidate, existing_norm).ratio() >= threshold:
            return True
    return False


def _score_sentence(sentence: str, index: int, total_sentences: int) -> float:
    position_score = 2.0
    if total_sentences > 1:
        position_score = 2.0 * (1.0 - (index / (total_sentences - 1)))

    number_bonus = 1.0 if re.search(r"\d", sentence) else 0.0
    name_bonus = 1.0 if _contains_name(sentence) else 0.0
    keyword_bonus = 0.7 * float(_sentence_keyword_hits(sentence))

    length_penalty = 0.0
    if len(clean_text(sentence)) < 40:
        length_penalty = 0.8

    return position_score + number_bonus + name_bonus + keyword_bonus - length_penalty


def _extractive_summary(text: str) -> list[str]:
    base_sentences = [clean_text(sentence) for sentence in _split_sentences(text) if clean_text(sentence)]
    if not base_sentences:
        return _fallback_summary(text)

    unique_sentences: list[str] = []
    for sentence in base_sentences:
        if _is_near_duplicate(sentence, unique_sentences, threshold=0.96):
            continue
        unique_sentences.append(sentence)

    if not unique_sentences:
        return _fallback_summary(text)

    scored: list[tuple[int, float]] = []
    total = len(unique_sentences)
    for index, sentence in enumerate(unique_sentences):
        score = _score_sentence(sentence, index=index, total_sentences=total)
        scored.append((index, score))

    target_count = min(
        MAX_SUMMARY_SENTENCES,
        max(MIN_SUMMARY_SENTENCES, min(TARGET_SUMMARY_SENTENCES, len(unique_sentences))),
    )

    ranked = sorted(scored, key=lambda item: (item[1], -item[0]), reverse=True)
    selected_indices: list[int] = []
    selected_sentences: list[str] = []

    for index, _ in ranked:
        sentence = unique_sentences[index]
        if _is_near_duplicate(sentence, selected_sentences):
            continue
        selected_indices.append(index)
        selected_sentences.append(sentence)
        if len(selected_indices) >= target_count:
            break

    if len(selected_indices) < MIN_SUMMARY_SENTENCES:
        for index, sentence in enumerate(unique_sentences):
            if index in selected_indices:
                continue
            if _is_near_duplicate(sentence, selected_sentences):
                continue
            selected_indices.append(index)
            selected_sentences.append(sentence)
            if len(selected_indices) >= MIN_SUMMARY_SENTENCES:
                break

    if not selected_indices:
        return _fallback_summary(text)

    selected_indices = sorted(selected_indices)
    summary = [unique_sentences[index] for index in selected_indices][:MAX_SUMMARY_SENTENCES]

    if len(summary) < MIN_SUMMARY_SENTENCES:
        return _fallback_summary(" ".join(unique_sentences))

    return summary


def _generate_context_with_openai(client: Any, title: str, text: str, summary: list[str]) -> dict[str, str]:
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
                    '  "why_it_matters": "1-2 meningar",\n'
                    '  "eli5": "1-2 meningar"\n'
                    "}\n\n"
                    f"Titel: {title}\n"
                    f"Sammanfattning: {' '.join(summary)}\n"
                    f"Text: {text}"
                ),
            },
        ],
    )

    payload = json.loads(response.choices[0].message.content or "{}")
    why = clean_text(payload.get("why_it_matters", "")) or "Det här påverkar nyhetsläget och vardagen på kort sikt."
    eli5 = clean_text(payload.get("eli5", "")) or "Kort sagt: detta är en viktig förändring och därför bör man följa utvecklingen."

    return {"why_it_matters": why, "eli5": eli5}


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

        summary = _extractive_summary(text)

        if client is None:
            why_it_matters = "Det här påverkar nyhetsläget och vardagen på kort sikt."
            eli5 = "Kort sagt: detta är en viktig förändring och därför bör man följa utvecklingen."
        else:
            try:
                context_payload = _generate_context_with_openai(client, title, text, summary)
                why_it_matters = context_payload["why_it_matters"]
                eli5 = context_payload["eli5"]
            except Exception:
                why_it_matters = "Det här påverkar nyhetsläget och vardagen på kort sikt."
                eli5 = "Kort sagt: detta är en viktig förändring och därför bör man följa utvecklingen."

        article["summary"] = summary
        article["why_it_matters"] = why_it_matters
        article["eli5"] = eli5
        article["text"] = text
        output.append(article)

    return write_json(SUMMARIZED_OUTPUT, output)


if __name__ == "__main__":
    output = run()
    print(f"Saved summarized articles to: {output}")
