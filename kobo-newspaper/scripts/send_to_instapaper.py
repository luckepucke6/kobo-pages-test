from __future__ import annotations

import os
from datetime import date

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
    article_url = os.getenv("ARTICLE_URL", "")

    missing_vars: list[str] = []
    if not username:
        missing_vars.append("INSTAPAPER_USERNAME")
    if not password:
        missing_vars.append("INSTAPAPER_PASSWORD")
    if not article_url:
        missing_vars.append("ARTICLE_URL")

    if missing_vars:
        raise SystemExit(f"Missing required environment variable(s): {', '.join(missing_vars)}")

    date_string = date.today().isoformat()
    if article_url.endswith(".html"):
        url = article_url
    else:
        base_url = article_url if article_url.endswith("/") else f"{article_url}/"
        url = f"{base_url}{date_string}.html"

    print(f"Final ARTICLE_URL: {url}")
    title = f"Kobo Morgonnyheter {date_string}"

    send_url_to_instapaper(url=url, title=title)
    print(f"URL sent to Instapaper: {url}")


if __name__ == "__main__":
    main()
