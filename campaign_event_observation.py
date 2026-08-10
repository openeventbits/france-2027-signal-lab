"""Deterministic, network-free Campaign Events observation construction."""

from __future__ import annotations

import hashlib
import json
import re
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Iterable, Literal

from candidate_identity import CandidateIdentityError, normalized_candidate_key
from campaign_event_attribution import AttributedStructuredEvent
from campaign_event_sources import (
    CAMPAIGN_EVENT_TYPES,
    CampaignEventSourceRegistryError,
    normalize_campaign_event_source_registry,
    normalize_https_url,
)
from campaign_events_contract import (
    CampaignEventsContractError,
    campaign_event_id,
    normalize_campaign_event_observations,
)

__all__ = [
    "CampaignEventObservationBatch",
    "CampaignEventObservationConfigurationError",
    "ClassifiedCampaignEvent",
    "build_campaign_event_observation",
    "build_campaign_event_observations",
    "classify_campaign_event",
]


class CampaignEventObservationConfigurationError(ValueError):
    """Raised when observation configuration or internal input is unsafe."""


_DEFAULT_CANDIDATE_REGISTRY = Path(__file__).with_name(
    "candidate_candidacy_status.json"
)
_DEFAULT_SOURCE_REGISTRY = Path(__file__).with_name("campaign_event_sources.json")
_UTC = timezone.utc
_OBSERVED_AT = re.compile(
    r"\d{4}-\d{2}-\d{2}T\d{2}:\d{2}:\d{2}Z\Z",
    re.ASCII,
)
_CLASSIFICATION_PRECEDENCE = (
    "campaign_launch",
    "debate",
    "candidate_visit",
    "rally",
    "public_meeting",
)
_PUBLIC_REQUIRED_KEYS = frozenset(
    {
        "event_key",
        "event_id",
        "event_type",
        "title",
        "candidate_ids",
        "candidate_names",
        "scheduled_start",
        "time_precision",
        "timezone",
        "status",
        "status_as_of",
        "evidence_status",
        "last_verified_at",
        "evidence",
    }
)
_PUBLIC_OPTIONAL_KEYS = frozenset(
    {
        "scheduled_end",
        "organization",
        "location_name",
        "locality",
        "department",
        "participants",
    }
)
_EXCLUDED_SEQUENCES = (
    ("comite", "de", "soutien"),
    ("reunion", "de", "soutien"),
    ("soiree", "de", "soutien"),
    ("rassemblement", "de", "soutien"),
    ("meeting", "de", "soutien"),
    ("watch", "party"),
    ("retransmission",),
    ("projection", "du", "debat"),
    ("projection", "de", "debat"),
    ("interview",),
    ("entretien",),
    ("conference", "de", "presse"),
    ("podcast",),
    ("emission",),
    ("publication",),
    ("communique",),
    ("formation",),
    ("atelier",),
    ("reunion", "interne"),
    ("reunion", "de", "bureau"),
    ("reunion", "des", "adherents"),
)
_CAMPAIGN_LAUNCH_SEQUENCES = (
    ("lancement", "de", "la", "campagne", "presidentielle"),
    ("lancement", "de", "campagne", "presidentielle"),
    ("lancement", "de", "la", "campagne"),
)
_PUBLIC_MEETING_PREFIXES = (
    ("meeting",),
    ("grand", "meeting"),
    ("reunion", "publique"),
    ("reunion", "electorale"),
)
_RALLY_PREFIXES = (
    ("rassemblement",),
    ("grand", "rassemblement"),
)
_CAMPAIGN_CONTEXT_SEQUENCES = (
    ("campagne",),
    ("campagne", "presidentielle"),
    ("presidentielle",),
    ("election", "presidentielle"),
)
_SOURCE_STATUS_MAP = {
    None: "scheduled",
    "CONFIRMED": "scheduled",
    "TENTATIVE": "scheduled",
    "CANCELLED": "cancelled",
    "POSTPONED": "postponed",
    "EventScheduled": "scheduled",
    "http://schema.org/EventScheduled": "scheduled",
    "http://schema.org/EventScheduled/": "scheduled",
    "https://schema.org/EventScheduled": "scheduled",
    "https://schema.org/EventScheduled/": "scheduled",
    "EventCancelled": "cancelled",
    "http://schema.org/EventCancelled": "cancelled",
    "http://schema.org/EventCancelled/": "cancelled",
    "https://schema.org/EventCancelled": "cancelled",
    "https://schema.org/EventCancelled/": "cancelled",
    "EventPostponed": "postponed",
    "http://schema.org/EventPostponed": "postponed",
    "http://schema.org/EventPostponed/": "postponed",
    "https://schema.org/EventPostponed": "postponed",
    "https://schema.org/EventPostponed/": "postponed",
}


@dataclass(frozen=True, slots=True)
class ClassifiedCampaignEvent:
    """One attributed record mapped to exactly one public campaign taxonomy."""

    attributed_event: AttributedStructuredEvent
    event_type: Literal[
        "rally",
        "public_meeting",
        "debate",
        "candidate_visit",
        "campaign_launch",
        "other",
    ]

    def __post_init__(self) -> None:
        if not isinstance(self.attributed_event, AttributedStructuredEvent):
            raise CampaignEventObservationConfigurationError(
                "attributed_event must be an AttributedStructuredEvent"
            )
        if self.event_type not in CAMPAIGN_EVENT_TYPES:
            raise CampaignEventObservationConfigurationError(
                "event_type is not in the Campaign Events taxonomy"
            )


@dataclass(frozen=True, slots=True)
class CampaignEventObservationBatch:
    """Contract-compatible observations and ordinary relevance rejections."""

    observations: tuple[dict[str, Any], ...]
    relevance_rejected_records: int

    def __post_init__(self) -> None:
        if type(self.observations) is not tuple:
            raise CampaignEventObservationConfigurationError(
                "observations must be a tuple"
            )
        allowed_keys = _PUBLIC_REQUIRED_KEYS | _PUBLIC_OPTIONAL_KEYS
        for observation in self.observations:
            if type(observation) is not dict:
                raise CampaignEventObservationConfigurationError(
                    "observations must contain plain dicts"
                )
            keys = frozenset(observation)
            if not _PUBLIC_REQUIRED_KEYS <= keys or not keys <= allowed_keys:
                raise CampaignEventObservationConfigurationError(
                    "observation does not have the public source-owned shape"
                )
        if (
            type(self.relevance_rejected_records) is not int
            or self.relevance_rejected_records < 0
        ):
            raise CampaignEventObservationConfigurationError(
                "relevance_rejected_records must be a non-negative integer"
            )


def _tokens(value: str) -> tuple[str, ...]:
    try:
        return tuple(normalized_candidate_key(value).split())
    except CandidateIdentityError as error:
        raise CampaignEventObservationConfigurationError(
            f"structured event text cannot be normalized: {error}"
        ) from error


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


def _starts_with(
    tokens: tuple[str, ...],
    sequence: tuple[str, ...],
) -> bool:
    return tokens[: len(sequence)] == sequence


def _event_token_fields(
    event: AttributedStructuredEvent,
) -> tuple[tuple[str, ...], ...]:
    structured = event.structured_event
    return tuple(
        _tokens(value)
        for value in (structured.title, structured.description)
        if value is not None
    )


def _has_excluded_context(fields: tuple[tuple[str, ...], ...]) -> bool:
    return any(
        _contains_sequence(tokens, sequence)
        for tokens in fields
        for sequence in _EXCLUDED_SEQUENCES
    )


def _is_campaign_launch(fields: tuple[tuple[str, ...], ...]) -> bool:
    for tokens in fields:
        for sequence in _CAMPAIGN_LAUNCH_SEQUENCES:
            if _starts_with(tokens, sequence):
                return True
            if (
                (_starts_with(tokens, ("meeting",))
                or _starts_with(tokens, ("grand", "meeting")))
                and _contains_sequence(tokens, sequence)
            ):
                return True
    return False


def _candidate_name_tokens(
    event: AttributedStructuredEvent,
) -> tuple[tuple[str, ...], ...]:
    return tuple(_tokens(name) for name in event.candidate_names)


def _has_paired_debate(
    fields: tuple[tuple[str, ...], ...],
    names: tuple[tuple[str, ...], ...],
) -> bool:
    if len(names) < 2:
        return False
    relations = (("face", "a"), ("contre",), ("vs",))
    for tokens in fields:
        for left in names:
            for right in names:
                if left == right:
                    continue
                if any(
                    _contains_sequence(tokens, left + relation + right)
                    for relation in relations
                ):
                    return True
                if _contains_sequence(
                    tokens,
                    ("debat", "entre") + left + ("et",) + right,
                ):
                    return True
    return False


def _is_debate(
    fields: tuple[tuple[str, ...], ...],
    event: AttributedStructuredEvent,
) -> bool:
    if any(
        _starts_with(tokens, ("debat",))
        or _starts_with(tokens, ("grand", "debat"))
        for tokens in fields
    ):
        return True
    return _has_paired_debate(fields, _candidate_name_tokens(event))


def _has_campaign_context(fields: tuple[tuple[str, ...], ...]) -> bool:
    return any(
        _contains_sequence(tokens, sequence)
        for tokens in fields
        for sequence in _CAMPAIGN_CONTEXT_SEQUENCES
    )


def _has_candidate_visit_semantics(
    fields: tuple[tuple[str, ...], ...],
    event: AttributedStructuredEvent,
) -> bool:
    for tokens in fields:
        for name in _candidate_name_tokens(event):
            if any(
                _contains_sequence(tokens, sequence)
                for sequence in (
                    ("visite", "de") + name,
                    name + ("en", "visite"),
                    ("deplacement", "de") + name,
                    name + ("se", "rendra", "a"),
                )
            ):
                return True
            if (
                _contains_sequence(tokens, name + ("sera", "a"))
                and _contains_sequence(
                    tokens,
                    ("dans", "le", "cadre", "d", "un", "deplacement"),
                )
            ):
                return True
    return False


def _is_candidate_visit(
    fields: tuple[tuple[str, ...], ...],
    event: AttributedStructuredEvent,
) -> bool:
    if not _has_candidate_visit_semantics(fields, event):
        return False
    return (
        event.attribution_basis == "candidate_owned_campaign"
        or _has_campaign_context(fields)
    )


def _is_rally(fields: tuple[tuple[str, ...], ...]) -> bool:
    for tokens in fields:
        if any(_starts_with(tokens, prefix) for prefix in _RALLY_PREFIXES):
            return True
        if (
            _starts_with(tokens, ("rally",))
            or _starts_with(tokens, ("rallye",))
        ) and _has_campaign_context((tokens,)):
            return True
    return False


def _is_public_meeting(fields: tuple[tuple[str, ...], ...]) -> bool:
    return any(
        any(_starts_with(tokens, prefix) for prefix in _PUBLIC_MEETING_PREFIXES)
        for tokens in fields
    )


def classify_campaign_event(
    event: AttributedStructuredEvent,
) -> ClassifiedCampaignEvent | None:
    """Classify one attributed record, or return ``None`` when not relevant."""

    if not isinstance(event, AttributedStructuredEvent):
        raise CampaignEventObservationConfigurationError(
            "event must be an AttributedStructuredEvent"
        )
    event.__post_init__()
    fields = _event_token_fields(event)
    if _has_excluded_context(fields):
        return None

    classifiers = {
        "campaign_launch": lambda: _is_campaign_launch(fields),
        "debate": lambda: _is_debate(fields, event),
        "candidate_visit": lambda: _is_candidate_visit(fields, event),
        "rally": lambda: _is_rally(fields),
        "public_meeting": lambda: _is_public_meeting(fields),
    }
    for event_type in _CLASSIFICATION_PRECEDENCE:
        if classifiers[event_type]():
            return ClassifiedCampaignEvent(event, event_type)
    return None


def _validated_source(
    source: Any,
    *,
    candidate_registry_path: str | Path,
) -> dict[str, Any]:
    try:
        normalized = normalize_campaign_event_source_registry(
            {"schema_version": "2.0", "sources": [source]},
            candidate_registry_path=candidate_registry_path,
        )["sources"][0]
    except (CampaignEventSourceRegistryError, OSError, TypeError) as error:
        raise CampaignEventObservationConfigurationError(
            f"source must be a valid campaign-event source record: {error}"
        ) from error
    if "campaign_events" not in normalized["allowed_lanes"]:
        raise CampaignEventObservationConfigurationError(
            "source is not allowed for campaign_events"
        )
    if not normalized["enabled"]:
        raise CampaignEventObservationConfigurationError(
            "source must be enabled"
        )
    return normalized


def _validated_observed_at(value: Any) -> str:
    if not isinstance(value, str) or not _OBSERVED_AT.fullmatch(value):
        raise CampaignEventObservationConfigurationError(
            "observed_at must be a canonical UTC RFC 3339 timestamp with seconds"
        )
    try:
        parsed = datetime.strptime(value, "%Y-%m-%dT%H:%M:%SZ").replace(
            tzinfo=_UTC
        )
    except ValueError as error:
        raise CampaignEventObservationConfigurationError(
            "observed_at must be a valid UTC timestamp"
        ) from error
    if parsed.strftime("%Y-%m-%dT%H:%M:%SZ") != value:
        raise CampaignEventObservationConfigurationError(
            "observed_at must be canonical UTC"
        )
    return value


def _validated_evidence_url(value: Any) -> str:
    try:
        return normalize_https_url(value, "evidence_url")
    except CampaignEventSourceRegistryError as error:
        raise CampaignEventObservationConfigurationError(str(error)) from error


def _validate_attribution_source_compatibility(
    event: AttributedStructuredEvent,
    source: dict[str, Any],
) -> None:
    if not event.candidate_ids:
        if (
            source["source_type"]
            not in {"party_first_party", "organizer_first_party"}
            or source["collection"]["attribution_policy"]
            != "explicit_participant"
        ):
            raise CampaignEventObservationConfigurationError(
                "unlinked attribution requires an explicit-participant "
                "party or organizer first-party source"
            )
        return
    source_is_candidate_owned = (
        source["collection"]["attribution_policy"]
        == "candidate_owned_campaign"
    )
    event_is_candidate_owned = (
        event.attribution_basis == "candidate_owned_campaign"
    )
    if source_is_candidate_owned != event_is_candidate_owned:
        raise CampaignEventObservationConfigurationError(
            "attribution basis is incompatible with source attribution policy"
        )
    if source_is_candidate_owned and list(event.candidate_ids) != source.get(
        "candidate_ids"
    ):
        raise CampaignEventObservationConfigurationError(
            "candidate-owned attribution does not match source candidate_ids"
        )


def _public_status(source_status: str | None) -> str:
    try:
        return _SOURCE_STATUS_MAP[source_status]
    except (KeyError, TypeError) as error:
        raise CampaignEventObservationConfigurationError(
            f"source_status cannot be mapped safely: {source_status!r}"
        ) from error


def _schedule_key_token(event: AttributedStructuredEvent) -> str:
    start = event.structured_event.scheduled_start
    if event.structured_event.time_precision == "date":
        return start
    return f"{start[:10]}-{start[11:16].replace(':', '')}"


def _source_owned_event_key(
    classified: ClassifiedCampaignEvent,
    *,
    source_id: str,
) -> str:
    attributed = classified.attributed_event
    structured = attributed.structured_event
    if structured.external_id is not None:
        identity = {
            "version": 1,
            "source_id": source_id,
            "external_id": structured.external_id,
        }
        encoded = json.dumps(
            identity,
            ensure_ascii=False,
            sort_keys=True,
            separators=(",", ":"),
        ).encode("utf-8")
        digest = hashlib.sha256(encoded).hexdigest()[:16]
        return f"{source_id}-uid-{digest}"

    anchor = {
        "title": structured.title,
        "scheduled_end": structured.scheduled_end,
        "organization": structured.organization,
        "location_name": structured.location_name,
        "locality": structured.locality,
    }
    identity = {
        "version": 1,
        "source_id": source_id,
        "event_type": classified.event_type,
        "scheduled_start": structured.scheduled_start,
        "time_precision": structured.time_precision,
        "candidate_ids": attributed.candidate_ids,
        "anchor": anchor,
    }
    encoded = json.dumps(
        identity,
        ensure_ascii=False,
        sort_keys=True,
        separators=(",", ":"),
    ).encode("utf-8")
    digest = hashlib.sha256(encoded).hexdigest()[:16]
    event_type = classified.event_type.replace("_", "-")
    return (
        f"{source_id}-{event_type}-{_schedule_key_token(attributed)}-{digest}"
    )


def _raw_observation(
    classified: ClassifiedCampaignEvent,
    *,
    source: dict[str, Any],
    observed_at: str,
    evidence_url: str,
) -> dict[str, Any]:
    attributed = classified.attributed_event
    structured = attributed.structured_event
    if classified.event_type not in source["allowed_event_types"]:
        raise CampaignEventObservationConfigurationError(
            f"classified event_type {classified.event_type!r} is not in "
            "source allowed_event_types"
        )
    status = _public_status(structured.source_status)
    event_key = _source_owned_event_key(
        classified,
        source_id=source["source_id"],
    )
    observation: dict[str, Any] = {
        "event_key": event_key,
        "event_id": campaign_event_id("campaign_events", event_key),
        "event_type": classified.event_type,
        "title": structured.title,
        "candidate_ids": list(attributed.candidate_ids),
        "candidate_names": list(attributed.candidate_names),
        "scheduled_start": structured.scheduled_start,
        "time_precision": structured.time_precision,
        "timezone": structured.timezone,
        "status": status,
        "status_as_of": observed_at[:10],
        "evidence_status": "verified",
        "last_verified_at": observed_at,
        "evidence": [
            {
                "source_id": source["source_id"],
                "source_url": evidence_url,
                "source_publisher": source["publisher"],
                "source_type": source["source_type"],
                "evidence_type": (
                    "explicit_schedule"
                    if status == "scheduled"
                    else "explicit_status_update"
                ),
            }
        ],
    }
    if structured.scheduled_end is not None:
        observation["scheduled_end"] = structured.scheduled_end
    if structured.participants:
        observation["participants"] = list(structured.participants)
    for field in ("organization", "location_name", "locality"):
        value = getattr(structured, field)
        if value is not None:
            observation[field] = value
    return observation


def build_campaign_event_observations(
    events: Iterable[AttributedStructuredEvent],
    *,
    source: dict[str, Any],
    observed_at: str,
    evidence_url: str,
    candidate_registry_path: str | Path = _DEFAULT_CANDIDATE_REGISTRY,
    source_registry_path: str | Path = _DEFAULT_SOURCE_REGISTRY,
) -> CampaignEventObservationBatch:
    """Build a deterministic batch without reconciling source observations."""

    normalized_source = _validated_source(
        source,
        candidate_registry_path=candidate_registry_path,
    )
    canonical_observed_at = _validated_observed_at(observed_at)
    canonical_evidence_url = _validated_evidence_url(evidence_url)
    try:
        supplied_events = tuple(events)
    except TypeError as error:
        raise CampaignEventObservationConfigurationError(
            "events must be an iterable of AttributedStructuredEvent records"
        ) from error

    observations: list[dict[str, Any]] = []
    rejected_records = 0
    for event in supplied_events:
        if not isinstance(event, AttributedStructuredEvent):
            raise CampaignEventObservationConfigurationError(
                "events must contain AttributedStructuredEvent records"
            )
        _validate_attribution_source_compatibility(event, normalized_source)
        classified = classify_campaign_event(event)
        if (
            classified is None
            and normalized_source["source_type"]
            in {
                "candidate_first_party",
                "party_first_party",
                "organizer_first_party",
            }
            and "other" in normalized_source["allowed_event_types"]
        ):
            classified = ClassifiedCampaignEvent(event, "other")
        if classified is None:
            rejected_records += 1
            continue
        observations.append(
            _raw_observation(
                classified,
                source=normalized_source,
                observed_at=canonical_observed_at,
                evidence_url=canonical_evidence_url,
            )
        )

    try:
        normalized_observations = normalize_campaign_event_observations(
            observations,
            candidate_registry_path=candidate_registry_path,
            source_registry_path=source_registry_path,
        )
    except (CampaignEventsContractError, OSError, TypeError) as error:
        raise CampaignEventObservationConfigurationError(
            f"constructed source-owned observation is invalid: {error}"
        ) from error
    return CampaignEventObservationBatch(
        observations=tuple(normalized_observations),
        relevance_rejected_records=rejected_records,
    )


def build_campaign_event_observation(
    event: AttributedStructuredEvent,
    *,
    source: dict[str, Any],
    observed_at: str,
    evidence_url: str,
    candidate_registry_path: str | Path = _DEFAULT_CANDIDATE_REGISTRY,
    source_registry_path: str | Path = _DEFAULT_SOURCE_REGISTRY,
) -> dict[str, Any] | None:
    """Build one source-owned observation, or ``None`` for normal rejection."""

    batch = build_campaign_event_observations(
        (event,),
        source=source,
        observed_at=observed_at,
        evidence_url=evidence_url,
        candidate_registry_path=candidate_registry_path,
        source_registry_path=source_registry_path,
    )
    return batch.observations[0] if batch.observations else None
