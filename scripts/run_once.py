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
from inbox_copilot.rules.builtins import GoogleSecurityAlertRule, JobAlertRule, NewsletterRule

# Adjust this import to where your Action lives
from inbox_copilot.rules.actions import Action  # <-- change if needed


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

    # ------------------------------------------------------------------
    # BOOTSTRAP (first run only)
    # ------------------------------------------------------------------
    if st.last_history_id is None:
        bootstrap_ids = client.list_messages(query="in:inbox newer_than:7d", max_results=200)
        print(f"[bootstrap] Found {len(bootstrap_ids)} messages in last 7 days")

        for mid in bootstrap_ids:
            mail, headers = build_mail(mid)
            planned = evaluate_rules(mail)
            planned = dedupe_actions(planned)
            #print_dry_run(headers, planned)
            all_actions: list[Action] = []
            for rule in rules:
                if rule.match(mail):
                    # Either rule.actions (static) or rule.plan(mail) (dynamic)
                    all_actions.extend(rule.actions(mail))

            executor = default_executor(dry_run=False)
            executor.run(client, all_actions)

        # Set checkpoint AFTER bootstrap
        st.last_history_id = profile["historyId"]
        st.runs += 1
        save_state(state_path, st)
        print(f"[state] initialized last_history_id={st.last_history_id} (after bootstrap)")
        return

    # ------------------------------------------------------------------
    # INCREMENTAL MODE
    # ------------------------------------------------------------------
    resp = client.service.users().history().list(
        userId="me",
        startHistoryId=st.last_history_id,
        historyTypes=["messageAdded"],
    ).execute()

    history = resp.get("history", [])

    message_ids: list[str] = []
    for h in history:
        for added in h.get("messagesAdded", []):
            message_ids.append(added["message"]["id"])

    print(f"Found {len(message_ids)} new messages since historyId={st.last_history_id}")

    # Dry-run first 5 during development
    for mid in message_ids:
        mail, headers = build_mail(mid)
        planned = evaluate_rules(mail)
        planned = dedupe_actions(planned)
        #print_dry_run(headers, planned)
        
        all_actions: list[Action] = []
        for rule in rules:
            if rule.match(mail):
                # Either rule.actions (static) or rule.plan(mail) (dynamic)
                all_actions.extend(rule.actions(mail))

        executor = default_executor(dry_run=False)
        executor.run(client, all_actions)


    # Update checkpoint AFTER processing
    st.last_history_id = profile["historyId"]
    st.runs += 1
    save_state(state_path, st)
    print(f"[state] runs={st.runs} last_history_id={st.last_history_id}")


if __name__ == "__main__":
    main()
