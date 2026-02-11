from __future__ import annotations

from backend.app.api.drafts import _as_reply_subject


def test_as_reply_subject_adds_re_prefix() -> None:
    assert _as_reply_subject("Einladung zum Vorstellungsgespraech") == "Re: Einladung zum Vorstellungsgespraech"


def test_as_reply_subject_normalizes_existing_reply_prefixes() -> None:
    assert _as_reply_subject("AW: Interview Termin") == "Re: Interview Termin"
    assert _as_reply_subject("Re: Interview Termin") == "Re: Interview Termin"
    assert _as_reply_subject("sv: Interview Termin") == "Re: Interview Termin"


def test_as_reply_subject_handles_empty_input() -> None:
    assert _as_reply_subject("") == "Re: Einladung zum Vorstellungsgespräch"
