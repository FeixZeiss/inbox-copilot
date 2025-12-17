from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Any, Dict, List, Optional

from google.auth.transport.requests import Request
from google.oauth2.credentials import Credentials
from google_auth_oauthlib.flow import InstalledAppFlow
from googleapiclient.discovery import build


# Readonly is enough for fetching and labeling later can be upgraded to modify.
SCOPES = ["https://www.googleapis.com/auth/gmail.readonly"]


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
        return (
            self.service.users()
            .messages()
            .get(userId=self._cfg.user_id, id=message_id, format=fmt)
            .execute()
        )

    def get_profile(self) -> Dict[str, Any]:
        """Get the Gmail profile of the authenticated user."""
        return self.service.users().getProfile(userId=self._cfg.user_id).execute()
