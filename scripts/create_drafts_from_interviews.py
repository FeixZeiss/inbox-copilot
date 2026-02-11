from __future__ import annotations

import argparse
import json
from datetime import datetime, timezone
from email.message import EmailMessage
from pathlib import Path

from dotenv import load_dotenv
from openai import OpenAI

from inbox_copilot.config.paths import LOGS_DIR, SECRETS_DIR
from inbox_copilot.gmail.client import GmailClient, GmailClientConfig


def load_gmail_config() -> GmailClientConfig:
    cred = SECRETS_DIR / "credentials.json"
    if not cred.exists():
        raise RuntimeError(
            f"Missing Gmail credentials at {cred}. "
            "Did you configure INBOX_COPILOT_SECRETS_DIR?"
        )

    token = SECRETS_DIR / "gmail_token.json"

    cfg = GmailClientConfig(
        credentials_path=cred,
        token_path=token,
        user_id="me",
    )

    if not cfg.credentials_path.exists():
        raise FileNotFoundError(f"Missing credentials: {cfg.credentials_path}")

    return cfg


def build_subject(company: str | None, role: str | None) -> str:
    company = company or "Interview"
    if role:
        return f"Interview: {company} - {role}"
    return f"Interview: {company}"


def build_body(data: dict) -> str:
    role = data.get("role")
    action_required = bool(data.get("action_required"))
    next_step = data.get("next_step")
    deadlines = data.get("deadlines") or []
    links = data.get("important_links") or []

    lines: list[str] = []
    lines.append("Hello [Name],")
    lines.append("")
    if role:
        lines.append(
            f"Thank you for the interview invitation for the {role} position."
        )
    else:
        lines.append("Thank you for the interview invitation.")
    if action_required:
        lines.append("I am happy to confirm the appointment.")
    else:
        lines.append("I am looking forward to the conversation.")
    lines.append("")
    lines.append("Best regards,")
    lines.append("[Your Name]")

    notes: list[str] = []
    if next_step:
        notes.append(f"- Next step: {next_step}")
    if deadlines:
        notes.append("- Deadlines/dates: " + ", ".join(str(d) for d in deadlines))
    if links:
        notes.append("- Important links: " + ", ".join(str(link) for link in links))

    if notes:
        lines.append("")
        lines.append("---")
        lines.append(
            "Notes (please remove before sending):"
        )
        lines.extend(notes)

    return "\n".join(lines)


def generate_draft_with_openai(
    data: dict,
    model: str,
    language: str,
    tone: str,
) -> tuple[str, str]:
    client = OpenAI()

    schema = {
        "type": "object",
        "additionalProperties": False,
        "properties": {
            "subject": {"type": "string"},
            "body": {"type": "string"},
        },
        "required": ["subject", "body"],
    }

    instructions = (
        "Create a concise, high-quality interview reply draft. "
        "Use plain text only. "
        "Keep placeholders [Name] and [Your Name] for personalization. "
        "Do not invent facts beyond the provided data."
    )

    resp = client.responses.create(
        model=model,
        input=[
            {
                "role": "system",
                "content": instructions,
            },
            {
                "role": "user",
                "content": (
                    f"Language: {language}\n"
                    f"Tone: {tone}\n"
                    f"Data: {json.dumps(data, ensure_ascii=True)}"
                ),
            },
        ],
        text={
            "format": {
                "type": "json_schema",
                "name": "draft",
                "schema": schema,
            }
        },
    )

    output_text = getattr(resp, "output_text", None)
    if not output_text:
        raise RuntimeError("OpenAI response was empty.")

    try:
        payload = json.loads(output_text)
    except json.JSONDecodeError as exc:
        raise RuntimeError("OpenAI response was not valid JSON.") from exc

    subject = str(payload.get("subject") or "").strip()
    body = str(payload.get("body") or "").strip()
    if not subject or not body:
        raise RuntimeError("OpenAI response missing subject or body.")

    return subject, body


def create_draft_message(
    from_email: str,
    subject: str,
    body: str,
    to_email: str | None,
) -> EmailMessage:
    msg = EmailMessage()
    msg["From"] = from_email
    if to_email:
        msg["To"] = to_email
    msg["Subject"] = subject
    msg.set_content(body)
    return msg


def draft_marker_path(json_path: Path) -> Path:
    return json_path.with_suffix(".draft.json")


def process_file(
    client: GmailClient,
    profile_email: str,
    json_path: Path,
    to_email: str | None,
    skip_existing: bool,
    dry_run: bool,
    use_openai: bool,
    model: str,
    language: str,
    tone: str,
) -> None:
    marker_path = draft_marker_path(json_path)
    if skip_existing and marker_path.exists():
        print(f"[SKIP] {json_path.name} draft marker exists")
        return

    data = json.loads(json_path.read_text(encoding="utf-8"))
    if data.get("status") != "interview":
        print(f"[SKIP] {json_path.name} status={data.get('status')}")
        return
    if not bool(data.get("action_required")):
        print(f"[SKIP] {json_path.name} action_required=False")
        return

    if use_openai:
        subject, body = generate_draft_with_openai(
            data=data,
            model=model,
            language=language,
            tone=tone,
        )
    else:
        subject = build_subject(data.get("company"), data.get("role"))
        body = build_body(data)
    msg = create_draft_message(profile_email, subject, body, to_email)

    if dry_run:
        print(f"[DRY_RUN] {json_path.name} -> subject={subject!r}")
        return

    resp = client.create_draft(msg)
    marker_payload = {
        "draft_id": resp.get("id"),
        "message_id": resp.get("message", {}).get("id"),
        "source_file": json_path.name,
        "created_at": datetime.now(timezone.utc).isoformat(),
    }
    marker_path.write_text(
        json.dumps(marker_payload, indent=2, ensure_ascii=True),
        encoding="utf-8",
    )
    print(f"[DRAFT] {json_path.name} -> draft_id={marker_payload['draft_id']}")


def main() -> None:
    load_dotenv()

    parser = argparse.ArgumentParser(
        description="Create Gmail drafts from interview JSON files."
    )
    parser.add_argument(
        "--dir",
        dest="interviews_dir",
        type=Path,
        default=LOGS_DIR / "interviews",
        help="Directory containing interview JSON files.",
    )
    parser.add_argument(
        "--default-to",
        dest="default_to",
        default="",
        help="Optional default recipient email address.",
    )
    parser.add_argument(
        "--no-skip-existing",
        dest="skip_existing",
        action="store_false",
        help="Create drafts even if a .draft.json marker exists.",
    )
    parser.add_argument(
        "--dry-run",
        dest="dry_run",
        action="store_true",
        help="Print what would be created without calling Gmail.",
    )
    parser.add_argument(
        "--use-openai",
        dest="use_openai",
        action="store_true",
        help="Use OpenAI to generate subject and body.",
    )
    parser.add_argument(
        "--model",
        dest="model",
        default="gpt-5.2",
        help="OpenAI model to use when --use-openai is set.",
    )
    parser.add_argument(
        "--language",
        dest="language",
        default="en",
        help="Language for the generated draft.",
    )
    parser.add_argument(
        "--tone",
        dest="tone",
        default="formal, friendly, concise",
        help="Tone for the generated draft.",
    )
    args = parser.parse_args()

    interviews_dir = args.interviews_dir
    if not interviews_dir.exists():
        raise FileNotFoundError(f"Missing directory: {interviews_dir}")

    json_files = sorted(p for p in interviews_dir.iterdir() if p.suffix == ".json")
    if not json_files:
        print(f"[INFO] No JSON files in {interviews_dir}")
        return

    cfg = load_gmail_config()
    client = GmailClient(cfg)
    client.connect()

    profile_email = client.get_profile().get("emailAddress", "")
    if not profile_email:
        raise RuntimeError("Could not resolve authenticated email address.")

    to_email = args.default_to.strip() or None

    for json_path in json_files:
        if json_path.name.endswith(".draft.json"):
            continue
        process_file(
            client=client,
            profile_email=profile_email,
            json_path=json_path,
            to_email=to_email,
            skip_existing=args.skip_existing,
            dry_run=args.dry_run,
            use_openai=args.use_openai,
            model=args.model,
            language=args.language,
            tone=args.tone,
        )


if __name__ == "__main__":
    main()
