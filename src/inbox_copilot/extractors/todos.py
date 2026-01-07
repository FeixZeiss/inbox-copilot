from __future__ import annotations

import re
from typing import List


def extract_todos(subject: str, body_text: str) -> List[str]:
    """
    Heuristic todo extraction.
    Keep it simple and deterministic to avoid false positives.
    """
    text = f"{subject}\n{body_text}"
    todos: List[str] = []

    for line in text.splitlines():
        line = line.strip()
        if not line:
            continue

        if re.match(r"^(todo:|to do:)", line, flags=re.IGNORECASE):
            todos.append(line)
            continue

        if re.match(r"^[-*]\\s*\\[ \\]", line):
            todos.append(line)
            continue

        if re.match(r"^(please|bitte)\\b", line, flags=re.IGNORECASE):
            todos.append(line)
            continue

    return todos
