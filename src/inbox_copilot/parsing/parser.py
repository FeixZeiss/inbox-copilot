from __future__ import annotations

import base64
from typing import Optional


def extract_body_from_payload(payload: dict) -> str:
    """
    Extract plain text body from Gmail message payload.
    Falls back to HTML if plain text is unavailable.
    """
    def decode(data: str) -> str:
        return base64.urlsafe_b64decode(data).decode("utf-8", errors="replace")

    def find_part(part: dict, mime_type: str) -> Optional[str]:
        # Depth-first search through multipart payloads.
        if part.get("mimeType") == mime_type and part.get("body", {}).get("data"):
            return decode(part["body"]["data"])
        for child in part.get("parts", []) or []:
            found = find_part(child, mime_type)
            if found:
                return found
        return None

    if payload.get("body", {}).get("data"):
        return decode(payload["body"]["data"])

    text = find_part(payload, "text/plain")
    if text:
        return text

    html = find_part(payload, "text/html")
    if html:
        return html

    return ""
