from __future__ import annotations

import os
from datetime import datetime

import requests

INSTAPAPER_ADD_URL = "https://www.instapaper.com/api/add"


def send_url_to_instapaper(url: str, title: str) -> None:
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
    print(f"Instapaper response text: {response.text.strip()}")

    if response.status_code != 201:
        response_text = response.text.strip() or "No response body"
        raise RuntimeError(f"Instapaper API request failed ({response.status_code}): {response_text}")


def main() -> None:
    username = os.getenv("INSTAPAPER_USERNAME", "")
    password = os.getenv("INSTAPAPER_PASSWORD", "")
    base_url = os.getenv("ARTICLE_URL", "")

    missing_vars: list[str] = []
    if not username:
        missing_vars.append("INSTAPAPER_USERNAME")
    if not password:
        missing_vars.append("INSTAPAPER_PASSWORD")
    if not base_url:
        missing_vars.append("ARTICLE_URL")

    if missing_vars:
        raise SystemExit(f"Missing required environment variable(s): {', '.join(missing_vars)}")

    date_string = datetime.now().strftime("%Y-%m-%d")
    if not base_url.endswith("/"):
        base_url = f"{base_url}/"

    url = f"{base_url}{date_string}.html"
    title = f"Kobo Morgonnyheter {date_string}"

    send_url_to_instapaper(url=url, title=title)
    print(f"URL sent to Instapaper: {url}")


if __name__ == "__main__":
    main()
