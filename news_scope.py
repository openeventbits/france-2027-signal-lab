"""Shared deterministic scope checks for French presidential-election news."""

from __future__ import annotations

import html
import re
import unicodedata
from typing import Any


GENERIC_PRESIDENTIAL_PATTERNS = (
    re.compile(r"\bpresidentielle\b"),
    re.compile(r"\bpresidentielles\b"),
    re.compile(r"\belection\s+presidentielle\b"),
    re.compile(r"\belections\s+presidentielles\b"),
    re.compile(r"\bscrutin\s+presidentiel\b"),
    re.compile(r"\bcourse\s+presidentielle\b"),
    re.compile(r"\bcampagne\s+presidentielle\b"),
    re.compile(r"\bsondages?\s+presidentiels?\b"),
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
    re.compile(
        r"\belections\s+presidentielles"
        r"(?:\s+francaises)?"
        r"(?:\s+de)?\s+2027\b"
    ),
    re.compile(
        r"\bscrutin\s+presidentiel(?:\s+francais)?"
        r"(?:\s+(?:de|a\s+venir))?\s+2027\b"
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

FOREIGN_PRESIDENTIAL_CONTEXT_PATTERNS = (
    re.compile(
        r"\b(?:presidentielles?|election\s+presidentielle|"
        r"elections\s+presidentielles|scrutin\s+presidentiel)\s+"
        r"(?:americain|americaine|americaines|bresilien|bresilienne|"
        r"bresiliennes|roumain|roumaine|roumaines|russe|russes|"
        r"ukrainien|ukrainienne|ukrainiennes)\b"
    ),
    re.compile(
        r"\bsondages?\s+presidentiels?\s+"
        r"(?:americain|americaine|bresilien|bresilienne|roumain|"
        r"roumaine|russe|ukrainien|ukrainienne)\b"
    ),
    re.compile(
        r"\b(?:presidentielle|election\s+presidentielle|"
        r"elections\s+presidentielles|scrutin\s+presidentiel)\b"
        r"(?:\s+[a-z0-9]+){0,3}\s+"
        r"\b(?:aux\s+etats\s+unis|aux\s+usa|au\s+bresil|"
        r"en\s+roumanie|en\s+russie|en\s+ukraine)\b"
    ),
    re.compile(
        r"\b(?:etats\s+unis|usa|bresil|roumanie|russie|ukraine)\b"
        r"(?:\s+[a-z0-9]+){0,5}\s+"
        r"\b(?:presidentielle|election\s+presidentielle|"
        r"elections\s+presidentielles|scrutin\s+presidentiel)\b"
    ),
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
    summary_text = normalize_scope_text(summary)
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

    # A monitored French figure may help anchor otherwise generic race
    # language, but identity must not override an explicit foreign-election
    # subject such as "l'élection présidentielle américaine".
    if has_candidate_anchor(candidate_names) and not any(
        pattern.search(headline_text) or pattern.search(summary_text)
        for pattern in FOREIGN_PRESIDENTIAL_CONTEXT_PATTERNS
    ):
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
