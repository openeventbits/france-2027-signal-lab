"""Deterministic, network-free candidate attribution for structured events."""

from __future__ import annotations

import json
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Iterable, Literal

from candidate_candidacy_status import (
    CandidateCandidacyStatusError,
    active_candidate_records,
    load_candidate_candidacy_status,
)
from candidate_identity import CandidateIdentityError, normalized_candidate_key
from campaign_event_sources import ATTRIBUTION_POLICIES, SOURCE_TYPES
from campaign_event_structured import StructuredEventRecord

__all__ = [
    "AttributedStructuredEvent",
    "CandidateAttributionBatch",
    "CandidateAttributionConfigurationError",
    "attribute_structured_event",
    "attribute_structured_events",
]


class CandidateAttributionConfigurationError(ValueError):
    """Raised when attribution configuration or canonical identity is unsafe."""


_DEFAULT_CANDIDATE_REGISTRY = Path(__file__).with_name(
    "candidate_candidacy_status.json"
)
_ATTRIBUTION_BASES = frozenset(
    {"explicit_participant", "candidate_owned_campaign"}
)
_DISCOURS_DE_RENTREE_PREFIX = ("discours", "de", "rentree", "de")
_PREFIX_RELATIONS = (
    ("avec",),
    ("en", "presence", "de"),
    ("discours", "de"),
    _DISCOURS_DE_RENTREE_PREFIX,
    ("intervention", "de"),
    ("prise", "de", "parole", "de"),
    ("meeting", "avec"),
    ("reunion", "publique", "avec"),
    ("debat", "avec"),
)
_SUFFIX_RELATIONS = (
    ("participera",),
    ("participe",),
    ("interviendra",),
    ("intervient",),
    ("sera", "present"),
    ("sera", "presente"),
    ("prendra", "la", "parole"),
    ("debattra",),
)
_PAIRED_RELATIONS = (
    ("face", "a"),
    ("contre",),
    ("vs",),
)
_EXCLUDED_EVENT_SEQUENCES = (
    ("reunion", "de", "soutien"),
    ("comite", "de", "soutien"),
    ("soiree", "de", "soutien"),
    ("rassemblement", "de", "soutien"),
    ("mobilisation", "pour"),
    ("retransmission",),
    ("projection", "du", "debat"),
    ("projection", "de", "debat"),
    ("watch", "party"),
)


@dataclass(frozen=True, slots=True)
class AttributedStructuredEvent:
    """One structured event associated with canonical candidate identities."""

    structured_event: StructuredEventRecord
    candidate_ids: tuple[str, ...]
    candidate_names: tuple[str, ...]
    attribution_basis: Literal[
        "explicit_participant",
        "candidate_owned_campaign",
    ]

    def __post_init__(self) -> None:
        if not isinstance(self.structured_event, StructuredEventRecord):
            raise CandidateAttributionConfigurationError(
                "structured_event must be a StructuredEventRecord"
            )
        if (
            type(self.candidate_ids) is not tuple
            or type(self.candidate_names) is not tuple
        ):
            raise CandidateAttributionConfigurationError(
                "candidate IDs and names must be tuples"
            )
        if not self.candidate_ids or len(self.candidate_ids) != len(
            self.candidate_names
        ):
            raise CandidateAttributionConfigurationError(
                "candidate IDs and names must be non-empty parallel tuples"
            )
        if any(
            not isinstance(value, str) or not value or value != value.strip()
            for value in (*self.candidate_ids, *self.candidate_names)
        ):
            raise CandidateAttributionConfigurationError(
                "candidate IDs and names must be non-empty trimmed text"
            )
        if len(set(self.candidate_ids)) != len(self.candidate_ids):
            raise CandidateAttributionConfigurationError(
                "candidate IDs must not contain duplicates"
            )
        if len(set(self.candidate_names)) != len(self.candidate_names):
            raise CandidateAttributionConfigurationError(
                "candidate names must not contain duplicates"
            )
        if (
            not isinstance(self.attribution_basis, str)
            or self.attribution_basis not in _ATTRIBUTION_BASES
        ):
            raise CandidateAttributionConfigurationError(
                "attribution_basis is not allowed"
            )


@dataclass(frozen=True, slots=True)
class CandidateAttributionBatch:
    """Deterministic accepted records and ordinary attribution rejections."""

    accepted: tuple[AttributedStructuredEvent, ...]
    rejected_records: int

    def __post_init__(self) -> None:
        if type(self.accepted) is not tuple or any(
            not isinstance(value, AttributedStructuredEvent)
            for value in self.accepted
        ):
            raise CandidateAttributionConfigurationError(
                "accepted must be a tuple of AttributedStructuredEvent records"
            )
        if type(self.rejected_records) is not int or self.rejected_records < 0:
            raise CandidateAttributionConfigurationError(
                "rejected_records must be a non-negative integer"
            )


@dataclass(frozen=True, slots=True)
class _Candidate:
    candidate_id: str
    candidate_name: str
    name_tokens: tuple[str, ...]


def _candidate_sort_key(candidate: _Candidate) -> tuple[str, str]:
    return candidate.candidate_name.casefold(), candidate.candidate_id


def _load_active_candidates(
    path: str | Path,
) -> tuple[tuple[_Candidate, ...], dict[str, _Candidate]]:
    try:
        registry = load_candidate_candidacy_status(path)
        active_records = active_candidate_records(registry)
    except (OSError, json.JSONDecodeError, CandidateCandidacyStatusError) as error:
        raise CandidateAttributionConfigurationError(
            f"candidate registry is unavailable or invalid: {error}"
        ) from error

    candidates: list[_Candidate] = []
    try:
        for entry in active_records:
            candidates.append(
                _Candidate(
                    candidate_id=entry["candidate_id"],
                    candidate_name=entry["candidate_name"],
                    name_tokens=tuple(
                        normalized_candidate_key(
                            entry["candidate_name"]
                        ).split()
                    ),
                )
            )
    except (KeyError, TypeError, CandidateIdentityError) as error:
        raise CandidateAttributionConfigurationError(
            f"candidate registry identity cannot be resolved: {error}"
        ) from error

    candidates.sort(key=_candidate_sort_key)
    by_id = {candidate.candidate_id: candidate for candidate in candidates}
    if len(by_id) != len(candidates):
        raise CandidateAttributionConfigurationError(
            "active candidate registry contains duplicate IDs"
        )
    return tuple(candidates), by_id


def _source_policy(source: Any) -> str:
    if type(source) is not dict:
        raise CandidateAttributionConfigurationError(
            "source must be a validated plain dict"
        )
    source_id = source.get("source_id")
    if (
        not isinstance(source_id, str)
        or not source_id
        or source_id != source_id.strip()
    ):
        raise CandidateAttributionConfigurationError(
            "source_id must be non-empty trimmed text"
        )
    source_type = source.get("source_type")
    if not isinstance(source_type, str) or source_type not in SOURCE_TYPES:
        raise CandidateAttributionConfigurationError(
            "source_type is not allowed"
        )
    collection = source.get("collection")
    if type(collection) is not dict:
        raise CandidateAttributionConfigurationError(
            "source collection configuration must be a plain dict"
        )
    policy = collection.get("attribution_policy")
    if not isinstance(policy, str) or policy not in ATTRIBUTION_POLICIES:
        raise CandidateAttributionConfigurationError(
            f"unknown attribution policy: {policy!r}"
        )
    if policy == "custom":
        raise CandidateAttributionConfigurationError(
            "custom attribution requires a bounded source-specific collector"
        )
    return policy


def _tokens(value: str) -> tuple[str, ...]:
    try:
        return tuple(normalized_candidate_key(value).split())
    except CandidateIdentityError:
        return ()


def _contains_sequence(
    tokens: tuple[str, ...],
    sequence: tuple[str, ...],
) -> bool:
    if not sequence or len(sequence) > len(tokens):
        return False
    return any(
        tokens[index : index + len(sequence)] == sequence
        for index in range(len(tokens) - len(sequence) + 1)
    )


def _sequence_starts(
    tokens: tuple[str, ...],
    sequence: tuple[str, ...],
) -> tuple[int, ...]:
    if not sequence or len(sequence) > len(tokens):
        return ()
    return tuple(
        index
        for index in range(len(tokens) - len(sequence) + 1)
        if tokens[index : index + len(sequence)] == sequence
    )


def _has_excluded_event_context(event: StructuredEventRecord) -> bool:
    for value in (event.title, event.description):
        if value is None:
            continue
        tokens = _tokens(value)
        if any(
            _contains_sequence(tokens, sequence)
            for sequence in _EXCLUDED_EVENT_SEQUENCES
        ):
            return True
    return False


def _has_unary_relation(
    tokens: tuple[str, ...],
    candidate: _Candidate,
) -> bool:
    for start in _sequence_starts(tokens, candidate.name_tokens):
        end = start + len(candidate.name_tokens)
        for prefix in _PREFIX_RELATIONS:
            if start < len(prefix) or tokens[start - len(prefix) : start] != prefix:
                continue
            if (
                prefix == _DISCOURS_DE_RENTREE_PREFIX
                and start != len(prefix)
            ):
                continue
            return True
        for suffix in _SUFFIX_RELATIONS:
            if tokens[end : end + len(suffix)] == suffix:
                return True

    return False


def _paired_candidates(
    tokens: tuple[str, ...],
    candidates: tuple[_Candidate, ...],
) -> set[str]:
    matched: set[str] = set()
    for left in candidates:
        for right in candidates:
            if left.candidate_id == right.candidate_id:
                continue
            for relation in _PAIRED_RELATIONS:
                sequence = left.name_tokens + relation + right.name_tokens
                if _contains_sequence(tokens, sequence):
                    matched.update((left.candidate_id, right.candidate_id))
            debate_between = (
                ("debat", "entre")
                + left.name_tokens
                + ("et",)
                + right.name_tokens
            )
            if _contains_sequence(tokens, debate_between):
                matched.update((left.candidate_id, right.candidate_id))
    return matched


def _explicit_candidates(
    event: StructuredEventRecord,
    candidates: tuple[_Candidate, ...],
) -> tuple[_Candidate, ...]:
    if _has_excluded_event_context(event):
        return ()

    title_and_description = tuple(
        _tokens(value)
        for value in (event.title, event.description)
        if value is not None
    )
    matched_ids: set[str] = set()
    for candidate in candidates:
        if any(
            _has_unary_relation(tokens, candidate)
            for tokens in title_and_description
        ):
            matched_ids.add(candidate.candidate_id)

    for tokens in title_and_description:
        matched_ids.update(_paired_candidates(tokens, candidates))

    if event.organization is not None:
        organization_tokens = _tokens(event.organization)
        for candidate in candidates:
            if organization_tokens == candidate.name_tokens:
                matched_ids.add(candidate.candidate_id)

    return tuple(
        candidate
        for candidate in candidates
        if candidate.candidate_id in matched_ids
    )


def _owned_candidates(
    source: dict[str, Any],
    active_by_id: dict[str, _Candidate],
) -> tuple[_Candidate, ...]:
    if source.get("source_type") != "candidate_first_party":
        raise CandidateAttributionConfigurationError(
            "candidate_owned_campaign requires candidate_first_party source"
        )
    candidate_ids = source.get("candidate_ids")
    if not isinstance(candidate_ids, list) or not candidate_ids:
        raise CandidateAttributionConfigurationError(
            "candidate_owned_campaign requires non-empty candidate_ids"
        )
    if any(not isinstance(value, str) for value in candidate_ids):
        raise CandidateAttributionConfigurationError(
            "candidate_owned_campaign candidate_ids must be strings"
        )
    if len(set(candidate_ids)) != len(candidate_ids):
        raise CandidateAttributionConfigurationError(
            "candidate_owned_campaign candidate_ids must be unique"
        )
    try:
        candidates = [active_by_id[candidate_id] for candidate_id in candidate_ids]
    except KeyError as error:
        raise CandidateAttributionConfigurationError(
            "candidate_owned_campaign owner ID is unknown, hidden, or ruled out: "
            f"{error.args[0]!r}"
        ) from error
    return tuple(sorted(candidates, key=_candidate_sort_key))


def _attributed_record(
    event: StructuredEventRecord,
    candidates: tuple[_Candidate, ...],
    *,
    basis: Literal["explicit_participant", "candidate_owned_campaign"],
) -> AttributedStructuredEvent:
    return AttributedStructuredEvent(
        structured_event=event,
        candidate_ids=tuple(candidate.candidate_id for candidate in candidates),
        candidate_names=tuple(candidate.candidate_name for candidate in candidates),
        attribution_basis=basis,
    )


def _attribute_with_context(
    event: StructuredEventRecord,
    *,
    source: dict[str, Any],
    policy: str,
    active_candidates: tuple[_Candidate, ...],
    active_by_id: dict[str, _Candidate],
) -> AttributedStructuredEvent | None:
    if not isinstance(event, StructuredEventRecord):
        raise CandidateAttributionConfigurationError(
            "event must be a StructuredEventRecord"
        )
    if policy == "candidate_owned_campaign":
        return _attributed_record(
            event,
            _owned_candidates(source, active_by_id),
            basis="candidate_owned_campaign",
        )

    candidates = _explicit_candidates(event, active_candidates)
    if not candidates or (
        policy == "multi_candidate_explicit" and len(candidates) < 2
    ):
        return None
    return _attributed_record(
        event,
        candidates,
        basis="explicit_participant",
    )


def attribute_structured_event(
    event: StructuredEventRecord,
    *,
    source: dict[str, Any],
    candidate_registry_path: str | Path = _DEFAULT_CANDIDATE_REGISTRY,
) -> AttributedStructuredEvent | None:
    """Attribute one record, returning ``None`` for a normal no-match result."""

    policy = _source_policy(source)
    active_candidates, active_by_id = _load_active_candidates(
        candidate_registry_path
    )
    return _attribute_with_context(
        event,
        source=source,
        policy=policy,
        active_candidates=active_candidates,
        active_by_id=active_by_id,
    )


def attribute_structured_events(
    events: Iterable[StructuredEventRecord],
    *,
    source: dict[str, Any],
    candidate_registry_path: str | Path = _DEFAULT_CANDIDATE_REGISTRY,
) -> CandidateAttributionBatch:
    """Attribute a deterministic batch and count ordinary no-match records."""

    policy = _source_policy(source)
    active_candidates, active_by_id = _load_active_candidates(
        candidate_registry_path
    )
    try:
        supplied_events = tuple(events)
    except TypeError as error:
        raise CandidateAttributionConfigurationError(
            "events must be an iterable of StructuredEventRecord objects"
        ) from error

    accepted: list[AttributedStructuredEvent] = []
    rejected_records = 0
    for event in supplied_events:
        attributed = _attribute_with_context(
            event,
            source=source,
            policy=policy,
            active_candidates=active_candidates,
            active_by_id=active_by_id,
        )
        if attributed is None:
            rejected_records += 1
        else:
            accepted.append(attributed)
    return CandidateAttributionBatch(
        accepted=tuple(accepted),
        rejected_records=rejected_records,
    )
