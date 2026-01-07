from __future__ import annotations

import re
from typing import List


def summarize(snippet: str, body_text: str, max_bullets: int = 3) -> List[str]:
    """
    Very lightweight summarizer: prefer snippet, then first sentences.
    """
    bullets: List[str] = []

    if snippet:
        cleaned = _clean_text(snippet)
        if cleaned:
            bullets.append(cleaned)

    if len(bullets) >= max_bullets:
        return bullets[:max_bullets]

    text = _clean_text(body_text)
    if not text:
        return bullets

    sentences = _split_sentences(text)
    for sent in sentences:
        if len(bullets) >= max_bullets:
            break
        if sent and sent not in bullets:
            bullets.append(sent)

    return bullets[:max_bullets]


def _split_sentences(text: str) -> List[str]:
    parts = re.split(r"[.!?]\\s+", text)
    return [p.strip() for p in parts if p.strip()]


def _clean_text(text: str) -> str:
    return re.sub(r"\\s+", " ", text).strip()
