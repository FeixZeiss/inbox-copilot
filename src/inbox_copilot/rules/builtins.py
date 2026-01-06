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
            label_name="Security",
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
            label_name="Newsletter",
            reason="Newsletter heuristic matched",
        )

# TODO: refine this rule further to reduce false negatives
class JobAlertRule(BaseRule):
    name = "job_application"
    priority = 50

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

    # NEW: Interview / scheduling signals
    INTERVIEW_PHRASES = (
        "vorstellungsgespräch",
        "vorstellungs-gespräch",
        "interview",
        "teams-interview",
        "teams interview",
        "wir möchten dich gerne kennen lernen",
        "wir möchten dich gerne kennenlernen",
        "laden dich ein",
        "wir laden dich ein",
        "einladung zum gespräch",
        "einladung zum interview",
        "termin",
        "termin bestätigt",
        "den genannten termin hast du bereits telefonisch bestätigt",
        "besprechungs-id",
        "passcode",
        "microsoft teams",
        "jetzt an der besprechung teilnehmen",
        "1. vg",
        "vg -",   # keep, but guarded by context below
    )

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
        "m/w/d",
    )

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

        # 2) Interview invites / scheduling:
        # Require interview phrase AND some recruiting context to avoid catching random Teams meetings.
        if self.contains_any(hay, self.INTERVIEW_PHRASES):
            if self.contains_any(hay, self.RECRUITING_WORDS):
                return True
            # or subject looks like a job title / process mail (e.g., contains m/w/d or "junior")
            if re.search(r"\b(m/w/d|junior|senior|data engineer|software|entwickler)\b", hay):
                return True

        # 3) ATS marker + recruiting words is also very likely an application mail
        if self.contains_any(hay, self.ATS_MARKERS) and self.contains_any(hay, self.RECRUITING_WORDS):
            return True

        # 4) Regex fallbacks
        if re.search(r"\bdank\w*\b.*\bbewerb\w*\b", hay, flags=re.IGNORECASE):
            return True
        if re.search(r"\breceiv\w*\b.*\bapplicat\w*\b", hay, flags=re.IGNORECASE):
            return True
        if re.search(r"\bbedank\w*\b.*\bbewerb\w*\b", hay, flags=re.IGNORECASE):
            return True

        # NEW: direct "interview" + "invite" style fallback
        if re.search(r"\b(interview|vorstellungsgespräch)\b", hay) and re.search(r"\b(einlad\w*|invite\w*|termin)\b", hay):
            return True

        return False


    def actions(self, mail: MailItem) -> Iterable[Action]:
        yield Action(
            type="add_label",
            message_id=mail.id,
            label_name="Applications",
            reason="Job application confirmation / recruiting mail detected",
        )
        yield Action(
            type="analyze_application", 
            message_id=mail.id, 
            reason="Extract application status & next steps",
        )

class NoFitRule(BaseRule):
    priority = 0

    def match(self, mail: MailItem) -> bool:
        return True

    def actions(self, mail: MailItem) -> Iterable[Action]:
        yield Action(
            type="add_label",
            message_id=mail.id,
            label_name="NoFit",
            reason="Mail did not match any other rule",
        )