"""Shared deterministic scope checks for French presidential-election news."""

from __future__ import annotations

import html
import re
import unicodedata
from typing import Any


GENERIC_PRESIDENTIAL_PATTERNS = (
    re.compile(r"\bpresidentielle\b"),
    re.compile(r"\belection\s+presidentielle\b"),
    re.compile(r"\bcourse\s+presidentielle\b"),
    re.compile(r"\bcampagne\s+presidentielle\b"),
    re.compile(
        r"\bcandidat(?:e)?\s+a\s+la\s+presidence\b"
    ),
)

EXPLICIT_FRENCH_ELECTION_PATTERNS = (
    re.compile(
        r"\bpresidentielle"
        r"(?:\s+francaise)?"
        r"(?:\s+de)?\s+2027\b"
    ),
    re.compile(
        r"\belection\s+presidentielle"
        r"(?:\s+francaise)?"
        r"(?:\s+de)?\s+2027\b"
    ),
    re.compile(r"\bpresidentielle\s+francaise\b"),
    re.compile(
        r"\belection\s+presidentielle\s+francaise\b"
    ),
    re.compile(r"\bcourse\s+a\s+l\s+elysee\b"),
    re.compile(r"\belysee\s+2027\b"),
)

FRENCH_POLITICAL_FORMATION_PATTERNS = (
    re.compile(r"\bparti\s+socialiste\b"),
    re.compile(r"\brassemblement\s+national\b"),
    re.compile(r"\bla\s+france\s+insoumise\b"),
    re.compile(r"\bles\s+republicains\b"),
    re.compile(r"\bles?\s+ecologistes\b"),
    re.compile(r"\brenaissance\b"),
    re.compile(r"\bhorizons\b"),
    re.compile(r"\bplace\s+publique\b"),
    re.compile(r"\bmodem\b"),
    re.compile(r"\b(?:ps|rn|lfi|lr)\b"),
)


def normalize_scope_text(value: Any) -> str:
    """Normalize text for deterministic scope matching."""

    text = html.unescape(str(value or ""))
    text = unicodedata.normalize("NFKD", text)
    text = "".join(
        character
        for character in text
        if not unicodedata.combining(character)
    )
    text = text.casefold()
    text = re.sub(r"[^a-z0-9]+", " ", text)

    return re.sub(r"\s+", " ", text).strip()


def has_candidate_anchor(candidate_names: Any) -> bool:
    """Return whether upstream matched a monitored French candidate."""

    if isinstance(candidate_names, str):
        return bool(candidate_names.strip())

    if not isinstance(
        candidate_names,
        (
            list,
            tuple,
            set,
            frozenset,
        ),
    ):
        return False

    return any(
        isinstance(name, str) and bool(name.strip())
        for name in candidate_names
    )


def has_generic_presidential_context(
    headline: Any,
    summary: Any = "",
) -> bool:
    """Detect generic presidential-race language."""

    combined = normalize_scope_text(
        " ".join(
            part
            for part in (
                str(headline or ""),
                str(summary or ""),
            )
            if part
        )
    )

    return any(
        pattern.search(combined)
        for pattern in GENERIC_PRESIDENTIAL_PATTERNS
    )


def has_french_presidential_anchor(
    headline: Any,
    summary: Any = "",
    candidate_names: Any = None,
) -> bool:
    """Detect evidence that the presidential context concerns France."""

    headline_text = normalize_scope_text(headline)
    combined = normalize_scope_text(
        " ".join(
            part
            for part in (
                str(headline or ""),
                str(summary or ""),
            )
            if part
        )
    )

    if has_candidate_anchor(candidate_names):
        return True

    if any(
        pattern.search(combined)
        for pattern in EXPLICIT_FRENCH_ELECTION_PATTERNS
    ):
        return True

    if any(
        pattern.search(combined)
        for pattern in FRENCH_POLITICAL_FORMATION_PATTERNS
    ):
        return True

    # Restrict the broad country word to the headline. Feed summaries may
    # contain publisher labels such as "France 24", which must not rescue
    # an otherwise foreign presidential story.
    if re.search(r"\bfrance\b", headline_text):
        return True

    return False


def unanchored_presidential_context(
    headline: Any,
    summary: Any = "",
    candidate_names: Any = None,
) -> bool:
    """Reject generic presidential stories lacking a French-race anchor."""

    return (
        has_generic_presidential_context(
            headline,
            summary,
        )
        and not has_french_presidential_anchor(
            headline,
            summary,
            candidate_names,
        )
    )
