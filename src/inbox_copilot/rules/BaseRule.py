from __future__ import annotations

import re
from abc import ABC, abstractmethod
from dataclasses import dataclass
from typing import Iterable, Sequence

# Adjust imports to your project
from inbox_copilot.rules.core import MailItem, Action


@dataclass(frozen=True)
class RuleMatch:
    """Result of a rule match. Can be extended later (e.g., confidence, extracted entities)."""
    matched: bool
    reason: str = ""


class BaseRule(ABC):
    """
    Base class for all rules.

    Design goals:
    - Provide consistent, reusable text matching helpers.
    - Keep rule logic readable and declarative.
    - Allow later extensions (priority, stop_processing, structured match info).
    """

    # Human-/debug-friendly unique name
    name: str = "base_rule"

    # Higher runs earlier (optional; your orchestrator may ignore this)
    priority: int = 0

    # If True and the rule matches, the orchestrator may stop evaluating remaining rules
    stop_processing: bool = False

    def __repr__(self) -> str:
        return f"{self.__class__.__name__}(name={self.name!r}, priority={self.priority})"

    # --- Helpers (None-safe, case-insensitive) ---

    def norm(self, s: str | None) -> str:
        """Normalize text for matching (None-safe, lowercased)."""
        return (s or "").lower()

    def header(self, mail: MailItem, name: str) -> str:
        """Get a header value normalized (lowercased)."""
        return self.norm(mail.headers.get(name))

    def subject(self, mail: MailItem) -> str:
        return self.header(mail, "Subject")

    def sender(self, mail: MailItem) -> str:
        return self.header(mail, "From")

    def snippet(self, mail: MailItem) -> str:
        return self.norm(mail.snippet)

    def contains_any(self, text: str | None, needles: Sequence[str]) -> bool:
        """True if any needle is a substring of text (case-insensitive)."""
        t = self.norm(text)
        return any(n.lower() in t for n in needles)

    def regex(self, text: str | None, pattern: str) -> bool:
        """Regex search on text (case-insensitive)."""
        return bool(re.search(pattern, self.norm(text), flags=re.IGNORECASE))

    def any_header_contains(self, mail: MailItem, header_names: Sequence[str], needles: Sequence[str]) -> bool:
        """True if any of the given headers contains any needle."""
        for hn in header_names:
            if self.contains_any(mail.headers.get(hn), needles):
                return True
        return False

    # --- Rule API ---

    @abstractmethod
    def match(self, mail: MailItem) -> tuple[bool, str]:
        """Return (matched, reason)."""
        raise NotImplementedError

    @abstractmethod
    def actions(self, mail: MailItem, reason: str) -> Iterable[Action]:
        """Yield actions to apply if match() is True."""
        raise NotImplementedError

    # Optional structured match (nice for debugging / logging later)
    def match_info(self, mail: MailItem) -> RuleMatch:
        """Default implementation: wrap match() in RuleMatch."""
        matched, reason = self.match(mail)
        return RuleMatch(matched=matched, reason=reason)
