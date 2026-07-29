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
    """Collapse unique surname-style labels onto full canonical source names.

    Public polling can contain both a full display name and a shortened label.
    A shortened label is collapsed only when its normalized tokens are the
    unique suffix of one longer name present in the same source-derived roster.
    No curated or collector-specific aliases are applied.
    """

    canonical_names = {canonical_candidate_name(value) for value in names}
    names_by_key: dict[str, list[str]] = {}
    for name in canonical_names:
        names_by_key.setdefault(normalized_candidate_key(name), []).append(name)
    duplicate_keys = {
        key: values
        for key, values in names_by_key.items()
        if len(values) > 1
    }
    if duplicate_keys:
        key, values = sorted(duplicate_keys.items())[0]
        raise CandidateIdentityError(
            "normalized candidate identity collision between "
            f"{sorted(values)!r}: {key!r}"
        )

    full_names = [
        (name, normalized_candidate_key(name).split())
        for name in canonical_names
        if len(normalized_candidate_key(name).split()) > 1
    ]
    resolved: set[str] = set()
    for name in canonical_names:
        tokens = normalized_candidate_key(name).split()
        suffix_matches = [
            full_name
            for full_name, full_tokens in full_names
            if len(full_tokens) > len(tokens)
            and full_tokens[-len(tokens) :] == tokens
        ]
        if len(suffix_matches) > 1:
            raise CandidateIdentityError(
                f"candidate short label is ambiguous: {name!r} -> "
                f"{sorted(suffix_matches)!r}"
            )
        resolved.add(suffix_matches[0] if suffix_matches else name)

    candidate_identity_map(resolved)
    return sorted(
        resolved,
        key=lambda name: (name.casefold(), candidate_id(name)),
    )


def resolve_candidate_name(value: str, canonical_names: Iterable[str]) -> str:
    """Resolve one source label to an exact or unique suffix roster identity."""

    label = canonical_candidate_name(value)
    label_tokens = normalized_candidate_key(label).split()
    roster = [canonical_candidate_name(name) for name in canonical_names]
    exact = [
        name
        for name in roster
        if normalized_candidate_key(name) == " ".join(label_tokens)
    ]
    if len(exact) == 1:
        return exact[0]
    if len(exact) > 1:
        raise CandidateIdentityError(
            f"candidate label has multiple exact identities: {label!r}"
        )

    suffix_matches = [
        name
        for name in roster
        if (
            len(normalized_candidate_key(name).split()) > len(label_tokens)
            and normalized_candidate_key(name).split()[-len(label_tokens) :]
            == label_tokens
        )
    ]
    if len(suffix_matches) != 1:
        raise CandidateIdentityError(
            f"candidate label is not uniquely resolvable: {label!r}"
        )
    return suffix_matches[0]
