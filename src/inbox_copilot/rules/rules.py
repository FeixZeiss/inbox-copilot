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
import re
from typing import Iterable

class JobAlertRule(BaseRule):
    name = "job_application"
    priority = 50

    # Strong "we got your application" signals
    CONFIRM_PHRASES = (
        "vielen dank für ihre bewerbung",
        "vielen dank fuer ihre bewerbung",
        "danke für ihre bewerbung",
        "danke fuer ihre bewerbung",
        "danke für deine bewerbung",
        "danke fuer deine bewerbung",
        "wir haben ihre bewerbung erhalten",
        "wir haben deine bewerbung erhalten",
        "eingangsbestätigung",
        "eingangsbestaetigung",
        "bestätigung ihrer bewerbung",
        "bestätigung deiner bewerbung",
        "thank you for your application",
        "thank you for applying",
        "we received your application",
        "application received",
        "your application has been received",
        "thank you for your interest",
        "we appreciate your interest",
    )

    # NEW: Rejections are still part of the application process
    REJECTION_PHRASES = (
        "nicht weiter berücksichtigen",
        "nicht weiter beruecksichtigen",
        "leider mitteilen",
        "wir müssen dir leider mitteilen",
        "wir muessen dir leider mitteilen",
        "wir müssen ihnen leider mitteilen",
        "wir muessen ihnen leider mitteilen",
        "konnten wir sie leider nicht",
        "konnten wir dich leider nicht",
        "leider nicht in den engsten kreis",
        "nicht in den engsten kreis",
        "bei der besetzung der stelle",
        "absage",
        "wir bedauern",
        "bedauern",
        "keinen günstigeren bescheid",
        "keinen guenstigeren bescheid",
        "wir wünschen ihnen alles gute für die zukunft",
        "wir wuenschen ihnen alles gute fuer die zukunft",
        "wir wünschen dir alles gute für die zukunft",
        "wir wuenschen dir alles gute fuer die zukunft",
        "werden wir gemäß unseren datenschutzbestimmungen löschen",
        "werden wir gemaess unseren datenschutzbestimmungen loeschen",
    )

    # Interview / scheduling signals
    INTERVIEW_PHRASES = (
        "vorstellungsgespräch",
        "vorstellungs-gespräch",
        "interview",
        "teams-interview",
        "teams interview",
        "wir möchten dich gerne kennen lernen",
        "wir möchten dich gerne kennenlernen",
        "wir moechten dich gerne kennen lernen",
        "wir moechten dich gerne kennenlernen",
        "laden dich ein",
        "wir laden dich ein",
        "einladung zum gespräch",
        "einladung zum gespraech",
        "einladung zum interview",
        "termin",
        "termin bestätigt",
        "termin bestaetigt",
        "den genannten termin hast du bereits telefonisch bestätigt",
        "den genannten termin hast du bereits telefonisch bestaetigt",
        "besprechungs-id",
        "passcode",
        "microsoft teams",
        "jetzt an der besprechung teilnehmen",
        "1. vg",
        "vg -",  # keep, but guarded by context below
    )

    # General recruiting context words
    RECRUITING_WORDS = (
        "bewerbung",
        "bewerbungsunterlagen",
        "application",
        "candidate",
        "recruit",
        "recruiting",
        "recruiter",
        "talent acquisition",
        "hr",
        "career",
        "position",
        "stelle",
        "m/w/d",
    )

    # Application document wording (helps for mails saying "Unterlagen" instead of "Bewerbung")
    APPLICATION_DOC_WORDS = (
        "unterlagen",
        "einreichung",
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

        # 2) Rejections: require recruiting/application context to avoid false positives
        if self.contains_any(hay, self.REJECTION_PHRASES):
            if self.contains_any(hay, self.RECRUITING_WORDS) or self.contains_any(hay, self.APPLICATION_DOC_WORDS):
                return True

        # 3) Interview invites / scheduling:
        # Require interview phrase AND some recruiting context to avoid catching random Teams meetings.
        if self.contains_any(hay, self.INTERVIEW_PHRASES):
            if self.contains_any(hay, self.RECRUITING_WORDS):
                return True
            # or subject looks like a job title / process mail (guarded)
            if re.search(r"\b(m/w/d|junior|senior|data engineer|software|entwickler)\b", hay, flags=re.IGNORECASE):
                return True

        # 4) ATS marker + recruiting words is very likely an application mail
        if self.contains_any(hay, self.ATS_MARKERS) and self.contains_any(hay, self.RECRUITING_WORDS):
            return True

        # 5) Regex fallbacks (order-insensitive)
        # German: "dank*/bedank*" and "bewerb*" in any order
        if re.search(r"\bdank\w*\b.*\bbewerb\w*\b", hay, flags=re.IGNORECASE):
            return True
        if re.search(r"\bbewerb\w*\b.*\bdank\w*\b", hay, flags=re.IGNORECASE):
            return True
        if re.search(r"\bbedank\w*\b.*\bbewerb\w*\b", hay, flags=re.IGNORECASE):
            return True
        if re.search(r"\bbewerb\w*\b.*\bbedank\w*\b", hay, flags=re.IGNORECASE):
            return True

        # English: "receiv*" and "applicat*" in any order
        if re.search(r"\breceiv\w*\b.*\bapplicat\w*\b", hay, flags=re.IGNORECASE):
            return True
        if re.search(r"\bapplicat\w*\b.*\breceiv\w*\b", hay, flags=re.IGNORECASE):
            return True

        # 6) Direct interview + invite/termin fallback
        if re.search(r"\b(interview|vorstellungsgespräch)\b", hay, flags=re.IGNORECASE) and re.search(
            r"\b(einlad\w*|invite\w*|termin)\b", hay, flags=re.IGNORECASE
        ):
            return True

        return False

    def actions(self, mail: MailItem) -> Iterable[Action]:
        yield Action(
            type="add_label",
            message_id=mail.id,
            label_name="Applications",
            reason="Job application / recruiting mail detected (confirmation, rejection, or interview scheduling)",
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