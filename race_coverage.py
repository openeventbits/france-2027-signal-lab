"""Deterministic France 2027 Race Coverage story identity and inheritance.

The model is deliberately lexical, network-free, and candidate-independent at
the clustering layer.  A story is a complete-link cluster: every pair of
articles assigned to it must independently satisfy :func:`story_match`.
Qualification is a separate operation.  A non-direct article can inherit only
from a Phase 1C direct anchor in its own coherent story; promoted articles are
never used as anchors.
"""

from __future__ import annotations

import hashlib
import re
import unicodedata
from datetime import datetime, timezone
from functools import lru_cache
from typing import Any, Callable


STORY_MODEL_VERSION = "race-story-lexical-complete-link-v1"
STORY_MAX_HOURS = 48
STORY_MIN_SHARED_TOKENS = 4
STORY_MIN_JACCARD = 0.60
STORY_MIN_OVERLAP = 0.75
CANDIDATE_FREE_MIN_SHARED_TOKENS = 5
CANDIDATE_FREE_MIN_JACCARD = 0.72
CANDIDATE_FREE_MIN_OVERLAP = 0.85
EXCEPTIONAL_MIN_SHARED_TOKENS = 7
EXCEPTIONAL_MIN_JACCARD = 0.82
EXCEPTIONAL_MIN_OVERLAP = 0.90


# Fixed/versioned French function, reporting, and presidential-race boilerplate
# tokens.  There is intentionally no corpus-relative rarity feature.
STORY_STOPWORDS = frozenset({
    "afin", "ainsi", "alors", "apres", "article", "assure", "avec",
    "avant", "avoir", "chez", "comme", "contre", "dans", "depuis", "des",
    "dit", "elle", "elles", "entre", "etre", "fait", "font", "france",
    "francais", "francaise", "leur", "leurs", "mais", "meme", "moins",
    "notre", "nous", "par", "pas", "plus", "pour", "quand", "que", "quel",
    "quelle", "qui", "sans", "selon", "ses", "son", "sont", "sous", "sur",
    "tous", "tout", "toute", "une", "vers", "vous", "candidat",
    "candidate", "candidats", "candidates", "candidature", "campagne",
    "elysee", "election", "elections", "electoral", "electorale", "politique",
    "president", "presidente", "presidentiel", "presidentielle", "scrutin",
    "2027", "actualite", "direct", "edition", "exclusif", "info", "journal",
    "matinale", "podcast", "replay", "video",
})


TOKEN_PATTERN = re.compile(r"[a-z0-9]+")


def normalize_story_text(value: Any) -> str:
    text = unicodedata.normalize("NFKD", str(value or ""))
    text = "".join(character for character in text if not unicodedata.combining(character))
    return " ".join(TOKEN_PATTERN.findall(text.casefold()))


def candidate_name_tokens(candidate_names: list[str] | tuple[str, ...]) -> frozenset[str]:
    """Return the global monitored-name token removal set.

    Candidate order and article-local candidate attribution cannot affect this
    set.  All monitored candidate name tokens are removed from every headline.
    """

    return frozenset(
        token
        for name in candidate_names
        for token in normalize_story_text(name).split()
        if len(token) >= 2
    )


@lru_cache(maxsize=None)
def _cached_story_features(
    normalized_headline: str,
    global_candidate_tokens: frozenset[str],
) -> tuple[frozenset[str], frozenset[tuple[str, str]], frozenset[str]]:
    ordered = tuple(
        token
        for token in normalized_headline.split()
        if (
            len(token) >= 3
            and not token.isdigit()
            and token not in STORY_STOPWORDS
            and token not in global_candidate_tokens
        )
    )
    tokens = frozenset(ordered)
    bigrams = frozenset(zip(ordered, ordered[1:]))
    distinctive = frozenset(token for token in tokens if len(token) >= 7)
    return tokens, bigrams, distinctive


def story_features(headline: Any, global_candidate_tokens: frozenset[str]) -> dict[str, Any]:
    tokens, bigrams, distinctive = _cached_story_features(
        normalize_story_text(headline),
        global_candidate_tokens,
    )
    return {
        "tokens": tokens,
        "bigrams": bigrams,
        "distinctive": distinctive,
    }


def _published(value: Any) -> datetime | None:
    if isinstance(value, datetime):
        parsed = value
    elif isinstance(value, str) and value.strip():
        try:
            parsed = datetime.fromisoformat(value.strip().replace("Z", "+00:00"))
        except ValueError:
            return None
    else:
        return None
    if parsed.tzinfo is None or parsed.utcoffset() is None:
        return None
    return parsed.astimezone(timezone.utc)


def _candidate_set(record: dict[str, Any]) -> frozenset[str]:
    values = record.get("candidate_names")
    if values is None:
        values = record.get("candidates", [])
    return frozenset(str(value).strip() for value in values or [] if str(value).strip())


def story_match(
    left: dict[str, Any],
    right: dict[str, Any],
    *,
    global_candidate_tokens: frozenset[str],
) -> dict[str, Any] | None:
    """Return transparent match evidence when two articles are the same story."""

    left_time = _published(left.get("published_at"))
    right_time = _published(right.get("published_at"))
    if left_time is None or right_time is None:
        return None
    hours_apart = abs((left_time - right_time).total_seconds()) / 3600
    if hours_apart > STORY_MAX_HOURS:
        return None

    left_features = story_features(left.get("headline"), global_candidate_tokens)
    right_features = story_features(right.get("headline"), global_candidate_tokens)
    left_tokens = left_features["tokens"]
    right_tokens = right_features["tokens"]
    shared = left_tokens & right_tokens
    if not left_tokens or not right_tokens:
        return None

    union = left_tokens | right_tokens
    jaccard = len(shared) / len(union)
    overlap = len(shared) / min(len(left_tokens), len(right_tokens))
    shared_bigrams = left_features["bigrams"] & right_features["bigrams"]
    shared_distinctive = (
        left_features["distinctive"] & right_features["distinctive"]
    )

    # Stable event/entity evidence: at least one normalized headline bigram,
    # or two fixed-rule distinctive (7+ character) tokens must be shared.
    event_evidence = bool(shared_bigrams) or len(shared_distinctive) >= 2
    if not event_evidence:
        return None

    left_candidates = _candidate_set(left)
    right_candidates = _candidate_set(right)
    one_candidate_free = bool(left_candidates) != bool(right_candidates)
    disjoint_candidates = bool(
        left_candidates and right_candidates and not (left_candidates & right_candidates)
    )

    minimum_shared = STORY_MIN_SHARED_TOKENS
    minimum_jaccard = STORY_MIN_JACCARD
    minimum_overlap = STORY_MIN_OVERLAP
    rule = "standard"
    if one_candidate_free:
        minimum_shared = CANDIDATE_FREE_MIN_SHARED_TOKENS
        minimum_jaccard = CANDIDATE_FREE_MIN_JACCARD
        minimum_overlap = CANDIDATE_FREE_MIN_OVERLAP
        rule = "candidate_free_strict"
    elif disjoint_candidates:
        minimum_shared = EXCEPTIONAL_MIN_SHARED_TOKENS
        minimum_jaccard = EXCEPTIONAL_MIN_JACCARD
        minimum_overlap = EXCEPTIONAL_MIN_OVERLAP
        rule = "exceptional_disjoint_candidates"

    if (
        len(shared) < minimum_shared
        or jaccard < minimum_jaccard
        or overlap < minimum_overlap
    ):
        return None
    if disjoint_candidates and len(shared_bigrams) < 2:
        return None

    return {
        "rule": rule,
        "hours_apart": round(hours_apart, 3),
        "shared_tokens": sorted(shared),
        "shared_token_count": len(shared),
        "jaccard": round(jaccard, 3),
        "overlap": round(overlap, 3),
        "shared_bigram_count": len(shared_bigrams),
    }


def _record_key(record: dict[str, Any]) -> tuple[Any, ...]:
    published = _published(record.get("published_at"))
    return (
        published.timestamp() if published is not None else float("inf"),
        str(record.get("id") or ""),
        normalize_story_text(record.get("headline")),
    )


def _story_id(seed: dict[str, Any]) -> str:
    identity = str(seed.get("id") or "").strip()
    if not identity:
        identity = "|".join((
            normalize_story_text(seed.get("headline")),
            str(seed.get("published_at") or ""),
            str(seed.get("publisher") or ""),
        ))
    digest = hashlib.sha256(
        f"{STORY_MODEL_VERSION}|{identity}".encode("utf-8")
    ).hexdigest()[:16]
    return f"story-{digest}"


def build_story_clusters(
    records: list[dict[str, Any]],
    candidate_names: list[str] | tuple[str, ...],
) -> list[dict[str, Any]]:
    """Assign complete-link stories deterministically and input-order independently."""

    global_tokens = candidate_name_tokens(candidate_names)
    clusters: list[dict[str, Any]] = []
    clusters_by_number: dict[int, dict[str, Any]] = {}
    token_index: dict[str, set[int]] = {}
    for record in sorted(records, key=_record_key):
        compatible: list[dict[str, Any]] = []
        features = story_features(record.get("headline"), global_tokens)
        candidate_counts: dict[int, int] = {}
        for token in features["tokens"]:
            for cluster_number in token_index.get(token, set()):
                candidate_counts[cluster_number] = (
                    candidate_counts.get(cluster_number, 0) + 1
                )
        candidate_numbers = sorted(
            cluster_number
            for cluster_number, shared_count in candidate_counts.items()
            if shared_count >= STORY_MIN_SHARED_TOKENS
        )
        for cluster_number in candidate_numbers:
            cluster = clusters_by_number[cluster_number]
            record_time = _published(record.get("published_at"))
            first_time = _published(cluster["records"][0].get("published_at"))
            if (
                record_time is None
                or first_time is None
                or (record_time - first_time).total_seconds()
                > STORY_MAX_HOURS * 3600
            ):
                continue
            if all(
                story_match(
                    record,
                    member,
                    global_candidate_tokens=global_tokens,
                ) is not None
                for member in cluster["records"]
            ):
                compatible.append(cluster)
        if compatible:
            selected = min(compatible, key=lambda value: value["story_id"])
            selected["records"].append(record)
        else:
            selected = {
                "story_id": _story_id(record),
                "records": [record],
                "_cluster_number": len(clusters),
            }
            clusters.append(selected)
            clusters_by_number[selected["_cluster_number"]] = selected
        for token in features["tokens"]:
            token_index.setdefault(token, set()).add(
                selected["_cluster_number"]
            )

    for cluster in clusters:
        cluster["records"].sort(key=_record_key)
        cluster.pop("_cluster_number", None)
    clusters.sort(key=lambda value: value["story_id"])
    return clusters


def qualify_race_coverage(
    records: list[dict[str, Any]],
    candidate_names: list[str] | tuple[str, ...],
    *,
    hard_veto: Callable[[dict[str, Any]], bool] | None = None,
) -> list[dict[str, Any]]:
    """Return direct and direct-anchor-inherited Race Coverage records.

    Input records carry ``direct_qualification`` as Phase 1C output.  Every
    promoted record must independently match a direct record; a promoted peer
    is never eligible to anchor another promotion.
    """

    clusters = build_story_clusters(records, candidate_names)
    global_tokens = candidate_name_tokens(candidate_names)
    qualified: list[dict[str, Any]] = []
    for cluster in clusters:
        direct_anchors = [
            record for record in cluster["records"]
            if record.get("direct_qualification") is not None
        ]
        for record in cluster["records"]:
            direct = record.get("direct_qualification")
            if direct is not None:
                output = dict(record)
                output.update({
                    "story_id": cluster["story_id"],
                    "qualification": "direct",
                    "qualification_anchor_id": None,
                    "qualification_evidence": None,
                })
                qualified.append(output)
                continue
            if hard_veto is not None and hard_veto(record):
                continue
            anchor_matches: list[tuple[tuple[Any, ...], dict[str, Any], dict[str, Any]]] = []
            for anchor in direct_anchors:
                evidence = story_match(
                    record,
                    anchor,
                    global_candidate_tokens=global_tokens,
                )
                if evidence is None:
                    continue
                rank = (
                    -evidence["jaccard"],
                    -evidence["overlap"],
                    -evidence["shared_token_count"],
                    evidence["hours_apart"],
                    str(anchor.get("id") or ""),
                )
                anchor_matches.append((rank, anchor, evidence))
            if not anchor_matches:
                continue
            _rank, anchor, evidence = min(anchor_matches, key=lambda value: value[0])
            output = dict(record)
            output.update({
                "story_id": cluster["story_id"],
                "qualification": "cluster_confirmed",
                "qualification_anchor_id": str(anchor.get("id") or ""),
                "qualification_evidence": evidence,
            })
            qualified.append(output)
    return sorted(qualified, key=_record_key)


def publisher_story_exposures(records: list[dict[str, Any]]) -> list[dict[str, Any]]:
    """Collapse records to publisher × story and union only local matches."""

    buckets: dict[tuple[str, str], dict[str, Any]] = {}
    for record in records:
        publisher = str(record.get("publisher") or "").strip()
        story_id = str(record.get("story_id") or "").strip()
        if not publisher or not story_id:
            continue
        key = (publisher, story_id)
        bucket = buckets.setdefault(
            key,
            {
                "publisher": publisher,
                "story_id": story_id,
                "candidate_names": set(),
                "record_ids": set(),
            },
        )
        bucket["candidate_names"].update(_candidate_set(record))
        identifier = str(record.get("id") or "").strip()
        if identifier:
            bucket["record_ids"].add(identifier)
    return [
        {
            "publisher": bucket["publisher"],
            "story_id": bucket["story_id"],
            "candidate_names": sorted(bucket["candidate_names"]),
            "record_ids": sorted(bucket["record_ids"]),
        }
        for _key, bucket in sorted(buckets.items())
    ]
