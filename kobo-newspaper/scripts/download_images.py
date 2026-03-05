from __future__ import annotations

import hashlib
import json
import os
from pathlib import Path
from typing import Any
from urllib.parse import urljoin, urlparse, urlunparse

import requests

PROJECT_ROOT = Path(__file__).resolve().parents[1]
NEWSPAPER_JSON_PATH = PROJECT_ROOT / "pages" / "newspaper.json"
IMAGES_DIR = PROJECT_ROOT / "pages" / "assets" / "images"

MAX_IMAGE_BYTES = 600 * 1024
REQUEST_TIMEOUT = (10, 25)
USER_AGENT = (
    "Mozilla/5.0 (Macintosh; Intel Mac OS X 14_0) "
    "AppleWebKit/537.36 (KHTML, like Gecko) "
    "Chrome/122.0.0.0 Safari/537.36"
)


def _derive_folder_base_url(article_url: str) -> str:
    parsed = urlparse(article_url)
    clean_parsed = parsed._replace(query="", fragment="")
    path = clean_parsed.path or "/"

    if path.endswith(".html"):
        folder_path = path.rsplit("/", 1)[0] + "/"
    elif path.endswith("/"):
        folder_path = path
    else:
        folder_path = path + "/"

    folder_parsed = clean_parsed._replace(path=folder_path)
    folder_url = urlunparse(folder_parsed)
    if not folder_url.endswith("/"):
        folder_url += "/"
    return folder_url


def _guess_image_extension(image_url: str, content_type: str | None) -> str | None:
    url_path = urlparse(image_url).path.lower()
    if url_path.endswith(".jpg") or url_path.endswith(".jpeg"):
        return ".jpg"
    if url_path.endswith(".png"):
        return ".png"

    normalized_type = (content_type or "").split(";")[0].strip().lower()
    if normalized_type in {"image/jpeg", "image/jpg"}:
        return ".jpg"
    if normalized_type == "image/png":
        return ".png"

    return None


def _safe_filename(source_url: str, extension: str) -> str:
    digest = hashlib.sha1(source_url.encode("utf-8")).hexdigest()[:16]
    return f"img_{digest}{extension}"


def _download_image(image_url: str, target_dir: Path) -> str | None:
    headers = {"User-Agent": USER_AGENT}

    try:
        with requests.get(image_url, stream=True, timeout=REQUEST_TIMEOUT, headers=headers) as response:
            response.raise_for_status()

            content_length = response.headers.get("Content-Length")
            if content_length and content_length.isdigit() and int(content_length) > MAX_IMAGE_BYTES:
                return None

            extension = _guess_image_extension(image_url, response.headers.get("Content-Type"))
            if not extension:
                return None

            filename = _safe_filename(image_url, extension)
            destination = target_dir / filename

            total_bytes = 0
            with destination.open("wb") as output_file:
                for chunk in response.iter_content(chunk_size=8192):
                    if not chunk:
                        continue
                    total_bytes += len(chunk)
                    if total_bytes > MAX_IMAGE_BYTES:
                        output_file.close()
                        destination.unlink(missing_ok=True)
                        return None
                    output_file.write(chunk)

            return filename
    except requests.RequestException:
        return None


def _iter_stories(payload: dict[str, Any]):
    for section in payload.get("sections", []):
        stories = section.get("stories", [])
        if not isinstance(stories, list):
            continue
        for story in stories:
            if isinstance(story, dict):
                yield story


def process_newspaper_images() -> None:
    article_url = os.environ.get("ARTICLE_URL")
    if not article_url:
        raise RuntimeError("Missing required environment variable: ARTICLE_URL")

    if not NEWSPAPER_JSON_PATH.exists():
        raise FileNotFoundError(f"Missing input file: {NEWSPAPER_JSON_PATH}")

    payload = json.loads(NEWSPAPER_JSON_PATH.read_text(encoding="utf-8"))

    base_folder_url = _derive_folder_base_url(article_url)
    assets_base_url = urljoin(base_folder_url, "assets/images/")

    IMAGES_DIR.mkdir(parents=True, exist_ok=True)

    downloaded_count = 0
    skipped_count = 0

    for story in _iter_stories(payload):
        original_image_url = story.get("image_url")
        if not isinstance(original_image_url, str) or not original_image_url.strip():
            story["image_url"] = None
            continue

        source_url = original_image_url.strip()
        filename = _download_image(source_url, IMAGES_DIR)
        if filename:
            story["image_url"] = urljoin(assets_base_url, filename)
            downloaded_count += 1
        else:
            # Safest fallback: keep original URL if download fails.
            story["image_url"] = source_url
            skipped_count += 1

    NEWSPAPER_JSON_PATH.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")
    print(f"Downloaded images: {downloaded_count}")
    print(f"Skipped/kept original: {skipped_count}")


if __name__ == "__main__":
    process_newspaper_images()
