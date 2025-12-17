from __future__ import annotations

import re
from typing import Iterable

from inbox_copilot.rules.core import MailItem, Action


class GoogleSecurityAlertRule:
    name = "google_security_alert"

    def match(self, mail: MailItem) -> bool:
        from_ = (mail.headers.get("From") or "").lower()
        subj = (mail.headers.get("Subject") or "").lower()
        return ("accounts.google.com" in from_ or "no-reply@accounts.google.com" in from_) and (
            "security" in subj or "sicherheits" in subj or "alert" in subj or "warn" in subj
        )

    def actions(self, mail: MailItem) -> Iterable[Action]:
        yield Action(
            type="add_label",
            message_id=mail.id,
            label_name="InboxCopilot/Security",
            reason="Google security-related sender/subject",
        )


class NewsletterRule:
    name = "newsletter"

    def match(self, mail: MailItem) -> bool:
        from_ = (mail.headers.get("From") or "").lower()
        subj = (mail.headers.get("Subject") or "").lower()
        # Heuristic: common newsletter patterns
        return any(x in from_ for x in ["newsletter", "noreply", "no-reply", "mailchimp"]) or bool(
            re.search(r"\b(unsubscribe|abbestellen)\b", (mail.snippet or "").lower())
        ) or any(x in subj for x in ["newsletter", "weekly", "digest"])

    def actions(self, mail: MailItem) -> Iterable[Action]:
        yield Action(
            type="add_label",
            message_id=mail.id,
            label_name="InboxCopilot/Newsletter",
            reason="Newsletter heuristic matched",
        )
