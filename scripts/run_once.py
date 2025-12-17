import os
from pathlib import Path

# State handling: persistent application state (historyId, run counter)
from inbox_copilot.storage.state import load_state, save_state

# Gmail API wrapper and config
from inbox_copilot.gmail.client import GmailClient, GmailClientConfig

# Rule system: normalized mail representation + concrete rules
from inbox_copilot.rules.core import MailItem
from inbox_copilot.rules.builtins import GoogleSecurityAlertRule, NewsletterRule


def load_gmail_config() -> GmailClientConfig:
    """
    Load Gmail OAuth configuration from a secrets directory.

    The secrets directory must be provided via environment variable:
    - INBOX_COPILOT_SECRETS_DIR (preferred)
    - AIVA_SECRETS_DIR (fallback)

    This function is intentionally strict:
    - Secrets must exist
    - Credentials file must be present
    """
    secrets_dir = os.getenv("INBOX_COPILOT_SECRETS_DIR") or os.getenv("AIVA_SECRETS_DIR")
    if not secrets_dir:
        raise RuntimeError("Set INBOX_COPILOT_SECRETS_DIR (or AIVA_SECRETS_DIR).")

    base = Path(secrets_dir)

    cfg = GmailClientConfig(
        credentials_path=base / "credentials.json",
        token_path=base / "gmail_token.json",
        user_id="me",
    )

    if not cfg.credentials_path.exists():
        raise FileNotFoundError(f"Missing credentials: {cfg.credentials_path}")

    # Ensure token directory exists (token is written during OAuth flow)
    cfg.token_path.parent.mkdir(parents=True, exist_ok=True)
    return cfg


def main() -> None:
    # ------------------------------------------------------------------
    # Rule registry
    # Each rule:
    # - decides whether a mail matches (match)
    # - emits one or more Actions (actions)
    # ------------------------------------------------------------------
    rules = [
        GoogleSecurityAlertRule(),
        NewsletterRule(),
    ]

    # ------------------------------------------------------------------
    # Load persistent application state
    # Contains last processed Gmail historyId + run counter
    # ------------------------------------------------------------------
    state_path = Path(".state/state.json")
    st = load_state(state_path)

    # ------------------------------------------------------------------
    # Initialize Gmail client
    # ------------------------------------------------------------------
    cfg = load_gmail_config()
    client = GmailClient(cfg)
    client.connect()

    # Fetch basic profile information (also provides current historyId)
    profile = client.get_profile()
    print(f"Connected as: {profile.get('emailAddress')}")


    # INIT: first run evaluates last 7 days via search query (bootstrap),
    # then stores current historyId as the incremental checkpoint.
    # This prevents retroactively processing the entire mailbox.
    if st.last_history_id is None:
        bootstrap_ids = client.list_messages(query="in:inbox newer_than:7d", max_results=200)
        print(f"[bootstrap] Found {len(bootstrap_ids)} messages in last 7 days")

        for mid in bootstrap_ids:
            msg = client.get_message(mid, fmt="metadata")
            headers = {h["name"]: h["value"] for h in msg["payload"].get("headers", [])}

            mail = MailItem(
                id=mid,
                thread_id=msg.get("threadId"),
                headers=headers,
                snippet=msg.get("snippet", ""),
            )

            planned = []  # IMPORTANT: reset per message
            for r in rules:
                if r.match(mail):
                    planned.extend(list(r.actions(mail)))

            for a in planned:
                print(f"[rule:{r.name}] -> {a.type} {a.label_name or ''} ({a.reason})")
            print("----")
            print(f"Subject: {headers.get('Subject')}")
            print(f"From:    {headers.get('From')}")

    # After bootstrap processing, start incremental from "now"
    st.last_history_id = profile["historyId"]
    st.runs += 1
    save_state(state_path, st)
    print(f"[state] initialized last_history_id={st.last_history_id} (after bootstrap)")
    return


    # ------------------------------------------------------------------
    # INCREMENTAL MODE:
    # Fetch only changes since the last stored historyId.
    # We are specifically interested in newly added messages.
    # ------------------------------------------------------------------
    resp = client.service.users().history().list(
        userId="me",
        startHistoryId=st.last_history_id,
        historyTypes=["messageAdded"],
    ).execute()

    history = resp.get("history", [])

    # Collect message IDs from the history response
    message_ids: list[str] = []
    for h in history:
        for added in h.get("messagesAdded", []):
            message_ids.append(added["message"]["id"])

    print(f"Found {len(message_ids)} new messages since historyId={st.last_history_id}")

    # ------------------------------------------------------------------
    # Rule evaluation (dry-run)
    # For each new message:
    # - fetch metadata
    # - normalize it into MailItem
    # - let all rules evaluate it
    # - collect planned actions
    # ------------------------------------------------------------------
    planned = []

    print(message_ids)

    # Limit to first 5 messages for safety during development
    for mid in message_ids[:5]:
        msg = client.get_message(mid, fmt="metadata")

        # Normalize headers into a simple dict for rule matching
        headers = {
            h["name"]: h["value"]
            for h in msg["payload"].get("headers", [])
        }

        # Unified mail representation passed to all rules
        mail = MailItem(
            id=mid,
            thread_id=msg.get("threadId"),
            headers=headers,
            snippet=msg.get("snippet", ""),
        )

        # Apply all rules to the mail
        for r in rules:
            print(r)  # debug: which rule is currently evaluated
            if r.match(mail):
                planned.extend(list(r.actions(mail)))

        # Print planned actions (dry-run, nothing is executed yet)
        for a in planned:
            print(f"[rule:{r.name}] -> {a.type} {a.label_name or ''} ({a.reason})")
            print("----")
            print(f"Subject: {headers.get('Subject')}")
            print(f"From:    {headers.get('From')}")

    # ------------------------------------------------------------------
    # Update checkpoint:
    # We always move the historyId forward to the latest value
    # AFTER successful processing.
    # ------------------------------------------------------------------
    st.last_history_id = profile["historyId"]
    st.runs += 1
    save_state(state_path, st)
    print(f"[state] runs={st.runs} last_history_id={st.last_history_id}")


if __name__ == "__main__":
    main()
