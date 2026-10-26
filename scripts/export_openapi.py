"""Writes the API's OpenAPI document to apps/web/openapi.json.

The frontend generates its TypeScript types from that file. CI runs this script and
fails if the committed file is out of date, so the backend and frontend cannot drift.
"""

import json
from pathlib import Path

from fleetpulse_backend.api.app import create_app

OUTPUT = Path(__file__).resolve().parents[1] / "apps" / "web" / "openapi.json"


def main() -> None:
    document = create_app(relay=False).openapi()
    content = json.dumps(document, indent=2, ensure_ascii=False) + "\n"
    OUTPUT.write_text(content, encoding="utf-8", newline="\n")  # LF on every OS
    print(f"wrote {OUTPUT}")


if __name__ == "__main__":
    main()
