from __future__ import annotations

from dataclasses import dataclass, field
from typing import Dict, List, Optional


@dataclass(frozen=True)
class NormalizedEmail:
    message_id: str
    subject: str
    from_email: str
    snippet: str
    body_text: str
    internal_date_ms: int
    headers: Dict[str, str] = field(default_factory=dict)
    label_ids: List[str] = field(default_factory=list)


@dataclass(frozen=True)
class EmailAnalysis:
    category: str
    suggested_labels: List[str]
    summary_bullets: List[str]
    todos: List[str]
    confidence: float
    notes: List[str]
    reason: Optional[str] = None
