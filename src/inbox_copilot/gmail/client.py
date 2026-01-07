from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Any, Dict, List, Optional

from google.auth.transport.requests import Request
from google.oauth2.credentials import Credentials
from google_auth_oauthlib.flow import InstalledAppFlow
from googleapiclient.discovery import build
from googleapiclient.errors import HttpError

from inbox_copilot.gmail.LabelColors import LABEL_COLORS

# Needs modify to add/remove labels (messages.modify)
SCOPES = ["https://www.googleapis.com/auth/gmail.modify"]


@dataclass(frozen=True)
class GmailClientConfig:
    # Path to OAuth client credentials downloaded from Google Cloud Console.
    credentials_path: Path
    # Token cache will be created here after first login.
    token_path: Path
    # Gmail userId, "me" refers to the authenticated user.
    user_id: str = "me"


class GmailClient:
    def __init__(self, cfg: GmailClientConfig):
        self._cfg = cfg
        self._creds: Optional[Credentials] = None
        self._service = None

        # Cache label name -> label id to avoid repeated API calls
        self._label_cache: Dict[str, str] = {}

    def connect(self) -> None:
        """Create an authenticated Gmail API service client."""
        creds = None

        if self._cfg.token_path.exists():
            creds = Credentials.from_authorized_user_file(str(self._cfg.token_path), SCOPES)

        # If there are no (valid) credentials available, let the user log in.
        if not creds or not creds.valid:
            if creds and creds.expired and creds.refresh_token:
                creds.refresh(Request())
            else:
                flow = InstalledAppFlow.from_client_secrets_file(
                    str(self._cfg.credentials_path),
                    SCOPES,
                )
                creds = flow.run_local_server(port=0)

            # Save the credentials for the next run.
            self._cfg.token_path.parent.mkdir(parents=True, exist_ok=True)
            self._cfg.token_path.write_text(creds.to_json(), encoding="utf-8")

        self._creds = creds
        self._service = build("gmail", "v1", credentials=creds)

        # Clear label cache after (re)connect to avoid stale mappings
        self._label_cache.clear()

    @property
    def service(self):
        if self._service is None:
            raise RuntimeError("GmailClient is not connected. Call connect() first.")
        return self._service

    def list_messages(self, query: str = "", max_results: int = 10) -> List[str]:
        """
        List message IDs matching a Gmail search query.
        Example query: 'newer_than:7d in:inbox -category:promotions'
        """
        resp = (
            self.service.users()
            .messages()
            .list(userId=self._cfg.user_id, q=query, maxResults=max_results)
            .execute()
        )
        msgs = resp.get("messages", [])
        return [m["id"] for m in msgs]

    def get_message(self, message_id: str, fmt: str = "full") -> Dict[str, Any]:
        """
        Fetch a full message resource.
        fmt: 'full' | 'metadata' | 'minimal' | 'raw'
        """
        try:
            return (
                self.service.users()
                .messages()
                .get(userId=self._cfg.user_id, id=message_id, format=fmt)
                .execute()
            )
        except HttpError as e:
            # Skip messages that no longer exist (deleted/moved) for this mailbox
            if getattr(e, "resp", None) and e.resp.status == 404:
                raise KeyError(f"Message not found: {message_id}") from e
        raise

    def get_profile(self) -> Dict[str, Any]:
        """Get the Gmail profile of the authenticated user."""
        return self.service.users().getProfile(userId=self._cfg.user_id).execute()
    
    def remove_label(self, message_id: str, label_name: str) -> None:
        label_id = self.get_or_create_label_id(label_name)  # or get_label_id + error if missing
        self.service.users().messages().modify(
            userId=self._cfg.user_id,
            id=message_id,
            body={"removeLabelIds": [label_id]},
        ).execute()


    # -----------------------------
    # Label helpers (name -> id)
    # -----------------------------

    def _refresh_label_cache(self) -> None:
        """Fetch all labels once and cache them by name."""
        resp = self.service.users().labels().list(userId=self._cfg.user_id).execute()
        labels = resp.get("labels", [])
        self._label_cache = {lbl["name"]: lbl["id"] for lbl in labels}

    def _get_label_id(self, label_name: str) -> Optional[str]:
        """Return label id if known, otherwise None."""
        if not self._label_cache:
            self._refresh_label_cache()
        return self._label_cache.get(label_name)
    
    def get_or_create_label_id(self, label_name: str) -> str:
        label_id = self._get_label_id(label_name)
        if label_id:
            self._update_label_color(label_id, label_name)
            return label_id
        return self._create_label(label_name)


    def _create_label(self, label_name: str) -> str:
        body = {
            "name": label_name,
            "labelListVisibility": "labelShow",
            "messageListVisibility": "show",
        }

        # Apply color if known
        color = LABEL_COLORS.get(label_name)
        if color:
            body["color"] = color

        created = (
            self.service.users()
            .labels()
            .create(userId=self._cfg.user_id, body=body)
            .execute()
        )

        label_id = created["id"]
        self._label_cache[label_name] = label_id
        return label_id
    
    def _update_label_color(self, label_id: str, label_name: str) -> None:
        color = LABEL_COLORS.get(label_name)
        if not color:
            return

        self.service.users().labels().patch(
            userId=self._cfg.user_id,
            id=label_id,
            body={"color": color},
        ).execute()

    def add_label(self, message_id: str, label_name: str) -> None:
        """Add a label (by name) to a message."""
        label_id = self.get_or_create_label_id(label_name)
        self.service.users().messages().modify(
            userId=self._cfg.user_id,
            id=message_id,
            body={"addLabelIds": [label_id]},
        ).execute()
