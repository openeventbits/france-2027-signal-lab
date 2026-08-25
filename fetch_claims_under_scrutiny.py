#!/usr/bin/env python3
"""Collect professional fact-check reviews for the active candidate registry."""

from __future__ import annotations

import argparse
import hashlib
import json
import os
import re
import sys
import tempfile
import time
import unicodedata
from datetime import date, datetime, timezone
from pathlib import Path
from typing import Any, Callable, Iterable
from urllib.error import HTTPError, URLError
from urllib.parse import parse_qsl, urlencode, urlsplit, urlunsplit
from urllib.request import Request, urlopen
from zoneinfo import ZoneInfo

from candidate_candidacy_status import (
    CandidateCandidacyStatusError,
    active_candidate_ids,
    active_candidate_names,
    active_candidate_records,
    active_projection_provenance,
    load_candidate_candidacy_status,
    validate_candidate_candidacy_status,
)


SCHEMA_VERSION = 2
LEGACY_SCHEMA_VERSION = 1
DEFAULT_ARCHIVE_WINDOW_DAYS = 365
API_RETRIEVAL_BUFFER_DAYS = 380
API_PAGE_SIZE = 100
API_TIMEOUT_SECONDS = 20
API_MAX_ATTEMPTS = 3
API_ENDPOINT = "https://factchecktools.googleapis.com/v1alpha1/claims:search"

APPROVED_PUBLISHERS = {
    "factuel.afp.com": "AFP Factuel",
    "www.tf1info.fr": "TF1 Info",
    "www.franceinfo.fr": "franceinfo",
}

PUBLISHER_HOST_ALIASES = {
    "factuel.afp.com": "factuel.afp.com",
    "tf1info.fr": "www.tf1info.fr",
    "www.tf1info.fr": "www.tf1info.fr",
    "franceinfo.fr": "www.franceinfo.fr",
    "www.franceinfo.fr": "www.franceinfo.fr",
}

# Collector-specific aliases are search/matching assistance, never membership.
# Keep these keyed by the stable registry candidate ID.
CLAIMANT_ALIASES_BY_ID = {
    "francois-ruffin": ("Le député François Ruffin",),
}
FACT_CHECK_QUERY_ALIASES_BY_ID = CLAIMANT_ALIASES_BY_ID

AMBIGUOUS_CLAIMANTS = {
    "unknown",
    "not stated",
    "inconnu",
    "non indiqué",
    "non précisé",
    "non renseigné",
    "anonymous",
    "anonyme",
}

# Temporary read compatibility for the tracked schema-1 production snapshot.
# These fields are validated only; they never drive current query membership.
LEGACY_TOP_LEVEL_FIELDS = {
    "schema_version",
    "generated_at",
    "candidate_window_days",
    "archive_window_days",
    "candidate_roster",
    "counts",
    "reviews",
}
LEGACY_ROSTER_FIELDS = {"count", "candidates"}
LEGACY_CANDIDATE_FIELDS = {
    "candidate_id",
    "candidate_name",
    "last_qualifying_poll_date",
    "eligibility_basis",
}
TOP_LEVEL_FIELDS = {
    "schema_version",
    "generated_at",
    "archive_window_days",
    "candidate_query",
    "counts",
    "reviews",
}
CANDIDATE_QUERY_FIELDS = {
    "source",
    "rule",
    "status_as_of",
    "count",
    "candidate_ids",
    "candidate_names",
}
CANDIDATE_QUERY_PROVENANCE_FIELDS = {
    "source_revision_id",
    "source_revision_timestamp",
}
COUNTS_FIELDS = {
    "reviews",
    "by_associations",
    "about_associations",
    "candidates_covered",
    "publishers",
}
REVIEW_FIELDS = {
    "id",
    "review_url",
    "publisher_name",
    "publisher_host",
    "review_date",
    "claim_text",
    "claimant",
    "rating",
    "language",
    "candidate_associations",
}
ASSOCIATION_FIELDS = {"candidate_id", "candidate_name", "relationship"}

APOSTROPHES = {"’", "‘", "‛", "ʼ", "＇", "`", "´"}


class CollectorError(RuntimeError):
    """A safe, credential-free collector failure."""


def parse_iso_date(value: Any) -> date | None:
    if not isinstance(value, str) or not re.fullmatch(r"\d{4}-\d{2}-\d{2}", value):
        return None
    try:
        return date.fromisoformat(value)
    except ValueError:
        return None


def parse_review_date(value: Any) -> date | None:
    if not isinstance(value, str) or not value.strip():
        return None
    stripped = value.strip()
    direct = parse_iso_date(stripped)
    if direct is not None:
        return direct
    try:
        parsed = datetime.fromisoformat(stripped.replace("Z", "+00:00"))
    except ValueError:
        return None
    return parsed.date()


def load_candidacy_status(path: Path) -> dict[str, Any]:
    """Load the one canonical candidate authority with safe collector errors."""

    try:
        return load_candidate_candidacy_status(path)
    except OSError as error:
        raise CollectorError(
            f"could not read candidacy registry {path}: "
            f"{error.strerror or 'I/O error'}"
        ) from None
    except json.JSONDecodeError as error:
        raise CollectorError(
            f"could not parse candidacy registry {path}: "
            f"line {error.lineno}, column {error.colno}"
        ) from None
    except CandidateCandidacyStatusError as error:
        raise CollectorError(f"invalid candidacy registry: {error}") from None


def candidate_query_records(payload: Any) -> list[dict[str, Any]]:
    """Return the active query universe via the canonical shared helper."""

    try:
        return list(active_candidate_records(payload))
    except CandidateCandidacyStatusError as error:
        raise CollectorError(f"invalid candidacy registry: {error}") from None


def build_candidate_query(payload: Any) -> dict[str, Any]:
    """Describe the active query field without turning it into evidence."""

    records = candidate_query_records(payload)
    try:
        identifiers = active_candidate_ids(payload)
        names = active_candidate_names(payload)
    except CandidateCandidacyStatusError as error:
        raise CollectorError(f"invalid candidacy registry: {error}") from None
    if identifiers != [record["candidate_id"] for record in records] or names != [
        record["candidate_name"] for record in records
    ]:
        raise CollectorError("shared active candidate projections are inconsistent")
    query = {
        "source": "candidate_candidacy_status.json",
        "rule": "active_monitoring_field",
        "status_as_of": payload["status_as_of"],
        "count": len(records),
        "candidate_ids": identifiers,
        "candidate_names": names,
    }
    if payload.get("schema_version") == "2.0":
        try:
            provenance = active_projection_provenance(payload)
        except CandidateCandidacyStatusError as error:
            raise CollectorError(f"invalid candidacy registry: {error}") from None
        query["source_revision_id"] = provenance["source_revision_id"]
        query["source_revision_timestamp"] = provenance["source_revision_timestamp"]
    return query


def candidate_identity_names(candidate: dict[str, Any]) -> tuple[str, ...]:
    return (
        candidate["candidate_name"],
        *tuple(candidate.get("previous_names", [])),
    )


def fact_check_query_terms(candidate: dict[str, Any]) -> tuple[str, ...]:
    """Return reviewed API terms without affecting candidate membership."""

    terms = (
        candidate["candidate_name"],
        *FACT_CHECK_QUERY_ALIASES_BY_ID.get(candidate["candidate_id"], ()),
    )
    return tuple(dict.fromkeys(term.strip() for term in terms if term.strip()))


def normalize_comparison(value: str) -> str:
    normalized = unicodedata.normalize("NFKC", value)
    characters: list[str] = []
    for character in normalized:
        if character in APOSTROPHES:
            character = "'"
        category = unicodedata.category(character)
        if character.isspace() or category[0] in {"P", "S", "C"} and character != "'":
            characters.append(" ")
        else:
            characters.append(character.casefold())
    return " ".join("".join(characters).split())


def comparison_tokens(value: str) -> tuple[str, ...]:
    normalized = unicodedata.normalize("NFKC", value).casefold()
    tokens: list[str] = []
    current: list[str] = []
    for character in normalized:
        category = unicodedata.category(character)
        if category[0] in {"L", "N", "M"}:
            current.append(character)
        elif current:
            tokens.append("".join(current))
            current = []
    if current:
        tokens.append("".join(current))
    return tuple(tokens)


def contains_complete_name(claim_text: str, candidate_name: str) -> bool:
    haystack = comparison_tokens(claim_text)
    needle = comparison_tokens(candidate_name)
    if not needle or len(needle) > len(haystack):
        return False
    return any(
        haystack[index : index + len(needle)] == needle
        for index in range(len(haystack) - len(needle) + 1)
    )


NORMALIZED_AMBIGUOUS_CLAIMANTS = {
    normalize_comparison(value) for value in AMBIGUOUS_CLAIMANTS
}


def classify_candidate_associations(
    claim_text: str,
    claimant: str,
    candidates: Iterable[dict[str, Any]],
) -> tuple[list[dict[str, str]], list[dict[str, str]]]:
    claimant_normalized = normalize_comparison(claimant)
    claimant_usable = bool(claimant_normalized) and (
        claimant_normalized not in NORMALIZED_AMBIGUOUS_CLAIMANTS
    )
    associations: list[dict[str, str]] = []
    unresolved: list[dict[str, str]] = []

    for candidate in candidates:
        candidate_name = candidate["candidate_name"]
        identity_names = candidate_identity_names(candidate)
        accepted_claimants = {
            normalize_comparison(identity_name) for identity_name in identity_names
        }
        accepted_claimants.update(
            normalize_comparison(alias)
            for alias in CLAIMANT_ALIASES_BY_ID.get(candidate["candidate_id"], ())
        )
        if claimant_normalized in accepted_claimants:
            associations.append(
                {
                    "candidate_id": candidate["candidate_id"],
                    "candidate_name": candidate_name,
                    "relationship": "by",
                }
            )
            continue

        if not any(
            contains_complete_name(claim_text, identity_name)
            for identity_name in identity_names
        ):
            continue
        if not claimant_usable:
            unresolved.append(
                {
                    "candidate_id": candidate["candidate_id"],
                    "candidate_name": candidate_name,
                    "reason": "relationship_unresolved",
                }
            )
            continue
        if any(
            contains_complete_name(claimant, identity_name)
            for identity_name in identity_names
        ):
            unresolved.append(
                {
                    "candidate_id": candidate["candidate_id"],
                    "candidate_name": candidate_name,
                    "reason": "relationship_unresolved",
                }
            )
            continue
        associations.append(
            {
                "candidate_id": candidate["candidate_id"],
                "candidate_name": candidate_name,
                "relationship": "about",
            }
        )

    relationship_order = {"by": 0, "about": 1}
    associations.sort(
        key=lambda item: (
            relationship_order[item["relationship"]],
            item["candidate_name"].casefold(),
            item["candidate_id"],
        )
    )
    unresolved.sort(key=lambda item: (item["candidate_name"].casefold(), item["candidate_id"]))
    return associations, unresolved


def normalize_review_url(value: Any) -> tuple[str, str] | None:
    if not isinstance(value, str) or not value.strip():
        return None
    try:
        parsed = urlsplit(value.strip())
        port = parsed.port
    except ValueError:
        return None
    scheme = parsed.scheme.lower()
    hostname = (parsed.hostname or "").lower()
    if scheme not in {"http", "https"} or not hostname or parsed.username is not None:
        return None
    if parsed.password is not None:
        return None

    hostname = PUBLISHER_HOST_ALIASES.get(hostname, hostname)

    if port is None or (scheme == "http" and port == 80) or (scheme == "https" and port == 443):
        netloc = hostname
    else:
        netloc = f"{hostname}:{port}"

    retained = [
        (key, value)
        for key, value in parse_qsl(parsed.query, keep_blank_values=True)
        if not key.casefold().startswith("utm_") and key.casefold() != "fbclid"
    ]
    retained.sort(key=lambda pair: (pair[0], pair[1]))
    normalized = urlunsplit(
        (scheme, netloc, parsed.path or "/", urlencode(retained, doseq=True), "")
    )
    return normalized, hostname


def stable_review_id(normalized_url: str) -> str:
    return hashlib.sha256(normalized_url.encode("utf-8")).hexdigest()


def _fetch_json_page(
    parameters: list[tuple[str, str]],
    api_key: str,
    opener: Callable[..., Any],
    sleeper: Callable[[float], None],
) -> dict[str, Any]:
    request = Request(
        f"{API_ENDPOINT}?{urlencode(parameters)}",
        headers={"Accept": "application/json", "X-Goog-Api-Key": api_key},
    )
    for attempt in range(1, API_MAX_ATTEMPTS + 1):
        try:
            with opener(request, timeout=API_TIMEOUT_SECONDS) as response:
                payload = response.read()
            try:
                decoded = json.loads(payload.decode("utf-8"))
            except (UnicodeDecodeError, json.JSONDecodeError):
                raise CollectorError("Fact Check API returned malformed JSON") from None
            if not isinstance(decoded, dict):
                raise CollectorError("Fact Check API response must be an object")
            return decoded
        except HTTPError as error:
            transient = error.code == 429 or 500 <= error.code <= 599
            if not transient or attempt == API_MAX_ATTEMPTS:
                raise CollectorError(
                    f"Fact Check API request failed with HTTP status {error.code}"
                ) from None
        except URLError:
            if attempt == API_MAX_ATTEMPTS:
                raise CollectorError("Fact Check API request failed after retries") from None
        except TimeoutError:
            if attempt == API_MAX_ATTEMPTS:
                raise CollectorError("Fact Check API request timed out after retries") from None
        sleeper(float(2 ** (attempt - 1)))
    raise AssertionError("unreachable")


def fetch_candidate_claims(
    candidate_name: str,
    api_key: str,
    opener: Callable[..., Any] = urlopen,
    sleeper: Callable[[float], None] = time.sleep,
) -> tuple[list[dict[str, Any]], int]:
    claims: list[dict[str, Any]] = []
    page_token: str | None = None
    seen_tokens: set[str] = set()
    pages = 0

    while True:
        parameters = [
            ("query", candidate_name),
            ("languageCode", "fr"),
            ("maxAgeDays", str(API_RETRIEVAL_BUFFER_DAYS)),
            ("pageSize", str(API_PAGE_SIZE)),
        ]
        if page_token is not None:
            if page_token in seen_tokens:
                raise CollectorError(f"pagination loop for candidate {candidate_name!r}")
            seen_tokens.add(page_token)
            parameters.append(("pageToken", page_token))

        response = _fetch_json_page(parameters, api_key, opener, sleeper)
        pages += 1
        page_claims = response.get("claims", [])
        if not isinstance(page_claims, list):
            raise CollectorError("Fact Check API claims field must be an array")
        if any(not isinstance(claim, dict) for claim in page_claims):
            raise CollectorError("Fact Check API returned a non-object claim")
        claims.extend(page_claims)

        next_token = response.get("nextPageToken")
        if next_token is None or next_token == "":
            break
        if not isinstance(next_token, str):
            raise CollectorError("Fact Check API nextPageToken must be a string")
        if next_token == page_token or next_token in seen_tokens:
            raise CollectorError(f"pagination loop for candidate {candidate_name!r}")
        page_token = next_token

    return claims, pages


def _diagnostic_review(reference: str, reason: str, **extra: Any) -> dict[str, Any]:
    diagnostic = {"reference": reference, "reason": reason}
    diagnostic.update(extra)
    return diagnostic


def flatten_claims(
    claims: Iterable[dict[str, Any]],
    candidates: list[dict[str, Any]],
    as_of: date,
    archive_window_days: int,
    diagnostics: dict[str, Any],
) -> list[dict[str, Any]]:
    if archive_window_days < 0:
        raise CollectorError("archive window must be nonnegative")
    records: dict[str, dict[str, Any]] = {}
    duplicate_instances = 0

    for claim_index, claim in enumerate(claims):
        claim_text_value = claim.get("text", "")
        claimant_value = claim.get("claimant", "")
        claim_text = claim_text_value.strip() if isinstance(claim_text_value, str) else ""
        claimant = claimant_value.strip() if isinstance(claimant_value, str) else ""
        reviews = claim.get("claimReview", [])
        if not isinstance(reviews, list):
            raise CollectorError("Fact Check API claimReview field must be an array")
        for review_index, review in enumerate(reviews):
            reference = f"claim[{claim_index}].claimReview[{review_index}]"
            if not isinstance(review, dict):
                diagnostics["invalid_reviews"].append(
                    _diagnostic_review(reference, "review_not_object")
                )
                continue

            normalized_url = normalize_review_url(review.get("url"))
            if normalized_url is None:
                diagnostics["invalid_reviews"].append(
                    _diagnostic_review(reference, "invalid_review_url")
                )
                continue
            review_url, publisher_host = normalized_url
            publisher_name = APPROVED_PUBLISHERS.get(publisher_host)
            if publisher_name is None:
                diagnostics["excluded_unknown_hosts"].append(
                    _diagnostic_review(reference, "unknown_publisher_host", host=publisher_host)
                )
                continue

            parsed_review_date = parse_review_date(review.get("reviewDate"))
            if parsed_review_date is None:
                diagnostics["invalid_reviews"].append(
                    _diagnostic_review(reference, "invalid_review_date", review_url=review_url)
                )
                continue
            instance_age_days = (as_of - parsed_review_date).days
            if 0 <= instance_age_days <= archive_window_days:
                _associations, instance_unresolved = classify_candidate_associations(
                    claim_text, claimant, candidates
                )
                for item in instance_unresolved:
                    diagnostics["unresolved_associations"].append(
                        {"review_url": review_url, **item}
                    )
            rating_value = review.get("textualRating", "")
            rating = rating_value.strip() if isinstance(rating_value, str) else ""
            core = {
                "claim_text": claim_text,
                "claimant": claimant,
                "review_date": parsed_review_date.isoformat(),
                "rating": rating,
                "publisher_name": publisher_name,
                "publisher_host": publisher_host,
            }
            existing = records.get(review_url)
            if existing is None:
                existing = {
                    "id": stable_review_id(review_url),
                    "review_url": review_url,
                    **core,
                }
                records[review_url] = existing
            else:
                duplicate_instances += 1
                for field, incoming in core.items():
                    current = existing[field]
                    if current and incoming and current != incoming:
                        raise CollectorError(
                            "conflicting duplicate review core field "
                            f"{field!r} for {review_url}"
                        )
                    if not current and incoming:
                        existing[field] = incoming

    public_reviews: list[dict[str, Any]] = []
    for record in records.values():
        age_days = (as_of - date.fromisoformat(record["review_date"])).days
        if age_days < 0 or age_days > archive_window_days:
            diagnostics["invalid_reviews"].append(
                _diagnostic_review(
                    record["review_url"],
                    "outside_archive_window",
                    review_url=record["review_url"],
                )
            )
            continue
        associations, _unresolved = classify_candidate_associations(
            record["claim_text"], record["claimant"], candidates
        )
        missing = [
            field for field in ("claim_text", "claimant", "rating") if not record[field]
        ]
        if missing:
            diagnostics["invalid_reviews"].append(
                _diagnostic_review(
                    record["review_url"], "missing_public_core_fields", fields=missing
                )
            )
            continue
        if not associations:
            continue
        public_reviews.append(
            {
                "id": record["id"],
                "review_url": record["review_url"],
                "publisher_name": record["publisher_name"],
                "publisher_host": record["publisher_host"],
                "review_date": record["review_date"],
                "claim_text": record["claim_text"],
                "claimant": record["claimant"],
                "rating": record["rating"],
                "language": "fr",
                "candidate_associations": associations,
            }
        )

    public_reviews.sort(
        key=lambda item: (
            -date.fromisoformat(item["review_date"]).toordinal(),
            item["publisher_name"],
            item["review_url"],
        )
    )
    diagnostics["deduplication"] = {
        "canonical_reviews_seen": len(records),
        "duplicate_instances_merged": duplicate_instances,
    }
    return public_reviews


def compute_counts(reviews: Iterable[dict[str, Any]]) -> dict[str, int]:
    review_list = list(reviews)
    associations = [
        association
        for review in review_list
        for association in review["candidate_associations"]
    ]
    return {
        "reviews": len(review_list),
        "by_associations": sum(item["relationship"] == "by" for item in associations),
        "about_associations": sum(
            item["relationship"] == "about" for item in associations
        ),
        "candidates_covered": len({item["candidate_id"] for item in associations}),
        "publishers": len({review["publisher_host"] for review in review_list}),
    }


def generated_at_value(as_of_argument: str | None) -> str:
    if as_of_argument is not None:
        return f"{as_of_argument}T00:00:00Z"
    return datetime.now(timezone.utc).replace(microsecond=0).isoformat().replace("+00:00", "Z")


def build_public_bundle(
    candidacy_payload: Any,
    reviews: list[dict[str, Any]],
    archive_window_days: int,
    generated_at: str,
) -> dict[str, Any]:
    return {
        "schema_version": SCHEMA_VERSION,
        "generated_at": generated_at,
        "archive_window_days": archive_window_days,
        "candidate_query": build_candidate_query(candidacy_payload),
        "counts": compute_counts(reviews),
        "reviews": reviews,
    }


def _require_exact_fields(value: dict[str, Any], expected: set[str], context: str) -> None:
    actual = set(value)
    if actual != expected:
        raise CollectorError(
            f"{context} fields differ: missing={sorted(expected - actual)}, "
            f"extra={sorted(actual - expected)}"
        )


def _validate_generated_at(value: Any) -> None:
    if not isinstance(value, str):
        raise CollectorError("generated_at must be an ISO-8601 UTC string")
    try:
        parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
    except ValueError:
        raise CollectorError("generated_at must be an ISO-8601 UTC string") from None
    if parsed.tzinfo is None or parsed.utcoffset() != timezone.utc.utcoffset(None):
        raise CollectorError("generated_at must use UTC")


def _validate_reviews(
    bundle: dict[str, Any],
    *,
    association_lookup: dict[str, str] | None,
    association_error: str,
) -> None:
    counts = bundle["counts"]
    if not isinstance(counts, dict):
        raise CollectorError("counts must be an object")
    _require_exact_fields(counts, COUNTS_FIELDS, "counts")
    if any(type(value) is not int or value < 0 for value in counts.values()):
        raise CollectorError("all declared counts must be nonnegative integers")
    reviews = bundle["reviews"]
    if not isinstance(reviews, list):
        raise CollectorError("reviews must be an array")

    seen_ids: set[str] = set()
    seen_urls: set[str] = set()
    expected_order: list[tuple[int, str, str]] = []
    for review_index, review in enumerate(reviews):
        if not isinstance(review, dict):
            raise CollectorError(f"review {review_index} must be an object")
        _require_exact_fields(review, REVIEW_FIELDS, f"review {review_index}")
        normalized = normalize_review_url(review["review_url"])
        if normalized is None or normalized[0] != review["review_url"]:
            raise CollectorError(f"review {review_index} URL is not normalized HTTP(S)")
        normalized_url, hostname = normalized
        if hostname not in APPROVED_PUBLISHERS:
            raise CollectorError(f"review {review_index} publisher host is not approved")
        if review["publisher_host"] != hostname:
            raise CollectorError(f"review {review_index} publisher host does not match URL")
        if review["publisher_name"] != APPROVED_PUBLISHERS[hostname]:
            raise CollectorError(f"review {review_index} publisher name is not canonical")
        review_id = review["id"]
        if not isinstance(review_id, str) or review_id != stable_review_id(normalized_url):
            raise CollectorError(f"review {review_index} id is not its stable URL hash")
        if review_id in seen_ids or normalized_url in seen_urls:
            raise CollectorError("review ids and normalized URLs must be unique")
        seen_ids.add(review_id)
        seen_urls.add(normalized_url)
        parsed_date = parse_iso_date(review["review_date"])
        if parsed_date is None:
            raise CollectorError(f"review {review_index} has an invalid review_date")
        expected_order.append((-parsed_date.toordinal(), review["publisher_name"], normalized_url))
        for field in ("claim_text", "claimant", "rating"):
            if not isinstance(review[field], str) or not review[field].strip():
                raise CollectorError(f"review {review_index} has an empty {field}")
        if review["language"] != "fr":
            raise CollectorError(f"review {review_index} language must equal fr")

        associations = review["candidate_associations"]
        if not isinstance(associations, list) or not associations:
            raise CollectorError(f"review {review_index} must have candidate associations")
        seen_candidate_ids: set[str] = set()
        association_order: list[tuple[int, str, str]] = []
        for association_index, association in enumerate(associations):
            if not isinstance(association, dict):
                raise CollectorError(
                    f"review {review_index} association {association_index} must be an object"
                )
            _require_exact_fields(
                association,
                ASSOCIATION_FIELDS,
                f"review {review_index} association {association_index}",
            )
            candidate_id = association["candidate_id"]
            candidate_name = association["candidate_name"]
            relationship = association["relationship"]
            if not isinstance(candidate_id, str) or not candidate_id:
                raise CollectorError("associated candidate id must be nonempty")
            if not isinstance(candidate_name, str) or not candidate_name.strip():
                raise CollectorError("associated candidate name must be nonempty")
            if relationship not in {"by", "about"}:
                raise CollectorError("public relationship must be by or about")
            if (
                association_lookup is not None
                and association_lookup.get(candidate_id) != candidate_name
            ):
                raise CollectorError(association_error)
            if candidate_id in seen_candidate_ids:
                raise CollectorError("a review cannot associate the same candidate twice")
            seen_candidate_ids.add(candidate_id)
            association_order.append(
                (0 if relationship == "by" else 1, candidate_name.casefold(), candidate_id)
            )
        if association_order != sorted(association_order):
            raise CollectorError("candidate associations are not deterministically sorted")

    if expected_order != sorted(expected_order):
        raise CollectorError("reviews are not deterministically sorted")
    if counts != compute_counts(reviews):
        raise CollectorError("declared counts do not match public records")


def _validate_legacy_public_bundle(
    bundle: dict[str, Any],
    expected_candidate_window_days: int | None,
    expected_archive_window_days: int,
) -> None:
    _require_exact_fields(bundle, LEGACY_TOP_LEVEL_FIELDS, "top-level")
    candidate_window_days = bundle["candidate_window_days"]
    if type(candidate_window_days) is not int or candidate_window_days < 0:
        raise CollectorError("candidate_window_days must be a nonnegative integer")
    if (
        expected_candidate_window_days is not None
        and candidate_window_days != expected_candidate_window_days
    ):
        raise CollectorError("candidate_window_days has an unexpected value")
    if bundle["archive_window_days"] != expected_archive_window_days:
        raise CollectorError("archive_window_days has an unexpected value")
    _validate_generated_at(bundle["generated_at"])

    roster_wrapper = bundle["candidate_roster"]
    if not isinstance(roster_wrapper, dict):
        raise CollectorError("candidate_roster must be an object")
    _require_exact_fields(roster_wrapper, LEGACY_ROSTER_FIELDS, "candidate_roster")
    roster = roster_wrapper["candidates"]
    if not isinstance(roster, list):
        raise CollectorError("candidate_roster.candidates must be an array")
    if type(roster_wrapper["count"]) is not int or roster_wrapper["count"] != len(roster):
        raise CollectorError("candidate roster count does not match its array")

    roster_lookup: dict[str, str] = {}
    for index, candidate in enumerate(roster):
        if not isinstance(candidate, dict):
            raise CollectorError(f"candidate roster item {index} must be an object")
        _require_exact_fields(
            candidate, LEGACY_CANDIDATE_FIELDS, f"candidate roster item {index}"
        )
        candidate_id = candidate["candidate_id"]
        candidate_name = candidate["candidate_name"]
        if not isinstance(candidate_id, str) or not candidate_id:
            raise CollectorError(f"candidate roster item {index} has an empty id")
        if not isinstance(candidate_name, str) or not candidate_name.strip():
            raise CollectorError(f"candidate roster item {index} has an empty name")
        if candidate_id in roster_lookup:
            raise CollectorError(f"duplicate candidate id: {candidate_id}")
        if parse_iso_date(candidate["last_qualifying_poll_date"]) is None:
            raise CollectorError(f"candidate roster item {index} has an invalid date")
        if candidate["eligibility_basis"] not in {"publication_date", "fieldwork_end"}:
            raise CollectorError(f"candidate roster item {index} has an invalid basis")
        roster_lookup[candidate_id] = candidate_name
    _validate_reviews(
        bundle,
        association_lookup=roster_lookup,
        association_error="associated candidate is not in the eligible legacy roster",
    )


def validate_public_bundle(
    bundle: Any,
    expected_candidate_window_days: int | None = 45,
    expected_archive_window_days: int = DEFAULT_ARCHIVE_WINDOW_DAYS,
    candidacy_payload: Any | None = None,
) -> None:
    if not isinstance(bundle, dict):
        raise CollectorError("public output must be an object")
    schema_version = bundle.get("schema_version")
    if schema_version == LEGACY_SCHEMA_VERSION:
        _validate_legacy_public_bundle(
            bundle,
            expected_candidate_window_days,
            expected_archive_window_days,
        )
        return
    if type(schema_version) is not int or schema_version != SCHEMA_VERSION:
        raise CollectorError("schema_version must equal 1 or 2")

    _require_exact_fields(bundle, TOP_LEVEL_FIELDS, "top-level")
    if bundle["archive_window_days"] != expected_archive_window_days:
        raise CollectorError("archive_window_days has an unexpected value")
    _validate_generated_at(bundle["generated_at"])
    query = bundle["candidate_query"]
    if not isinstance(query, dict):
        raise CollectorError("candidate_query must be an object")
    _require_exact_fields(
        query,
        CANDIDATE_QUERY_FIELDS | CANDIDATE_QUERY_PROVENANCE_FIELDS,
        "candidate_query",
    )
    revision_id = query["source_revision_id"]
    if type(revision_id) is not int or revision_id <= 0:
        raise CollectorError(
            "candidate_query.source_revision_id must be a positive integer"
        )
    revision_timestamp = query["source_revision_timestamp"]
    if not isinstance(revision_timestamp, str):
        raise CollectorError(
            "candidate_query.source_revision_timestamp must be an ISO-8601 UTC string"
        )
    try:
        parsed_revision_timestamp = datetime.fromisoformat(
            revision_timestamp.replace("Z", "+00:00")
        )
    except ValueError:
        raise CollectorError(
            "candidate_query.source_revision_timestamp must be an ISO-8601 UTC string"
        ) from None
    if (
        parsed_revision_timestamp.tzinfo is None
        or parsed_revision_timestamp.utcoffset()
        != timezone.utc.utcoffset(None)
    ):
        raise CollectorError(
            "candidate_query.source_revision_timestamp must use UTC"
        )
    if query["source"] != "candidate_candidacy_status.json":
        raise CollectorError("candidate_query.source is not canonical")
    if query["rule"] != "active_monitoring_field":
        raise CollectorError("candidate_query.rule is not canonical")
    if parse_iso_date(query["status_as_of"]) is None:
        raise CollectorError("candidate_query.status_as_of is invalid")
    identifiers = query["candidate_ids"]
    names = query["candidate_names"]
    if not isinstance(identifiers, list) or not isinstance(names, list):
        raise CollectorError("candidate query identities must be arrays")
    if any(not isinstance(value, str) or not value for value in identifiers):
        raise CollectorError("candidate query ids must be nonempty strings")
    if any(not isinstance(value, str) or not value.strip() for value in names):
        raise CollectorError("candidate query names must be nonempty strings")
    if len(set(identifiers)) != len(identifiers):
        raise CollectorError("candidate query ids must be unique")
    if type(query["count"]) is not int or query["count"] != len(identifiers):
        raise CollectorError("candidate query count does not match candidate ids")
    if len(names) != query["count"]:
        raise CollectorError("candidate query names do not match candidate count")

    association_lookup: dict[str, str] | None = None
    if candidacy_payload is not None:
        try:
            validate_candidate_candidacy_status(candidacy_payload)
            expected_query = build_candidate_query(candidacy_payload)
        except CandidateCandidacyStatusError as error:
            raise CollectorError(f"invalid candidacy registry: {error}") from None
        if query != expected_query:
            raise CollectorError("candidate query does not match active registry projection")
        association_lookup = {
            candidate["candidate_id"]: candidate["candidate_name"]
            for candidate in candidacy_payload["candidates"]
        }
    _validate_reviews(
        bundle,
        association_lookup=association_lookup,
        association_error="associated candidate is not in the canonical registry",
    )


def _canonicalize_existing_review(
    review: dict[str, Any],
    candidacy_payload: dict[str, Any],
) -> dict[str, Any]:
    by_id = {
        candidate["candidate_id"]: candidate
        for candidate in candidacy_payload["candidates"]
    }
    canonical_associations: list[dict[str, str]] = []
    for association in review["candidate_associations"]:
        candidate = by_id.get(association["candidate_id"])
        if candidate is None:
            raise CollectorError(
                "existing claim association candidate is absent from canonical registry"
            )
        allowed_names = {
            normalize_comparison(name) for name in candidate_identity_names(candidate)
        }
        if normalize_comparison(association["candidate_name"]) not in allowed_names:
            raise CollectorError(
                "existing claim association conflicts with canonical registry identity"
            )
        canonical_associations.append(
            {
                "candidate_id": candidate["candidate_id"],
                "candidate_name": candidate["candidate_name"],
                "relationship": association["relationship"],
            }
        )
    canonical_associations.sort(
        key=lambda item: (
            0 if item["relationship"] == "by" else 1,
            item["candidate_name"].casefold(),
            item["candidate_id"],
        )
    )
    return {**review, "candidate_associations": canonical_associations}


# Claims is an evidence archive, not the candidate authority: accepted reviews
# survive query-universe lifecycle changes while their registry identity remains valid.
def load_existing_reviews(
    path: Path | None,
    candidacy_payload: dict[str, Any],
    as_of: date,
    archive_window_days: int,
) -> list[dict[str, Any]]:
    if path is None or not path.exists():
        return []
    try:
        bundle = json.loads(path.read_text(encoding="utf-8"))
    except OSError as error:
        raise CollectorError(
            f"could not read existing claims file {path}: {error.strerror or 'I/O error'}"
        ) from None
    except json.JSONDecodeError as error:
        raise CollectorError(
            f"could not parse existing claims file {path}: "
            f"line {error.lineno}, column {error.colno}"
        ) from None
    validate_public_bundle(
        bundle,
        expected_candidate_window_days=None,
        expected_archive_window_days=archive_window_days,
        candidacy_payload=None,
    )
    retained: list[dict[str, Any]] = []
    for review in bundle["reviews"]:
        review_date = date.fromisoformat(review["review_date"])
        age_days = (as_of - review_date).days
        if age_days < 0:
            raise CollectorError("existing claim review date is in the future")
        if age_days <= archive_window_days:
            retained.append(_canonicalize_existing_review(review, candidacy_payload))
    return retained


def merge_reviews(
    existing_reviews: Iterable[dict[str, Any]],
    fetched_reviews: Iterable[dict[str, Any]],
) -> list[dict[str, Any]]:
    """Merge evidence by canonical URL; newly fetched evidence wins."""

    merged = {review["review_url"]: review for review in existing_reviews}
    merged.update({review["review_url"]: review for review in fetched_reviews})
    result = list(merged.values())
    result.sort(
        key=lambda item: (
            -date.fromisoformat(item["review_date"]).toordinal(),
            item["publisher_name"],
            item["review_url"],
        )
    )
    return result


def semantic_public_content(bundle: dict[str, Any]) -> dict[str, Any]:
    return {**bundle, "generated_at": bundle["generated_at"][:10]}


def atomic_write_json(path: Path, payload: Any) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    descriptor, temporary_name = tempfile.mkstemp(
        prefix=f".{path.name}.", suffix=".tmp", dir=path.parent
    )
    try:
        with os.fdopen(descriptor, "w", encoding="utf-8", newline="\n") as handle:
            json.dump(payload, handle, ensure_ascii=False, indent=2)
            handle.write("\n")
            handle.flush()
            os.fsync(handle.fileno())
        os.replace(temporary_name, path)
    finally:
        temporary_path = Path(temporary_name)
        if temporary_path.exists():
            temporary_path.unlink()


def collect(
    candidacy_status_path: Path,
    output_path: Path,
    diagnostics_path: Path,
    archive_window_days: int,
    as_of: date,
    as_of_argument: str | None,
    existing_claims_path: Path | None = None,
) -> dict[str, Any]:
    resolved_candidacy = candidacy_status_path.resolve()
    resolved_output = output_path.resolve()
    resolved_diagnostics = diagnostics_path.resolve()
    if len({resolved_candidacy, resolved_output, resolved_diagnostics}) != 3:
        raise CollectorError(
            "candidacy registry, public output, and diagnostics paths must be distinct"
        )
    if existing_claims_path is not None and (
        existing_claims_path.resolve() == resolved_candidacy
        or existing_claims_path.resolve() == resolved_diagnostics
    ):
        raise CollectorError(
            "existing claims must be distinct from candidacy and diagnostics paths"
        )
    if archive_window_days < 0:
        raise CollectorError("archive window must be nonnegative")

    candidacy = load_candidacy_status(candidacy_status_path)
    active_candidates = candidate_query_records(candidacy)
    candidate_query = build_candidate_query(candidacy)
    identity_candidates = candidacy["candidates"]
    existing_reviews = load_existing_reviews(
        existing_claims_path,
        candidacy,
        as_of,
        archive_window_days,
    )
    diagnostics: dict[str, Any] = {
        "as_of": as_of.isoformat(),
        "candidate_source": candidate_query["source"],
        "candidate_rule": candidate_query["rule"],
        "candidate_status_as_of": candidate_query["status_as_of"],
        "candidate_query_count": candidate_query["count"],
        "candidate_query_ids": candidate_query["candidate_ids"],
        "candidate_query_names": candidate_query["candidate_names"],
        "candidate_source_provenance": candidacy.get("source"),
        "query_status": [],
        "excluded_unknown_hosts": [],
        "invalid_reviews": [],
        "unresolved_associations": [],
        "deduplication": {
            "canonical_reviews_seen": 0,
            "duplicate_instances_merged": 0,
        },
        "historical_evidence": {
            "retained_existing_reviews": len(existing_reviews),
            "fetched_reviews": 0,
            "merged_reviews": 0,
        },
        "final_counts": None,
    }

    all_claims: list[dict[str, Any]] = []
    if active_candidates:
        api_key = os.environ.get("GOOGLE_FACTCHECK_API_KEY")
        if not api_key:
            diagnostics["failure"] = "GOOGLE_FACTCHECK_API_KEY is not configured"
            atomic_write_json(diagnostics_path, diagnostics)
            raise CollectorError(
                "GOOGLE_FACTCHECK_API_KEY is required for a nonempty active query field"
            )
        for candidate in active_candidates:
            query_terms = fact_check_query_terms(candidate)
            candidate_claims: list[dict[str, Any]] = []
            pages = 0
            try:
                for query_term in query_terms:
                    claims, query_pages = fetch_candidate_claims(query_term, api_key)
                    candidate_claims.extend(claims)
                    pages += query_pages
            except CollectorError as error:
                diagnostics["query_status"].append(
                    {
                        "candidate_id": candidate["candidate_id"],
                        "candidate_name": candidate["candidate_name"],
                        "query_terms": list(query_terms),
                        "status": "failed",
                    }
                )
                diagnostics["failure"] = str(error)
                atomic_write_json(diagnostics_path, diagnostics)
                raise
            diagnostics["query_status"].append(
                {
                    "candidate_id": candidate["candidate_id"],
                    "candidate_name": candidate["candidate_name"],
                    "query_terms": list(query_terms),
                    "status": "ok",
                    "pages": pages,
                    "claims": len(candidate_claims),
                }
            )
            all_claims.extend(candidate_claims)

    fetched_reviews = flatten_claims(
        all_claims,
        identity_candidates,
        as_of,
        archive_window_days,
        diagnostics,
    )
    reviews = merge_reviews(existing_reviews, fetched_reviews)
    diagnostics["historical_evidence"] = {
        "retained_existing_reviews": len(existing_reviews),
        "fetched_reviews": len(fetched_reviews),
        "merged_reviews": len(reviews),
    }
    bundle = build_public_bundle(
        candidacy,
        reviews,
        archive_window_days,
        generated_at_value(as_of_argument),
    )
    validate_public_bundle(
        bundle,
        expected_archive_window_days=archive_window_days,
        candidacy_payload=candidacy,
    )
    diagnostics["final_counts"] = bundle["counts"]
    atomic_write_json(diagnostics_path, diagnostics)
    atomic_write_json(output_path, bundle)
    return bundle


def parse_args(argv: list[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description=(
            "Collect Google Fact Check Tools publisher reviews for the canonical "
            "active candidate registry."
        )
    )
    parser.add_argument(
        "--candidacy-status",
        type=Path,
        default=Path("candidate_candidacy_status.json"),
    )
    parser.add_argument(
        "--existing-claims",
        type=Path,
        default=Path("claims_under_scrutiny.json"),
        help="Existing accepted evidence to retain within the archive window",
    )
    parser.add_argument("--output", type=Path, default=Path("claims_under_scrutiny.json"))
    parser.add_argument(
        "--diagnostics-output", type=Path, default=Path("diagnostics.json")
    )
    parser.add_argument(
        "--archive-window-days", type=int, default=DEFAULT_ARCHIVE_WINDOW_DAYS
    )
    parser.add_argument(
        "--as-of",
        help="Use YYYY-MM-DD instead of today's date in Europe/Paris",
    )
    return parser.parse_args(argv)


def main(argv: list[str] | None = None) -> int:
    args = parse_args(argv)
    if args.as_of is not None:
        as_of = parse_iso_date(args.as_of)
        if as_of is None:
            print("error: --as-of must be a valid YYYY-MM-DD date", file=sys.stderr)
            return 2
    else:
        as_of = datetime.now(ZoneInfo("Europe/Paris")).date()
    try:
        bundle = collect(
            args.candidacy_status,
            args.output,
            args.diagnostics_output,
            args.archive_window_days,
            as_of,
            args.as_of,
            args.existing_claims,
        )
    except CollectorError as error:
        print(f"error: {error}", file=sys.stderr)
        return 1
    print(
        f"Wrote {bundle['counts']['reviews']} reviews while querying "
        f"{bundle['candidate_query']['count']} active candidates to {args.output}"
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
