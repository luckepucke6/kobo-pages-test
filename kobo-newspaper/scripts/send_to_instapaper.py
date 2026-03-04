from __future__ import annotations

import os
from datetime import datetime

import requests

INSTAPAPER_ADD_URL = "https://www.instapaper.com/api/add"
DEFAULT_TITLE = f"Kobo Morgonnyheter {datetime.now().strftime('%Y-%m-%d')}"


def send_url_to_instapaper(url: str, title: str = DEFAULT_TITLE) -> None:
    username = os.getenv("INSTAPAPER_USERNAME")
    password = os.getenv("INSTAPAPER_PASSWORD")

    if not username or not password:
        raise RuntimeError("Missing INSTAPAPER_USERNAME or INSTAPAPER_PASSWORD environment variables.")

    payload = {
        "username": username,
        "password": password,
        "url": url,
        "title": title,
    }

    try:
        response = requests.post(
            INSTAPAPER_ADD_URL,
            data=payload,
            timeout=30,
        )
    except requests.RequestException as exc:
        raise RuntimeError(f"Failed to send request to Instapaper: {exc}") from exc

    print(f"Instapaper response status: {response.status_code}")

    if response.status_code != 201:
        response_text = response.text.strip() or "No response body"
        raise RuntimeError(f"Instapaper API request failed ({response.status_code}): {response_text}")


def main() -> None:
    url = os.getenv("ARTICLE_URL", "")
    title = os.getenv("ARTICLE_TITLE", DEFAULT_TITLE)

    if not url:
        raise SystemExit("Missing ARTICLE_URL environment variable.")

    send_url_to_instapaper(url=url, title=title)
    print(f"URL sent to Instapaper: {url}")


if __name__ == "__main__":
    main()
