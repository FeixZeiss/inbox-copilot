from __future__ import annotations

from abc import ABC, abstractmethod
from dataclasses import dataclass
from typing import Dict

from inbox_copilot.rules.core import Action, ActionType
from inbox_copilot.gmail.client import GmailClient


class ActionHandler(ABC):
    @abstractmethod
    def handle(self, client: GmailClient, action: Action) -> None:
        """Execute one action."""
        ...


class PrintHandler(ActionHandler):
    def handle(self, client: GmailClient, action: Action) -> None:
        # English output messages (per your preference)
        print(f"[PRINT] message_id={action.message_id} reason={action.reason}")


class AddLabelHandler(ActionHandler):
    def handle(self, client: GmailClient, action: Action) -> None:
        if not action.label_name:
            raise ValueError("ADD_LABEL requires label_name")

        # You need a method like this on your GmailClient:
        # client.add_label(message_id, label_name)
        client.add_label(action.message_id, action.label_name)

        print(f"[LABEL] message_id={action.message_id} label={action.label_name} reason={action.reason}")


class ArchiveHandler(ActionHandler):
    def handle(self, client: GmailClient, action: Action) -> None:
        # You need a method like:
        # client.archive(message_id)
        client.archive(action.message_id)
        print(f"[ARCHIVE] message_id={action.message_id} reason={action.reason}")
