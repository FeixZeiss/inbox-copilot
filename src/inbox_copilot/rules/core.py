from __future__ import annotations
from dataclasses import dataclass
from typing import Iterable, Protocol, Optional, Literal, Dict
from enum import Enum


@dataclass(frozen=True)
class MailItem:
    id: str
    thread_id: Optional[str]
    headers: Dict[str, str]  # e.g. {"From": "...", "Subject": "..."}
    snippet: str


class ActionType(str, Enum):
    PRINT = "print"
    ADD_LABEL = "add_label"
    ARCHIVE = "archive"
    REMOVE_LABEL = "remove_label"
    ANALYZE_APPLICATION = "analyze_application"


@dataclass(frozen=True)
class Action:
    type: ActionType
    message_id: str
    label_name: Optional[str] = None
    reason: str = ""


