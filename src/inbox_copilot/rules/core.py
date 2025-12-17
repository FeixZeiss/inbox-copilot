from __future__ import annotations
from dataclasses import dataclass
from typing import Iterable, Protocol, Optional, Literal, Dict


@dataclass(frozen=True)
class MailItem:
    id: str
    thread_id: Optional[str]
    headers: Dict[str, str]  # e.g. {"From": "...", "Subject": "..."}
    snippet: str


ActionType = Literal["add_label", "archive"]


@dataclass(frozen=True)
class Action:
    type: ActionType
    message_id: str
    label_name: Optional[str] = None
    reason: str = ""


class Rule(Protocol):
    name: str

    def match(self, mail: MailItem) -> bool: ...
    def actions(self, mail: MailItem) -> Iterable[Action]: ...
