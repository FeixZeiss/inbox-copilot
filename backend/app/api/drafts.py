from __future__ import annotations

import json
import re
from datetime import datetime, timezone
from email.message import EmailMessage
from email.utils import parseaddr
from pathlib import Path
from typing import Any

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel
from openai import OpenAI, AuthenticationError

from backend.app.status import run_status_store
from inbox_copilot.app.run import load_gmail_config
from inbox_copilot.config.paths import SECRETS_DIR
from inbox_copilot.gmail.client import GmailClient
from inbox_copilot.parsing.parser import extract_body_from_payload

router = APIRouter()
SIGNATURE = "Mit freundlichen Grüßen\nFelix Zeiß"


class DraftsRequest(BaseModel):
    dry_run: bool = True


def _load_openai_api_key() -> str | None:
    txt_path = SECRETS_DIR / "openai_token.txt"
    if txt_path.exists():
        try:
            token = txt_path.read_text(encoding="utf-8").strip()
        except UnicodeDecodeError:
            return None
        return token or None

    json_path = SECRETS_DIR / "openai_token.json"
    if json_path.exists():
        try:
            payload = json.loads(json_path.read_text(encoding="utf-8"))
        except (UnicodeDecodeError, json.JSONDecodeError):
            return None
        # Prefer explicit key names, then generic token key.
        candidates = [
            payload.get("api_key"),
            payload.get("openai_api_key"),
            payload.get("token"),
        ]
        for candidate in candidates:
            if isinstance(candidate, str):
                token = candidate.strip()
                if token:
                    return token
        return None

    return None


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


def _build_subject(data: dict[str, Any], generated_subject: str | None = None) -> str:
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


def _extract_contact_name(data: dict[str, Any]) -> str | None:
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


def _extract_recipient_display(data: dict[str, Any]) -> str:
    raw_value = str(data.get("source_from") or "").strip()
    if not raw_value:
        return ""
    display_name, address = parseaddr(raw_value)
    display_name = display_name.strip()
    address = address.strip()
    if display_name and address:
        return f"{display_name} <{address}>"
    if address:
        return address
    return raw_value


def _personalize_salutation(body: str, data: dict[str, Any]) -> str:
    name = _extract_contact_name(data)
    if not name:
        return body
    lines = body.splitlines()
    if not lines:
        return body

    # Replace first non-empty salutation line with a personalized greeting.
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


def _hydrate_source_context(client: GmailClient, data: dict[str, Any]) -> dict[str, Any]:
    # If full source text is already present, keep as-is.
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


def _with_signature(body: str) -> str:
    text = body.strip()
    if text.endswith(SIGNATURE):
        return text
    return f"{text}\n\n{SIGNATURE}"


def _build_body(data: dict[str, Any]) -> str:
    contact_name = _extract_contact_name(data)
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

    return _with_signature("\n".join(lines))


def _generate_draft_with_openai(client: OpenAI, data: dict[str, Any]) -> tuple[str, str]:
    schema = {
        "type": "object",
        "additionalProperties": False,
        "properties": {
            "subject": {"type": "string"},
            "body": {"type": "string"},
        },
        "required": ["subject", "body"],
    }

    resp = client.responses.create(
        model="gpt-5.2",
        input=[
            {
                "role": "system",
                "content": (
                    "Erstelle eine kurze, hochwertige Antwort auf eine Interview-Einladung. "
                    "Schreibe ausschließlich auf Deutsch und im Klartext. "
                    "Sprich den Ansprechpartner nach Möglichkeit direkt mit Namen an. "
                    "Wenn kein Name erkennbar ist, beginne mit 'Hallo,'. "
                    "Der Text MUSS exakt mit diesen zwei Zeilen enden: "
                    "'Mit freundlichen Grüßen' und 'Felix Zeiß'. "
                    "Erfinde keine Fakten, die nicht im Originaltext stehen."
                ),
            },
            {
                "role": "user",
                "content": (
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

    payload = json.loads(output_text)
    subject = str(payload.get("subject") or "").strip()
    body = str(payload.get("body") or "").strip()
    if not subject or not body:
        raise RuntimeError("OpenAI response missing subject or body.")
    return subject, _with_signature(_personalize_salutation(body, data))


def _push_recent_action(action: dict[str, Any], detail: str) -> None:
    snapshot = run_status_store.snapshot()
    current = snapshot.get("recent_actions", [])
    run_status_store.update(
        state=snapshot.get("state", "running"),
        step=snapshot.get("step", "drafts"),
        detail=detail,
        recent_actions=[action] + current[:49],
    )


def _push_draft_summary(
    *,
    detail: str,
    dry_run: bool,
    total_files: int,
    eligible: int,
    created: int,
    dry_run_count: int,
    skipped_existing: int,
    errors: int,
    using_openai: bool,
) -> None:
    _push_recent_action(
        {
            "type": "draft_summary",
            "mode": "dry_run" if dry_run else "created",
            "total_files": total_files,
            "eligible": eligible,
            "created": created,
            "dry_run_count": dry_run_count,
            "skipped_existing": skipped_existing,
            "errors": errors,
            "using_openai": using_openai,
        },
        detail=detail,
    )


@router.post("/drafts/create")
def create_drafts(payload: DraftsRequest) -> dict[str, Any]:
    repo_root = Path(__file__).resolve().parents[3]
    interviews_dir = repo_root / "logs" / "interviews"

    run_status_store.update(
        state="running",
        step="drafts",
        detail="Preparing draft creation",
    )

    if not interviews_dir.exists():
        raise HTTPException(status_code=400, detail=f"Missing directory: {interviews_dir}")

    json_files = sorted(
        p
        for p in interviews_dir.iterdir()
        if p.suffix == ".json" and not p.name.endswith(".draft.json")
    )
    if not json_files:
        detail = "No interview JSON files found"
        run_status_store.update(state="done", step="drafts", detail=detail)
        _push_draft_summary(
            detail=detail,
            dry_run=payload.dry_run,
            total_files=0,
            eligible=0,
            created=0,
            dry_run_count=0,
            skipped_existing=0,
            errors=0,
            using_openai=False,
        )
        return {
            "ok": True,
            "summary": {
                "total_files": 0,
                "eligible": 0,
                "created": 0,
                "dry_run": 0,
                "skipped_existing": 0,
                "errors": 0,
            },
            "used_openai": False,
            "dry_run": payload.dry_run,
        }

    # Fast pre-filter: skip files with existing marker before any JSON parsing/API calls.
    skipped_existing = 0
    candidate_files: list[Path] = []
    for json_path in json_files:
        marker_path = json_path.with_suffix(".draft.json")
        if marker_path.exists():
            skipped_existing += 1
            continue
        candidate_files.append(json_path)

    if not candidate_files:
        detail = f"No new draft candidates (skipped {skipped_existing} existing markers)"
        run_status_store.update(state="done", step="drafts", detail=detail)
        _push_draft_summary(
            detail=detail,
            dry_run=payload.dry_run,
            total_files=len(json_files),
            eligible=0,
            created=0,
            dry_run_count=0,
            skipped_existing=skipped_existing,
            errors=0,
            using_openai=False,
        )
        return {
            "ok": True,
            "summary": {
                "total_files": len(json_files),
                "eligible": 0,
                "created": 0,
                "dry_run": 0,
                "skipped_existing": skipped_existing,
                "errors": 0,
            },
            "used_openai": False,
            "dry_run": payload.dry_run,
        }

    cfg = load_gmail_config()
    gmail = GmailClient(cfg)
    gmail.connect()
    profile_email = gmail.get_profile().get("emailAddress", "")
    if not profile_email:
        raise HTTPException(status_code=500, detail="Could not resolve authenticated email address.")

    openai_token_uploaded = (SECRETS_DIR / "openai_token.json").exists() or (SECRETS_DIR / "openai_token.txt").exists()
    openai_client: OpenAI | None = None
    if openai_token_uploaded:
        token = _load_openai_api_key()
        if not token:
            msg = (
                "Uploaded OpenAI token is invalid (missing key field). "
                "Please upload a valid OpenAI API key."
            )
            run_status_store.update(state="error", step="drafts", detail=msg)
            raise HTTPException(
                status_code=400,
                detail={
                    "code": "openai_token_invalid",
                    "message": msg,
                    "delete_recommended": True,
                },
            )
        openai_client = OpenAI(api_key=token)

    total_files = len(json_files)
    eligible = 0
    created = 0
    dry_run_count = 0
    errors = 0

    for json_path in candidate_files:
        try:
            data = json.loads(json_path.read_text(encoding="utf-8"))
            if data.get("status") != "interview":
                continue
            data = _hydrate_source_context(gmail, data)

            eligible += 1
            if openai_client:
                try:
                    subject, body = _generate_draft_with_openai(openai_client, data)
                    subject = _build_subject(data, generated_subject=subject)
                except AuthenticationError as exc:
                    msg = (
                        "Uploaded OpenAI token is invalid. "
                        "Please upload a valid OpenAI API key and try again."
                    )
                    run_status_store.update(state="error", step="drafts", detail=msg)
                    raise HTTPException(
                        status_code=401,
                        detail={
                            "code": "openai_token_invalid",
                            "message": msg,
                            "delete_recommended": True,
                        },
                    ) from exc
            else:
                subject = _build_subject(data)
                body = _build_body(data)

            recipient = _extract_recipient_display(data)
            if payload.dry_run:
                dry_run_count += 1
                continue

            msg = EmailMessage()
            msg["From"] = profile_email
            msg["Subject"] = subject
            msg.set_content(body)

            resp = gmail.create_draft(msg)
            marker_payload = {
                "draft_id": resp.get("id"),
                "message_id": resp.get("message", {}).get("id"),
                "source_file": json_path.name,
                "created_at": datetime.now(timezone.utc).isoformat(),
            }
            # Safety guard: marker files are persisted only for real draft creation.
            if not payload.dry_run:
                marker_path = json_path.with_suffix(".draft.json")
                marker_path.write_text(
                    json.dumps(marker_payload, indent=2, ensure_ascii=True),
                    encoding="utf-8",
                )
            created += 1
            _push_recent_action(
                {
                    "type": "draft",
                    "mode": "created",
                    "to": recipient,
                    "subject": subject,
                    "source_file": json_path.name,
                    "using_openai": bool(openai_client),
                },
                detail=f"Draft created: {json_path.name}",
            )
        except HTTPException:
            raise
        except Exception as exc:
            errors += 1
            current = run_status_store.snapshot().get("recent_errors", [])
            run_status_store.update(
                state="running",
                step="drafts",
                detail=f"Draft error: {json_path.name}",
                recent_errors=[
                    {
                        "message_id": json_path.name,
                        "from": "",
                        "subject": "",
                        "error": f"{type(exc).__name__}: {exc}",
                    }
                ]
                + current[:49],
            )

    run_status_store.update(
        state="done",
        step="drafts",
        detail="Draft creation completed",
    )
    _push_draft_summary(
        detail="Draft creation completed",
        dry_run=payload.dry_run,
        total_files=total_files,
        eligible=eligible,
        created=created,
        dry_run_count=dry_run_count,
        skipped_existing=skipped_existing,
        errors=errors,
        using_openai=bool(openai_client),
    )

    return {
        "ok": True,
        "summary": {
            "total_files": total_files,
            "eligible": eligible,
            "created": created,
            "dry_run": dry_run_count,
            "skipped_existing": skipped_existing,
            "errors": errors,
        },
        "used_openai": bool(openai_client),
        "dry_run": payload.dry_run,
    }
