from __future__ import annotations

from abc import ABC, abstractmethod
import re
from openai import OpenAI
import json

from inbox_copilot.rules.core import Action
from inbox_copilot.gmail.client import GmailClient
from inbox_copilot.config.paths import LOGS_DIR, SECRETS_DIR
from inbox_copilot.parsing.parser import extract_body_from_payload


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

        # Ensure the label exists before applying it to the message.
        label_id = client.get_or_create_label_id(action.label_name)
        if not label_id:
            raise ValueError(f"Failed to get or create label: {action.label_name}") 
        
        client.add_label(action.message_id, action.label_name)
        print(f"[LABEL] message_id={action.message_id} label={action.label_name} reason={action.reason}")


class ArchiveHandler(ActionHandler):
    def handle(self, client: GmailClient, action: Action) -> None:
        client.archive(action.message_id)
        print(f"[ARCHIVE] message_id={action.message_id} reason={action.reason}")

class AnalyzeApplicationHandler(ActionHandler):
    def __init__(self) -> None:
        api_key = self._load_openai_api_key()
        self.openai_client = OpenAI(api_key=api_key) if api_key else OpenAI()

    @staticmethod
    def _load_openai_api_key() -> str | None:
        token_path = SECRETS_DIR / "openai_token.txt"
        if token_path.exists():
            try:
                token = token_path.read_text(encoding="utf-8").strip()
            except UnicodeDecodeError:
                return None
            return token or None

        json_path = SECRETS_DIR / "openai_token.json"
        if json_path.exists():
            try:
                payload = json.loads(json_path.read_text(encoding="utf-8"))
            except (UnicodeDecodeError, json.JSONDecodeError):
                return None
            token = payload.get("api_key") or payload.get("token") or payload.get("openai_api_key")
            return token or None

        return None
    
    def handle(self, client: GmailClient, action: Action) -> None:
        print(f"[ANALYZE] message_id={action.message_id} reason={action.reason}")
        # Fetch full body so extraction can consider the whole email.
        msg = client.get_message(action.message_id, fmt="full")
        payload = msg.get("payload", {})
        body_text = extract_body_from_payload(payload)

        headers = {h["name"]: h["value"] for h in msg["payload"].get("headers", [])}
        subject = headers.get("Subject", "")
        sender = headers.get("From", "")
        snippet = msg.get("snippet", "")

        # Use Structured Outputs so parsing is deterministic.
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


        # Keep the prompt strict: we only accept JSON for automation.
        resp = self.openai_client.responses.create(
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

        # Keep original mail context so reply drafts can use full source text.
        analysis["source_subject"] = subject
        analysis["source_from"] = sender
        analysis["source_snippet"] = snippet
        analysis["source_body_text"] = body_text
        analysis["source_message_id"] = action.message_id

        # Only persist interview-related results for now.
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
            json.dumps(analysis, indent=2, ensure_ascii=False),
            encoding="utf-8",
        )
        print(f"[ANALYZE_SAVED] message_id={action.message_id} path={output_path}")


    def _sanitize_filename(self, company: str | None) -> str:
        if not company:
            return "unknown_company"
        # Restrict filenames to a safe subset.
        cleaned = re.sub(r"[^A-Za-z0-9._-]+", "_", company.strip())
        return cleaned or "unknown_company"
