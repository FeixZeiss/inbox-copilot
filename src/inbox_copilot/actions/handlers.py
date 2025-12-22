from __future__ import annotations

from abc import ABC, abstractmethod
from dataclasses import dataclass
from typing import Dict
from openai import OpenAI
import json

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
        label_ID = client.get_or_create_label_id(action.label_name)
        if not label_ID:
            raise ValueError(f"Failed to get or create label: {action.label_name}") 
        
        client.add_label(action.message_id, action.label_name)
        #client._update_label_color(label_ID, action.label_name)
        #print(f"[DEBUG] Ensured label exists: {action.label_name} (id={label_ID})")

        print(f"[LABEL] message_id={action.message_id} label={action.label_name} reason={action.reason}")


class ArchiveHandler(ActionHandler):
    def handle(self, client: GmailClient, action: Action) -> None:
        # You need a method like:
        # client.archive(message_id)
        client.archive(action.message_id)
        print(f"[ARCHIVE] message_id={action.message_id} reason={action.reason}")

class AnalyzeApplicationHandler(ActionHandler):
    client_ai = OpenAI()
    def handle(self, client: GmailClient, action: Action) -> None:
        # Fetch message content (for v1: subject/from/snippet is enough; later use full body)
        msg = client.get_message(action.message_id, fmt="metadata")
        headers = {h["name"]: h["value"] for h in msg["payload"].get("headers", [])}
        subject = headers.get("Subject", "")
        sender = headers.get("From", "")
        snippet = msg.get("snippet", "")

        # Structured Outputs (JSON Schema) so parsing is reliable
        schema = {
            "name": "application_summary",
            "strict": True,
            "schema": {
                "type": "object",
                "additionalProperties": False,
                "properties": {
                    "company": {"type": ["string", "null"]},
                    "role": {"type": ["string", "null"]},
                    "status": {
                        "type": "string",
                        "enum": ["confirmation", "interview", "rejection", "question", "offer", "other"]
                    },
                    "action_required": {"type": "boolean"},
                    "next_step": {"type": ["string", "null"]},
                    "deadlines": {"type": "array", "items": {"type": "string"}},
                    "important_links": {"type": "array", "items": {"type": "string"}},
                    "confidence": {"type": "number", "minimum": 0, "maximum": 1}
                },
                "required": ["status", "action_required", "deadlines", "important_links", "confidence"]
            }
        }

        resp = client_ai.responses.create(
            model="gpt-4.1-mini",  # good/cheap starting point; you can swap later
            input=[
                {
                    "role": "system",
                    "content": (
                        "You extract structured facts from job application emails. "
                        "Return ONLY JSON that matches the provided schema."
                    ),
                },
                {
                    "role": "user",
                    "content": (
                        f"Subject: {subject}\n"
                        f"From: {sender}\n"
                        f"Snippet: {snippet}\n"
                        "\nExtract the company, role, application status, next step, deadlines, and links."
                    ),
                },
            ],
            text={
                "format": {
                    "type": "json_schema",
                    "json_schema": schema
                }
            },
        )

        data = json.loads(resp.output_text)
        print("[APPLICATION ANALYSIS]", action.message_id)
        print(json.dumps(data, indent=2, ensure_ascii=False))

