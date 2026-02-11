from __future__ import annotations

import argparse
import json
import re
from datetime import datetime, timezone
from email.message import EmailMessage
from pathlib import Path

from dotenv import load_dotenv
from openai import OpenAI

from inbox_copilot.config.paths import LOGS_DIR, SECRETS_DIR
from inbox_copilot.gmail.client import GmailClient, GmailClientConfig
from inbox_copilot.parsing.parser import extract_body_from_payload

SIGNATURE = "Mit freundlichen Grüßen\nFelix Zeiß"


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


def _as_reply_subject(subject: str) -> str:
    cleaned = subject.strip()
    if not cleaned:
        return "Re: Einladung zum Vorstellungsgespräch"
    match = re.match(r"^(re|aw|sv)\s*:\s*(.*)$", cleaned, flags=re.IGNORECASE)
    if match:
        tail = match.group(2).strip()
        if not tail:
            return "Re: Einladung zum Vorstellungsgespräch"
        return f"Re: {tail}"
    return f"Re: {cleaned}"


def build_subject(data: dict, generated_subject: str | None = None) -> str:
    original_subject = str(data.get("source_subject") or data.get("subject") or "").strip()
    if original_subject:
        return _as_reply_subject(original_subject)
    if generated_subject:
        return _as_reply_subject(generated_subject)
    company = data.get("company") or ""
    role = data.get("role")
    if role:
        return _as_reply_subject(f"Einladung zum Vorstellungsgespräch – {role}")
    if company:
        return _as_reply_subject(f"Einladung zum Vorstellungsgespräch bei {company}")
    return _as_reply_subject("Einladung zum Vorstellungsgespräch")


def extract_contact_name(data: dict) -> str | None:
    from_header = str(data.get("source_from") or "").strip()
    if not from_header:
        return None
    display = from_header.split("<", 1)[0].strip().strip('"').strip()
    if not display or "@" in display:
        return None
    display = re.sub(r"\s+", " ", display)
    display = re.sub(
        r"^(frau|herr|mr\.?|ms\.?|dr\.?|prof\.?)\s+",
        "",
        display,
        flags=re.IGNORECASE,
    )
    return display or None


def personalize_salutation(body: str, data: dict) -> str:
    name = extract_contact_name(data)
    if not name:
        return body
    lines = body.splitlines()
    if not lines:
        return body
    for idx, line in enumerate(lines):
        stripped = line.strip()
        if not stripped:
            continue
        if "[Name]" in line:
            lines[idx] = line.replace("[Name]", name)
            break
        if stripped in {"Hallo,", "Guten Tag,", "Sehr geehrte Damen und Herren,"}:
            lines[idx] = f"Hallo {name},"
            break
        if stripped.startswith("Hallo ") and stripped.endswith(","):
            break
        lines.insert(idx, f"Hallo {name},")
        break
    return "\n".join(lines)


def hydrate_source_context(client: GmailClient, data: dict) -> dict:
    if data.get("source_body_text"):
        return data
    message_id = str(data.get("source_message_id") or "").strip()
    if not message_id:
        return data
    try:
        msg = client.get_message(message_id, fmt="full")
    except Exception:
        return data

    payload = msg.get("payload", {})
    headers = {h.get("name"): h.get("value") for h in payload.get("headers", [])}
    enriched = dict(data)
    enriched.setdefault("source_subject", headers.get("Subject", ""))
    enriched.setdefault("source_from", headers.get("From", ""))
    enriched.setdefault("source_snippet", msg.get("snippet", ""))
    enriched.setdefault("source_body_text", extract_body_from_payload(payload))
    return enriched


def with_signature(body: str) -> str:
    text = body.strip()
    if text.endswith(SIGNATURE):
        return text
    return f"{text}\n\n{SIGNATURE}"


def build_body(data: dict) -> str:
    contact_name = extract_contact_name(data)
    role = data.get("role")
    action_required = bool(data.get("action_required"))

    lines: list[str] = []
    lines.append(f"Hallo {contact_name}," if contact_name else "Hallo,")
    lines.append("")
    if role:
        lines.append(
            f"vielen Dank für die Einladung zum Vorstellungsgespräch für die Position {role}."
        )
    else:
        lines.append("vielen Dank für die Einladung zum Vorstellungsgespräch.")
    if action_required:
        lines.append("Ich bestätige den Termin gerne.")
    else:
        lines.append("Ich freue mich auf das Gespräch.")

    return with_signature("\n".join(lines))


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
        "Erstelle eine kurze, hochwertige Antwort auf eine Interview-Einladung. "
        "Schreibe ausschließlich auf Deutsch und im Klartext. "
        "Sprich den Ansprechpartner nach Möglichkeit direkt mit Namen an. "
        "Wenn kein Name erkennbar ist, beginne mit 'Hallo,'. "
        "Der Text MUSS exakt mit diesen zwei Zeilen enden: "
        "'Mit freundlichen Grüßen' und 'Felix Zeiß'. "
        "Erfinde keine Fakten, die nicht im Originaltext stehen."
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
                    f"LANGUAGE:\n{language}\n\n"
                    f"TONE:\n{tone}\n\n"
                    f"ANALYSE_DATEN:\n{json.dumps(data, ensure_ascii=False)}\n\n"
                    f"ORIGINAL_SUBJECT:\n{data.get('source_subject', '')}\n\n"
                    f"ORIGINAL_FROM:\n{data.get('source_from', '')}\n\n"
                    f"ORIGINAL_SNIPPET:\n{data.get('source_snippet', '')}\n\n"
                    f"ORIGINAL_MAILTEXT_VOLLSTAENDIG:\n{data.get('source_body_text', '')}\n"
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

    return subject, with_signature(personalize_salutation(body, data))


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
    data = hydrate_source_context(client, data)

    if use_openai:
        subject, body = generate_draft_with_openai(
            data=data,
            model=model,
            language=language,
            tone=tone,
        )
        subject = build_subject(data, generated_subject=subject)
    else:
        subject = build_subject(data)
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
    # Safety guard: marker files are persisted only for real draft creation.
    if not dry_run:
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
        default="de",
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

    skipped_existing = 0
    if args.skip_existing:
        candidate_files: list[Path] = []
        for p in json_files:
            if p.name.endswith(".draft.json"):
                continue
            if draft_marker_path(p).exists():
                skipped_existing += 1
                continue
            candidate_files.append(p)
        json_files = candidate_files
        if skipped_existing:
            print(f"[INFO] Skipped {skipped_existing} files with existing draft marker")

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
