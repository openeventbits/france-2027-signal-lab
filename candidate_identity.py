"""Narrow candidate-identity helpers for Candidate Signals.

The public source payloads already contain canonical display names.  This
module therefore normalizes only whitespace and matching identity, and creates
stable ASCII identifiers.  It intentionally contains no collector aliases.
"""

from __future__ import annotations

import re
import unicodedata
from collections.abc import Iterable


class CandidateIdentityError(ValueError):
    """Raised when canonical candidate identities are empty or collide."""


def canonical_candidate_name(value: str) -> str:
    """Return an NFC display name with deterministic internal whitespace."""

    if not isinstance(value, str):
        raise CandidateIdentityError("candidate name must be a string")
    name = re.sub(r"\s+", " ", unicodedata.normalize("NFC", value)).strip()
    if not name:
        raise CandidateIdentityError("candidate name must not be empty")
    return name


def normalized_candidate_key(value: str) -> str:
    """Return an accent-insensitive Unicode-aware candidate matching key."""

    name = canonical_candidate_name(value)
    decomposed = unicodedata.normalize("NFKD", name)
    without_marks = "".join(
        character
        for character in decomposed
        if not unicodedata.combining(character)
    ).casefold()
    tokens: list[str] = []
    current: list[str] = []
    for character in without_marks:
        if character.isalnum():
            current.append(character)
        elif current:
            tokens.append("".join(current))
            current = []
    if current:
        tokens.append("".join(current))
    key = " ".join(tokens)
    if not key:
        raise CandidateIdentityError(
            f"candidate name has no usable identity characters: {name!r}"
        )
    return key


def candidate_id(value: str) -> str:
    """Return a deterministic lowercase ASCII candidate identifier."""

    name = canonical_candidate_name(value)
    decomposed = unicodedata.normalize("NFKD", name)
    ascii_text = "".join(
        character
        for character in decomposed
        if not unicodedata.combining(character) and character.isascii()
    ).lower()
    identifier = re.sub(r"[^a-z0-9]+", "-", ascii_text).strip("-")
    if not identifier:
        raise CandidateIdentityError(
            f"candidate name cannot form an ASCII id: {name!r}"
        )
    return identifier


def candidate_identity_map(names: Iterable[str]) -> dict[str, str]:
    """Return canonical-name-to-id mapping after checking key and ID collisions."""

    identifiers: dict[str, str] = {}
    normalized_keys: dict[str, str] = {}
    result: dict[str, str] = {}

    for value in names:
        name = canonical_candidate_name(value)
        identifier = candidate_id(name)
        normalized = normalized_candidate_key(name)

        prior_id_name = identifiers.get(identifier)
        if prior_id_name is not None and prior_id_name != name:
            raise CandidateIdentityError(
                "candidate id collision between "
                f"{prior_id_name!r} and {name!r}: {identifier}"
            )

        prior_key_name = normalized_keys.get(normalized)
        if prior_key_name is not None and prior_key_name != name:
            raise CandidateIdentityError(
                "normalized candidate identity collision between "
                f"{prior_key_name!r} and {name!r}: {normalized!r}"
            )

        identifiers[identifier] = name
        normalized_keys[normalized] = name
        result[name] = identifier

    return result


def canonicalize_candidate_roster(names: Iterable[str]) -> list[str]:
    """Canonicalize a roster without inferring identities from partial names."""

    canonical_names = {canonical_candidate_name(value) for value in names}
    candidate_identity_map(canonical_names)
    return sorted(
        canonical_names,
        key=lambda name: (name.casefold(), candidate_id(name)),
    )


def resolve_candidate_name(value: str, canonical_names: Iterable[str]) -> str:
    """Resolve one source label only to an exact normalized roster identity."""

    label = canonical_candidate_name(value)
    label_key = normalized_candidate_key(label)
    roster = [canonical_candidate_name(name) for name in canonical_names]
    exact = [
        name
        for name in roster
        if normalized_candidate_key(name) == label_key
    ]
    if len(exact) == 1:
        return exact[0]
    if len(exact) > 1:
        raise CandidateIdentityError(
            f"candidate label has multiple exact identities: {label!r}"
        )
    raise CandidateIdentityError(
        f"candidate label is not explicitly resolvable: {label!r}"
    )
