from __future__ import annotations

from pathlib import Path

from app.models import HTML_OUTPUT, PAGES_DIR, PUBLISH_OUTPUT, read_json, write_json


def run() -> Path:
    payload = read_json(HTML_OUTPUT)
    if not isinstance(payload, dict):
        raise ValueError("Expected object input from build_html")

    date = str(payload.get("date", ""))
    html = str(payload.get("html", ""))
    edition_filename = str(payload.get("edition_filename", "")) or f"{date}.html"

    if not date or not html:
        raise ValueError("Rendered payload missing required fields: date/html")

    PAGES_DIR.mkdir(parents=True, exist_ok=True)

    edition_path = PAGES_DIR / edition_filename
    edition_path.write_text(html, encoding="utf-8")

    latest_index = PAGES_DIR / "index.html"
    latest_index.write_text(
        "\n".join(
            [
                "<!doctype html>",
                "<html lang=\"sv\">",
                "<head>",
                "  <meta charset=\"utf-8\" />",
                "  <meta name=\"viewport\" content=\"width=device-width, initial-scale=1\" />",
                f"  <meta http-equiv=\"refresh\" content=\"0; url=./{edition_filename}\" />",
                "  <title>Kobo Morgonnyheter – senaste utgåvan</title>",
                "</head>",
                "<body>",
                f"  <p>Omdirigerar till senaste utgåvan: <a href=\"./{edition_filename}\">{edition_filename}</a></p>",
                "</body>",
                "</html>",
            ]
        ),
        encoding="utf-8",
    )

    result = {
        "date": date,
        "edition_path": str(edition_path.relative_to(PAGES_DIR.parent)),
        "latest_index_path": str(latest_index.relative_to(PAGES_DIR.parent)),
    }
    return write_json(PUBLISH_OUTPUT, result)


if __name__ == "__main__":
    output = run()
    print(f"Saved publish result to: {output}")
