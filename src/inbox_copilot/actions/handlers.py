from __future__ import annotations

from abc import ABC, abstractmethod
import re
from openai import OpenAI
import json
import base64

from inbox_copilot.rules.core import Action
from inbox_copilot.gmail.client import GmailClient
from inbox_copilot.config.paths import LOGS_DIR


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
        print(f"[ANALYZE] message_id={action.message_id} reason={action.reason}")
        # Fetch message content (for v1: subject/from/snippet is enough; later use full body)
        msg = client.get_message(action.message_id, fmt="full")
        payload = msg.get("payload", {})
        body_text = self.extract_body(payload)

        headers = {h["name"]: h["value"] for h in msg["payload"].get("headers", [])}
        subject = headers.get("Subject", "")
        sender = headers.get("From", "")
        snippet = msg.get("snippet", "")

        # Structured Outputs (JSON Schema) so parsing is reliable
        schema = {
            "type": "object",
            "additionalProperties": False,
            "properties": {
                "company": {"type": ["string", "null"]},
                "role": {"type": ["string", "null"]},
                "status": {
                    "type": "string",
                    "enum": ["confirmation", "interview", "rejection", "question", "offer", "other"],
                },
                "action_required": {"type": "boolean"},
                "next_step": {"type": ["string", "null"]},
                "deadlines": {"type": "array", "items": {"type": "string"}},
                "important_links": {"type": "array", "items": {"type": "string"}},
                "confidence": {"type": "number", "minimum": 0, "maximum": 1},
            },
            # IMPORTANT: must include EVERY key in properties
            "required": [
                "company",
                "role",
                "status",
                "action_required",
                "next_step",
                "deadlines",
                "important_links",
                "confidence",
            ],
        }


        resp = self.client_ai.responses.create(
            model="gpt-5.2",
            input=[
                {
                    "role": "system",
                    "content": (
                        "Return ONLY JSON matching the schema. "
                        "Extract facts explicitly from the email. "
                        "Include URLs in important_links. "
                        "Include response deadlines in deadlines. "
                        "Do not invent facts. "
                        "Convert dates to YYYY-MM-DD when possible."
                    ),
                },
                {
                    "role": "user",
                    "content": (
                        f"Subject: {subject}\n"
                        f"From: {sender}\n\n"
                        f"EMAIL BODY:\n{body_text}"
                    ),
                },
            ],
            text={
                "format": {
                    "type": "json_schema",
                    "name": "application_summary",
                    "schema": schema,
                }
            },
        )

        output_text = getattr(resp, "output_text", None)
        if not output_text:
            print(f"[ANALYZE_RESULT] message_id={action.message_id} json=<empty>")
            return

        try:
            analysis = json.loads(output_text)
        except json.JSONDecodeError:
            print(f"[ANALYZE_RESULT] message_id={action.message_id} json=<invalid>")
            return

        if analysis.get("status") != "interview":
            print(f"[ANALYZE_RESULT] message_id={action.message_id} json={output_text}")
            return

        output_dir = LOGS_DIR / "interviews"
        output_dir.mkdir(parents=True, exist_ok=True)
        file_stem = self._sanitize_filename(analysis.get("company"))
        output_path = output_dir / f"{file_stem}.json"

        if output_path.exists():
            output_path = output_dir / f"{file_stem}-{action.message_id}.json"

        output_path.write_text(
            json.dumps(analysis, indent=2, ensure_ascii=True),
            encoding="utf-8",
        )
        print(f"[ANALYZE_SAVED] message_id={action.message_id} path={output_path}")


    def extract_body(self, payload: dict) -> str:
        """
        Extract plain text body from Gmail message payload.
        Falls nur HTML vorhanden ist, wird HTML als Fallback zurückgegeben.
        """
        def decode(data: str) -> str:
            return base64.urlsafe_b64decode(data).decode("utf-8", errors="replace")

        # 1️⃣ Direkt im Body
        body = payload.get("body", {})
        if body.get("data"):
            return decode(body["data"])

        # 2️⃣ Multipart
        for part in payload.get("parts", []) or []:
            mime = part.get("mimeType", "")
            body = part.get("body", {})

            if mime == "text/plain" and body.get("data"):
                return decode(body["data"])

        # 3️⃣ HTML Fallback
        for part in payload.get("parts", []) or []:
            mime = part.get("mimeType", "")
            body = part.get("body", {})

            if mime == "text/html" and body.get("data"):
                return decode(body["data"])

        return ""

    def _sanitize_filename(self, company: str | None) -> str:
        if not company:
            return "unknown_company"
        cleaned = re.sub(r"[^A-Za-z0-9._-]+", "_", company.strip())
        return cleaned or "unknown_company"
