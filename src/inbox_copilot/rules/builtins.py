from __future__ import annotations

import re
from typing import Iterable

from inbox_copilot.rules.core import MailItem, Action
from inbox_copilot.rules.BaseRule import BaseRule   

class GoogleSecurityAlertRule(BaseRule):
    name = "google_security_alert"
    priority = 100

    def match(self, mail: MailItem) -> bool:
        from_ = self.sender(mail)
        subj = self.subject(mail)

        is_google_sender = self.contains_any(from_, [
            "accounts.google.com",
            "no-reply@accounts.google.com",
        ])
        is_security_topic = self.contains_any(subj, [
            "security",
            "sicherheits",
            "alert",
            "warn",
        ])

        return is_google_sender and is_security_topic

    def actions(self, mail: MailItem) -> Iterable[Action]:
        yield Action(
            type="add_label",
            message_id=mail.id,
            label_name="InboxCopilot/Security",
            reason="Google security-related sender/subject",
        )



class NewsletterRule(BaseRule):
    name = "newsletter"
    priority = 10

    def match(self, mail: MailItem) -> bool:
        from_ = self.sender(mail)
        subj = self.subject(mail)
        snip = self.snippet(mail)

        return (
            self.contains_any(from_, ["newsletter", "noreply", "no-reply", "mailchimp"])
            or self.contains_any(subj, ["newsletter", "weekly", "digest"])
            or self.regex(snip, r"\b(unsubscribe|abbestellen)\b")
        )

    def actions(self, mail: MailItem) -> Iterable[Action]:
        yield Action(
            type="add_label",
            message_id=mail.id,
            label_name="InboxCopilot/Newsletter",
            reason="Newsletter heuristic matched",
        )

class JobAlertRule(BaseRule):
    name = "job_application"
    priority = 50
    LABEL = "InboxCopilot/Applications"

    # Strong phrases (German + English) commonly found in confirmations
    CONFIRM_PHRASES = (
        "vielen dank für ihre bewerbung",
        "vielen dank fuer ihre bewerbung",
        "danke für ihre bewerbung",
        "danke fuer ihre bewerbung",
        "wir haben ihre bewerbung erhalten",
        "eingangsbestätigung",
        "eingangsbestaetigung",
        "bestätigung ihrer bewerbung",
        "bestätigung deiner bewerbung",
        "thank you for your application",
        "thank you for applying",
        "we received your application",
        "application received",
        "your application has been received",
        "wir bedanken uns für das vertrauen",
        "wir bedanken uns für deine bewerbung",
        "wir bedanken uns für ihre bewerbung",
        "danke für dein interesse",
        "thank you for your interest",
        "we appreciate your interest",
    )


    # General recruiting signals (fallback)
    RECRUITING_WORDS = (
        "bewerbung",
        "application",
        "candidate",
        "recruit",
        "recruiting",
        "talent acquisition",
        "hr",
        "career",
        "position",
        "stelle",
    )

    # ATS platforms (often show up in From / links / snippets)
    ATS_MARKERS = (
        "greenhouse",
        "lever",
        "workday",
        "smartrecruiters",
        "personio",
        "ashby",
        "icims",
        "recruitee",
        "teamtailor",
        "breezy",
        "jobvite",
        "successfactors",
    )

    def match(self, mail: MailItem) -> bool:
        subj = self.subject(mail)
        from_ = self.sender(mail)
        snip = self.snippet(mail)

        hay = f"{subj}\n{from_}\n{snip}".lower()

        # 1) Very strong confirmation phrases
        if self.contains_any(hay, self.CONFIRM_PHRASES):
            return True

        # 2) ATS marker + recruiting words is also very likely an application mail
        if self.contains_any(hay, self.ATS_MARKERS) and self.contains_any(hay, self.RECRUITING_WORDS):
            return True

        # 3) Regex fallback: "dank* ... bewerb" or "received ... application"
        if re.search(r"\bdank\w*\b.*\bbewerb\w*\b", hay, flags=re.IGNORECASE):
            return True
        if re.search(r"\breceiv\w*\b.*\bapplicat\w*\b", hay, flags=re.IGNORECASE):
            return True
        if re.search(r"\bbedank\w*\b.*\bbewerb\w*\b", hay, flags=re.IGNORECASE):
            return True


        return False

    def actions(self, mail: MailItem) -> Iterable[Action]:
        yield Action(
            type="add_label",
            message_id=mail.id,
            label_name=self.LABEL,
            reason="Job application confirmation / recruiting mail detected",
        )

class NoFitRule(BaseRule):
    name = "no_Fit"
    priority = 0
    LABEL = "InboxCopilot/No Fit"

    def match(self, mail: MailItem) -> bool:
        return True

    def actions(self, mail: MailItem) -> Iterable[Action]:
        yield Action(
            type="add_label",
            message_id=mail.id,
            label_name=self.LABEL,
            reason="Mail did not match any other rule",
        )