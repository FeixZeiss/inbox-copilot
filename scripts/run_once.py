import os
from pathlib import Path
from dotenv import load_dotenv

load_dotenv()

# State handling: persistent application state (historyId, run counter)
from inbox_copilot.actions.executor import default_executor
from inbox_copilot.storage.state import load_state, save_state

# Gmail API wrapper and config
from inbox_copilot.gmail.client import GmailClient, GmailClientConfig

# Rule system: normalized mail representation + concrete rules
from inbox_copilot.rules.core import MailItem
from inbox_copilot.rules.builtins import GoogleSecurityAlertRule, JobAlertRule, NewsletterRule, NoFitRule

# Adjust this import to where your Action lives
from inbox_copilot.rules.actions import Action  # <-- change if needed
from googleapiclient.errors import HttpError


def load_gmail_config() -> GmailClientConfig:
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

    return cfg


def main() -> None:
    # ------------------------------------------------------------------
    # Rule registry
    # ------------------------------------------------------------------
    rules = [
        GoogleSecurityAlertRule(),
        NewsletterRule(),
        JobAlertRule(),
    ]

    # Optional: run higher priority rules first if you add "priority"
    # rules = sorted(rules, key=lambda r: getattr(r, "priority", 0), reverse=True)

    # ------------------------------------------------------------------
    # Load persistent application state
    # ------------------------------------------------------------------
    state_path = Path(".state/state.json")
    st = load_state(state_path)

    # ------------------------------------------------------------------
    # Initialize Gmail client
    # ------------------------------------------------------------------
    cfg = load_gmail_config()
    client = GmailClient(cfg)
    client.connect()

    profile = client.get_profile()
    print(f"Connected as: {profile.get('emailAddress')}")

    # ------------------------------------------------------------------
    # Local helpers: one evaluation flow for BOTH bootstrap + incremental
    # ------------------------------------------------------------------
    def build_mail(mid: str) -> tuple[MailItem, dict]:
        """Fetch message metadata and normalize into MailItem + headers."""
        msg = client.get_message(mid, fmt="metadata")
        headers = {h["name"]: h["value"] for h in msg["payload"].get("headers", [])}

        mail = MailItem(
            id=mid,
            thread_id=msg.get("threadId"),
            headers=headers,
            snippet=msg.get("snippet", ""),
        )
        return mail, headers

    def evaluate_rules(mail: MailItem) -> list[tuple[str, Action]]:
        """Return a list of (rule_name, action) pairs for this mail."""
        planned: list[tuple[str, Action]] = []
        for rule in rules:
            if rule.match(mail):
                for action in rule.actions(mail):
                    planned.append((rule.name, action))
        return planned

    def dedupe_actions(planned: list[tuple[str, Action]]) -> list[tuple[str, Action]]:
        """Remove duplicate actions (same type/label/reason) while keeping order."""
        seen: set[tuple[str, str | None, str]] = set()
        out: list[tuple[str, Action]] = []
        for rule_name, action in planned:
            key = (action.type, action.label_name, action.reason)
            if key not in seen:
                seen.add(key)
                out.append((rule_name, action))
        return out

    def print_dry_run(headers: dict, planned: list[tuple[str, Action]]) -> None:
        """Pretty print planned actions for one mail."""
        if not planned:
            return

        print("----")
        print(f"Subject: {headers.get('Subject', '')}")
        print(f"From:    {headers.get('From', '')}")

        for rule_name, action in planned:
            label = action.label_name or ""
            print(f"[rule:{rule_name}] -> {action.type} {label} ({action.reason})")

    def process_message(mid: str) -> None:
        try:
            mail, headers = build_mail(mid)
        except KeyError as e:
            # Message was deleted/moved between list/history and fetch
            print(f"[SKIP] {e}")
            return

        best_actions: list[Action] = []
        best_rule_name = "NONE"

        for rule in sorted(rules, key=lambda r: r.priority, reverse=True):
            if rule.match(mail):
                best_actions = list(rule.actions(mail))
                best_rule_name = getattr(rule, "name", rule.__class__.__name__)
                break

        if not best_actions:
            nofit = NoFitRule()
            best_actions = list(nofit.actions(mail))
            best_rule_name = getattr(nofit, "name", nofit.__class__.__name__)

        subj = headers.get("Subject", "")
        frm = headers.get("From", "")
        print(f"[match] {mid} -> {best_rule_name} | Subject={subj!r} | From={frm!r}")

        executor = default_executor(dry_run=False)
        executor.run(client, best_actions)

    def get_message_ids_incremental(start_history_id: str) -> tuple[list[str], str]:
        message_ids: list[str] = []
        page_token: str | None = None
        last_resp: dict | None = None

        while True:
            resp = client.service.users().history().list(
                userId="me",
                startHistoryId=start_history_id,
                historyTypes=["messageAdded", "labelAdded"],
                labelId="INBOX",
                pageToken=page_token,
                maxResults=500,
            ).execute()
            last_resp = resp

            for h in resp.get("history", []):
                for added in h.get("messagesAdded", []):
                    message_ids.append(added["message"]["id"])
                for la in h.get("labelsAdded", []):
                    msg = la.get("message")
                    if msg and "id" in msg:
                        message_ids.append(msg["id"])

            page_token = resp.get("nextPageToken")
            if not page_token:
                break

        # dedupe in-order
        seen = set()
        message_ids = [mid for mid in message_ids if not (mid in seen or seen.add(mid))]

        # “neuer checkpoint”: am besten aus profile frisch holen (oder last_resp["historyId"] wenn vorhanden)
        latest_profile = client.get_profile()
        new_history_id = latest_profile["historyId"]

        return message_ids, new_history_id


    def get_message_ids_bootstrap() -> list[str]:
        return client.list_messages(query="in:inbox newer_than:60d", max_results=200)

    if st.last_history_id is None:
        message_ids = get_message_ids_bootstrap()
        print(f"[bootstrap] Found {len(message_ids)} messages in last 7 days")

        for mid in message_ids:
            process_message(mid)

        latest_profile = client.get_profile()
        st.last_history_id = latest_profile["historyId"]
        st.runs += 1
        save_state(state_path, st)
        print(f"[state] initialized last_history_id={st.last_history_id}")
        return

    # incremental
    try:
        message_ids, new_history_id = get_message_ids_incremental(st.last_history_id)
    except HttpError as e:
        # If startHistoryId is invalid/too old -> resync
        print(f"[RESYNC] history list failed, falling back to last 7 days. Error: {e}")
        message_ids = client.list_messages(query="in:inbox newer_than:7d", max_results=500)
        new_history_id = client.get_profile()["historyId"]
        for mid in message_ids:
            process_message(mid)

    for mid in message_ids:
        process_message(mid)

    st.last_history_id = new_history_id
    st.runs += 1
    save_state(state_path, st)
    print(f"[state] runs={st.runs} last_history_id={st.last_history_id}")


if __name__ == "__main__":
    main()
