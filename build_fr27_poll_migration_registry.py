"""Build the reviewed FR27 migration registry from frozen audit evidence.

This is a deterministic maintainer tool.  It reads only repository data and
the two frozen MediaWiki fixtures; it never fetches live Wikipedia.
"""

from __future__ import annotations

import argparse
import hashlib
import json
from collections import defaultdict
from pathlib import Path
from typing import Any, Callable

from poll_migration import (
    ENGLISH_FIXTURE,
    FRENCH_FIXTURE,
    FIRST_ROUND,
    SECOND_ROUND,
    FactualKey,
    candidate_identity,
    exact_factual_key,
    load_mediawiki_fixture,
    parse_french_frozen_fixture,
    pollster_identity,
    validate_migration_registry,
)


ROOT = Path(__file__).parent
OUTPUT = ROOT / "fr27_poll_migration_registry.json"

AMBIGUOUS_IDENTITY_LOCATORS = {"FR-T1R9", "FR-T1R10", "FR-T1R11"}

COMMISSION_HARRIS_JULY = (
    "https://www.commission-des-sondages.fr/notices/files/notices/2026/"
    "juillet/10223-pres-iv-toluna-harris-interactive-rtl-8-juillet.pdf"
)
COMMISSION_IFOP_MAY = (
    "https://www.commission-des-sondages.fr/notices/files/notices/2026/"
    "mai/10193-pres-ifop-le-figaro-29-mai.pdf"
)
COMMISSION_ODOXA_MARCH = (
    "https://www.commission-des-sondages.fr/notices/files/notices/2026/"
    "mars/10167-pres-odoxa-31-mars.pdf"
)
COMMISSION_CLUSTER_SEPTEMBER = (
    "https://www.commission-des-sondages.fr/notices/files/notices/2025/"
    "octobre/9990-pres-cluster-17-le-point-3-octobre.pdf"
)
COMMISSION_IFOP_MARCH = (
    "https://www.commission-des-sondages.fr/notices/files/notices/2025/"
    "mars/9912-pres-ifop-jdd-30-mars-notice-pour-publication.pdf"
)
HEXAGONE_REPORT = (
    "https://observatoire-hexagone.org/wp-content/uploads/2025/05/"
    "20250502_Hexagone_Grande-Enquete-Electorale-2025.pdf"
)


def _read_json(path: Path) -> Any:
    return json.loads(path.read_text(encoding="utf-8"))


def _sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def _candidate_scores(event: dict[str, Any]) -> tuple[tuple[str, str], ...]:
    key = exact_factual_key(event, sample_scope="reported")
    return key.candidates


def _candidate_ids(event: dict[str, Any]) -> tuple[str, ...]:
    return tuple(candidate_id for candidate_id, _score in _candidate_scores(event))


def _full_key(event: dict[str, Any]) -> FactualKey:
    return exact_factual_key(event, sample_scope="reported")


def _index_unique(
    records: list[dict[str, Any]],
    key: Callable[[dict[str, Any]], tuple[Any, ...]],
) -> dict[tuple[Any, ...], list[dict[str, Any]]]:
    index: dict[tuple[Any, ...], list[dict[str, Any]]] = defaultdict(list)
    for record in records:
        index[key(record)].append(record)
    return index


def _sample_match_key(event: dict[str, Any]) -> tuple[Any, ...]:
    return (
        event["round"],
        pollster_identity(event["pollster"]),
        event["fieldwork_start"],
        event["fieldwork_end"],
        _candidate_scores(event),
    )


def _score_match_key(event: dict[str, Any]) -> tuple[Any, ...]:
    return (
        event["round"],
        pollster_identity(event["pollster"]),
        event["fieldwork_start"],
        event["fieldwork_end"],
        event["sample_size"],
        _candidate_ids(event),
    )


def _date_match_key(event: dict[str, Any]) -> tuple[Any, ...]:
    return (
        event["round"],
        pollster_identity(event["pollster"]),
        event["sample_size"],
        _candidate_scores(event),
    )


def _alias_match_key(event: dict[str, Any]) -> tuple[Any, ...]:
    return (
        event["round"],
        event["fieldwork_start"],
        event["fieldwork_end"],
        event["sample_size"],
        _candidate_scores(event),
    )


SAMPLE_DECISIONS: dict[tuple[str, str], tuple[int, str, str, list[str]]] = {
    ("harris-interactive", "2026-07-07"): (
        1592,
        "registered_voters",
        "Commission notice supports 1,592 registered voters; 1,582 is unsupported.",
        [COMMISSION_HARRIS_JULY],
    ),
    ("ifop", "2026-05-26"): (
        1368,
        "registered_voters",
        "Retain the 1,368 registered-voter base, not the 1,501-adult total.",
        [COMMISSION_IFOP_MAY],
    ),
    ("odoxa", "2026-03-25"): (
        1299,
        "survey_respondents",
        "The 1,005 figure belongs to another barometer; this survey interviewed 1,299.",
        [COMMISSION_ODOXA_MARCH],
    ),
    ("harris-interactive", "2026-03-22"): (
        1000,
        "registered_voters",
        "Retain the 1,000 registered-voter base drawn from 1,062 adults.",
        [],
    ),
    ("elabe", "2025-10-30"): (
        1396,
        "registered_voters",
        "Use the registered-voter base of 1,396 rather than the 1,501-adult total.",
        [],
    ),
    ("harris-interactive", "2025-10-07"): (
        1124,
        "registered_voters",
        "Retain the 1,124 registered-voter base drawn from 1,289 adults.",
        [],
    ),
    ("cluster17", "2025-09-30"): (
        1451,
        "registered_voters",
        "Commission evidence identifies 1,451 registered voters; 1,531 is the adult total and 1,534 is unsupported.",
        [COMMISSION_CLUSTER_SEPTEMBER],
    ),
    ("ifop", "2025-09-24"): (
        1127,
        "registered_voters",
        "Use the 1,127 registered-voter base rather than the 1,210-adult total.",
        [],
    ),
    ("harris-interactive", "2025-05-19"): (
        1071,
        "registered_voters",
        "Retain the 1,071 registered-voter base drawn from 1,217 adults.",
        [],
    ),
    ("ifop", "2024-09-06"): (
        1107,
        "registered_voters",
        "Retain the 1,107 registered-voter base drawn from 1,204 adults.",
        [],
    ),
    ("cluster17", "2024-04-02"): (
        1686,
        "registered_voters",
        "Retain the 1,686 registered-voter base drawn from 1,713 adults.",
        [],
    ),
    ("ifop", "2023-10-24"): (
        1084,
        "registered_voters",
        "Use the 1,084 registered-voter base rather than the 1,179-adult total.",
        [],
    ),
    ("opinionway", "2023-04-12"): (
        965,
        "registered_voters",
        "Use the 965 registered-voter base rather than the 1,038-adult total.",
        [],
    ),
    ("cluster17", "2022-11-04"): (
        2096,
        "registered_voters",
        "Use the 2,096 registered-voter base rather than the 2,151-adult total.",
        [],
    ),
    ("ifop", "2022-10-25"): (
        1126,
        "registered_voters",
        "The original notice reports 1,126 registered voters; 1,125 is a transcription error.",
        [],
    ),
}


def _clone_for_key(event: dict[str, Any]) -> dict[str, Any]:
    return {
        "round": event["round"],
        "pollster": event["pollster"],
        "fieldwork_start": event["fieldwork_start"],
        "fieldwork_end": event["fieldwork_end"],
        "sample_size": event["sample_size"],
        "sample_scope": event.get("sample_scope", "reported"),
        "candidates": [dict(candidate) for candidate in event["candidates"]],
    }


def _canonical_first_pair(
    old: dict[str, Any], incoming: dict[str, Any], category: str
) -> tuple[FactualKey, str, list[str]]:
    canonical = _clone_for_key(incoming)
    reviewed_pollster: str | None = None
    reason = "Reviewed first-round factual reconciliation."
    evidence: list[str] = []
    if category == "sample":
        decision = SAMPLE_DECISIONS[
            (pollster_identity(incoming["pollster"]), incoming["fieldwork_start"])
        ]
        canonical["sample_size"], canonical["sample_scope"], reason, evidence = decision
    elif category == "date":
        canonical["fieldwork_start"] = "2025-03-26"
        canonical["fieldwork_end"] = "2025-03-27"
        reason = "The Commission/Ifop report supports 26-27 March 2025; the French range is unsupported."
        evidence = [COMMISSION_IFOP_MARCH]
    elif category == "score":
        if incoming["source_locator"] == "FR-T3R23":
            canonical["candidates"] = [dict(candidate) for candidate in old["candidates"]]
            reason = "The original Ifop report supports Philippe at 26; retain the current value over the French transcription."
        else:
            reason = "Original poll evidence supports the reviewed French score correction."
    elif category == "pollster_alias":
        reviewed_pollster = "ifop-hexagone"
        reason = "The April 2025 study is the wave-scoped Ifop/Hexagone commission."
        evidence = [HEXAGONE_REPORT]
    evidence = [*evidence, incoming["source_url"]]
    return (
        exact_factual_key(
            canonical,
            sample_scope=canonical["sample_scope"],
            reviewed_pollster=reviewed_pollster,
        ),
        reason,
        list(dict.fromkeys(evidence)),
    )


def _canonical_runoff_pair(
    old: dict[str, Any], incoming: dict[str, Any]
) -> tuple[FactualKey, str, list[str]]:
    canonical = _clone_for_key(incoming)
    reviewed_pollster: str | None = None
    pollster = pollster_identity(incoming["pollster"])
    start = incoming["fieldwork_start"]
    evidence = [incoming["source_url"]]
    if pollster == "harris-interactive" and start == "2026-07-07":
        canonical["sample_size"] = 1592
        canonical["sample_scope"] = "registered_voters"
        reason = "Commission notice supports 1,592 registered voters; 1,582 is unsupported."
        evidence.insert(0, COMMISSION_HARRIS_JULY)
    elif pollster == "cluster17" and start == "2024-04-02":
        canonical["sample_size"] = 1686
        canonical["sample_scope"] = "registered_voters"
        reason = "Retain the registered-voter base of 1,686 rather than the adult total of 1,713."
    elif pollster == "odoxa" and start == "2025-11-19":
        canonical["sample_scope"] = "matchup_respondents"
        reason = "The French row reports the matchup-specific respondent base rather than the blanket survey total."
    elif pollster == "ifop" and start == "2025-04-11":
        ids = {candidate_identity(item["name"]) for item in incoming["candidates"]}
        scores = {candidate_identity(item["name"]): item["score"] for item in incoming["candidates"]}
        if ids == {"edouard-philippe", "marine-le-pen"} and scores["edouard-philippe"] == 52:
            canonical["fieldwork_start"] = "2025-04-21"
            canonical["fieldwork_end"] = "2025-04-30"
            canonical["sample_size"] = 1838
            reviewed_pollster = "ifop"
            reason = "The separate 1,838-person late-April study supports Philippe 52 - Le Pen 48."
        else:
            canonical = _clone_for_key(old)
            reviewed_pollster = "ifop-hexagone"
            reason = "The 9,128-person Bardella runoffs belong to the 11-18 April Ifop/Hexagone study."
        evidence.insert(0, HEXAGONE_REPORT)
    else:
        raise AssertionError(f"unexpected runoff reconciliation: {incoming['source_locator']}")
    return (
        exact_factual_key(
            canonical,
            sample_scope=canonical["sample_scope"],
            reviewed_pollster=reviewed_pollster,
        ),
        reason,
        list(dict.fromkeys(evidence)),
    )


def _decision_value(value: Any) -> Any:
    if isinstance(value, tuple):
        return [
            {"candidate_id": candidate_id, "score": score}
            for candidate_id, score in value
        ]
    return value


def _field_decisions(
    old: FactualKey, incoming: FactualKey, canonical: FactualKey
) -> dict[str, dict[str, Any]]:
    decisions: dict[str, dict[str, Any]] = {}
    for field in (
        "pollster_identity",
        "fieldwork_start",
        "fieldwork_end",
        "sample_size",
        "sample_scope",
        "candidates",
    ):
        values = (getattr(old, field), getattr(incoming, field), getattr(canonical, field))
        if not (values[0] == values[1] == values[2]):
            decisions[field] = {
                "old": _decision_value(values[0]),
                "incoming": _decision_value(values[1]),
                "canonical": _decision_value(values[2]),
            }
    return decisions


def _mapping_record(
    old: dict[str, Any],
    incoming: dict[str, Any],
    canonical: FactualKey,
    *,
    reviewed: bool,
    reason: str,
    evidence: list[str],
    incoming_key: FactualKey | None = None,
) -> dict[str, Any]:
    old_key = _full_key(old)
    incoming_key = incoming_key or _full_key(incoming)
    record = {
        "legacy_event_id": old["event_id"],
        "retained_event_id": old["event_id"],
        "incoming_source_locator": incoming["source_locator"],
        "treatment": (
            "retain_id_reviewed_correction"
            if reviewed
            else "retain_id_source_refresh"
        ),
        "old_factual_key": old_key.to_dict(),
        "incoming_factual_key": incoming_key.to_dict(),
        "canonical_factual_key": canonical.to_dict(),
        "legacy_source_url": old["source_url"],
        "incoming_source_url": incoming["source_url"],
        "evidence_urls": list(dict.fromkeys(evidence)),
        "review_reason": reason,
    }
    if reviewed:
        record["field_decisions"] = _field_decisions(old_key, incoming_key, canonical)
    return record


def _match_reviewed_first(
    current: list[dict[str, Any]], incoming: list[dict[str, Any]]
) -> tuple[list[tuple[dict[str, Any], dict[str, Any], str]], list[dict[str, Any]], list[dict[str, Any]]]:
    remaining_current = list(current)
    remaining_incoming = list(incoming)
    matches: list[tuple[dict[str, Any], dict[str, Any], str]] = []
    for category, key_function in (
        ("sample", _sample_match_key),
        ("score", _score_match_key),
        ("date", _date_match_key),
        ("pollster_alias", _alias_match_key),
    ):
        current_index = _index_unique(remaining_current, key_function)
        incoming_index = _index_unique(remaining_incoming, key_function)
        category_matches: list[tuple[dict[str, Any], dict[str, Any], str]] = []
        for key in set(current_index) & set(incoming_index):
            old_records = current_index[key]
            new_records = incoming_index[key]
            if len(old_records) != 1 or len(new_records) != 1:
                continue
            old = old_records[0]
            new = new_records[0]
            if category == "sample" and old["sample_size"] == new["sample_size"]:
                continue
            if category == "score" and _candidate_scores(old) == _candidate_scores(new):
                continue
            if category == "date" and (
                old["fieldwork_start"], old["fieldwork_end"]
            ) == (new["fieldwork_start"], new["fieldwork_end"]):
                continue
            if category == "pollster_alias" and not (
                pollster_identity(old["pollster"]) == "ifop-hexagone"
                and pollster_identity(new["pollster"]) == "ifop"
            ):
                continue
            category_matches.append((old, new, category))
        matched_old = {item[0]["event_id"] for item in category_matches}
        matched_new = {item[1]["source_locator"] for item in category_matches}
        remaining_current = [item for item in remaining_current if item["event_id"] not in matched_old]
        remaining_incoming = [item for item in remaining_incoming if item["source_locator"] not in matched_new]
        matches.extend(category_matches)
    return matches, remaining_current, remaining_incoming


def _runoff_review_key(event: dict[str, Any]) -> tuple[Any, ...]:
    identity = pollster_identity(event["pollster"])
    if identity == "ifop-hexagone":
        identity = "ifop"
    return (
        identity,
        event["fieldwork_start"],
        _candidate_scores(event),
    )


def build_registry() -> dict[str, Any]:
    current_first = _read_json(ROOT / "polls.json")
    current_second = _read_json(ROOT / "second_round_polls.json")["events"]
    french = parse_french_frozen_fixture(
        load_mediawiki_fixture(FRENCH_FIXTURE, 238906992)
    )

    eligible_french_first = [
        record
        for record in french["first_round"]
        if record["source_locator"] not in AMBIGUOUS_IDENTITY_LOCATORS
    ]
    current_first_keyed = [
        event
        for event in current_first
        if not any(
            normalize_generic(candidate["name"])
            for candidate in event["candidates"]
        )
    ]
    first_by_key = _index_unique(current_first_keyed, lambda event: (_full_key(event),))
    exact_first: list[tuple[dict[str, Any], dict[str, Any]]] = []
    exact_first_locators: set[str] = set()
    exact_first_ids: set[str] = set()
    for incoming in eligible_french_first:
        matches = first_by_key.get((_full_key(incoming),), [])
        if len(matches) == 1:
            exact_first.append((matches[0], incoming))
            exact_first_locators.add(incoming["source_locator"])
            exact_first_ids.add(matches[0]["event_id"])
        elif len(matches) > 1:
            raise AssertionError(f"ambiguous exact first-round match: {incoming['source_locator']}")
    assert len(exact_first) == 100

    remaining_current_first = [
        event for event in current_first_keyed if event["event_id"] not in exact_first_ids
    ]
    remaining_french_first = [
        event
        for event in eligible_french_first
        if event["source_locator"] not in exact_first_locators
    ]
    reviewed_first, unmatched_current_first, new_first = _match_reviewed_first(
        remaining_current_first, remaining_french_first
    )
    category_counts = defaultdict(int)
    for _old, _incoming, category in reviewed_first:
        category_counts[category] += 1
    assert dict(category_counts) == {
        "sample": 43,
        "score": 8,
        "date": 3,
        "pollster_alias": 5,
    }
    assert len(reviewed_first) == 59
    assert len(new_first) == 29

    current_second_index = _index_unique(current_second, lambda event: (_full_key(event),))
    exact_second: list[tuple[dict[str, Any], dict[str, Any]]] = []
    exact_second_ids: set[str] = set()
    exact_second_locators: set[str] = set()
    for incoming in french["second_round"]:
        matches = current_second_index.get((_full_key(incoming),), [])
        if len(matches) == 1:
            exact_second.append((matches[0], incoming))
            exact_second_ids.add(matches[0]["event_id"])
            exact_second_locators.add(incoming["source_locator"])
        elif len(matches) > 1:
            raise AssertionError(f"ambiguous exact runoff match: {incoming['source_locator']}")
    assert len(exact_second) == 22

    remaining_current_second = [
        event for event in current_second if event["event_id"] not in exact_second_ids
    ]
    remaining_french_second = [
        event
        for event in french["second_round"]
        if event["source_locator"] not in exact_second_locators
    ]
    old_runoff_index = _index_unique(remaining_current_second, _runoff_review_key)
    incoming_runoff_index = _index_unique(remaining_french_second, _runoff_review_key)
    reviewed_second: list[tuple[dict[str, Any], dict[str, Any]]] = []
    for key in set(old_runoff_index) & set(incoming_runoff_index):
        if len(old_runoff_index[key]) == len(incoming_runoff_index[key]) == 1:
            reviewed_second.append((old_runoff_index[key][0], incoming_runoff_index[key][0]))
    assert len(reviewed_second) == 14
    reviewed_second_ids = {old["event_id"] for old, _incoming in reviewed_second}
    reviewed_second_locators = {
        incoming["source_locator"] for _old, incoming in reviewed_second
    }
    historical_second = [
        event
        for event in remaining_current_second
        if event["event_id"] not in reviewed_second_ids
    ]
    new_second = [
        event
        for event in remaining_french_second
        if event["source_locator"] not in reviewed_second_locators
    ]
    assert len(historical_second) == 2
    assert len(new_second) == 12

    source_only: list[dict[str, Any]] = []
    for old, incoming in [*exact_first, *exact_second]:
        if old["source_url"] == incoming["source_url"]:
            continue
        key = _full_key(old)
        source_only.append(
            _mapping_record(
                old,
                incoming,
                key,
                reviewed=False,
                reason="The frozen French row reports the same factual poll with a different direct source URL.",
                evidence=[incoming["source_url"]],
            )
        )
    assert len(source_only) == 102

    reviewed_records: list[dict[str, Any]] = []
    for old, incoming, category in reviewed_first:
        canonical, reason, evidence = _canonical_first_pair(old, incoming, category)
        incoming_key = _full_key(incoming)
        if category == "pollster_alias":
            incoming_key = exact_factual_key(
                incoming,
                sample_scope="reported",
                reviewed_pollster="ifop",
            )
        reviewed_records.append(
            _mapping_record(
                old,
                incoming,
                canonical,
                reviewed=True,
                reason=reason,
                evidence=evidence,
                incoming_key=incoming_key,
            )
        )
    for old, incoming in reviewed_second:
        canonical, reason, evidence = _canonical_runoff_pair(old, incoming)
        reviewed_records.append(
            _mapping_record(
                old,
                incoming,
                canonical,
                reviewed=True,
                reason=reason,
                evidence=evidence,
            )
        )
    assert len(reviewed_records) == 73

    mapped_first_ids = {
        record["legacy_event_id"]
        for record in [*source_only, *reviewed_records]
        if record["old_factual_key"]["round"] == FIRST_ROUND
    }
    # Ten exact common-source rows need no migration entry but are represented.
    exact_common_first_ids = {
        old["event_id"]
        for old, incoming in exact_first
        if old["source_url"] == incoming["source_url"]
    }
    persistence_first = [
        event
        for event in current_first
        if event["event_id"] not in mapped_first_ids | exact_common_first_ids
    ]
    assert len(persistence_first) == 44

    payload: dict[str, Any] = {
        "schema_version": "1.0",
        "source_revisions": {
            "english": {
                "revision_id": 1371070883,
                "page_url": "https://en.wikipedia.org/wiki/Opinion_polling_for_the_2027_French_presidential_election",
                "fixture": "test_fixtures/fr27_polling/en_mediawiki_1371070883.json",
                "fixture_sha256": _sha256(ENGLISH_FIXTURE),
            },
            "french": {
                "revision_id": 238906992,
                "page_url": "https://fr.wikipedia.org/wiki/Liste_de_sondages_sur_l%27%C3%A9lection_pr%C3%A9sidentielle_fran%C3%A7aise_de_2027",
                "fixture": "test_fixtures/fr27_polling/fr_mediawiki_238906992.json",
                "fixture_sha256": _sha256(FRENCH_FIXTURE),
            },
        },
        "acceptance": {
            "current_first_round_preserved": 203,
            "current_second_round_preserved": 38,
            "french_new_first_round": 29,
            "french_new_second_round": 12,
            "source_only_migrations": 102,
            "reviewed_reconciliation_mappings": 73,
            "unexplained_historical_losses": 0,
            "unresolved_accepted_identity_ambiguities": 0,
            "duplicate_canonical_factual_identities": 0,
            "fail_closed_french_rows": 8,
        },
        "wave_scoped_pollster_aliases": [
            {
                "reported": "Ifop",
                "canonical_identity": "ifop-hexagone",
                "fieldwork_start": "2025-04-11",
                "fieldwork_end": "2025-04-18",
                "sample_size": 9128,
                "evidence_urls": [HEXAGONE_REPORT],
                "review_reason": "Apply Ifop/Hexagone only to the reviewed April 2025 commissioned wave.",
            }
        ],
        "source_only_identity_migrations": sorted(
            source_only,
            key=lambda record: (record["old_factual_key"]["round"], record["legacy_event_id"]),
        ),
        "reviewed_reconciliations": sorted(
            reviewed_records,
            key=lambda record: (record["old_factual_key"]["round"], record["legacy_event_id"]),
        ),
        "persistence_obligations": {
            "first_round": [
                {
                    "event_id": event["event_id"],
                    "treatment": "preserve_historical",
                    "evidence_urls": [event["source_url"]],
                    "review_reason": "Validated current FR27 history has no accepted French counterpart and must persist.",
                }
                for event in sorted(persistence_first, key=lambda item: item["event_id"])
            ],
            "second_round": [
                {
                    "event_id": event["event_id"],
                    "treatment": "preserve_historical",
                    "evidence_urls": [event["source_url"]],
                    "review_reason": "Genuine English-only historical Ifop runoff must persist.",
                }
                for event in sorted(historical_second, key=lambda item: item["event_id"])
            ],
        },
        "french_additions": {
            "first_round": [
                _addition_record(event, FIRST_ROUND) for event in sorted(new_first, key=lambda item: item["source_locator"])
            ],
            "second_round": [
                _addition_record(event, SECOND_ROUND) for event in sorted(new_second, key=lambda item: item["source_locator"])
            ],
        },
        "fail_closed": [
            {
                "source_locator": record["source_locator"],
                "reason_code": record["reason_code"],
                "treatment": "skip_fail_closed",
                "evidence_urls": [
                    "https://fr.wikipedia.org/w/index.php?oldid=238906992"
                ],
                "review_reason": (
                    "Censored scores remain incompatible with the exact-score contract."
                    if record["reason_code"] == "censored_score"
                    else "The French row does not uniquely identify every scored candidate."
                ),
            }
            for record in french["rejected"]
        ],
        "identity_skips": [
            {
                "source_locator": locator,
                "reason_code": "ambiguous_candidate_identity",
                "treatment": "skip_fail_closed",
                "evidence_urls": [
                    "https://fr.wikipedia.org/w/index.php?oldid=238906992"
                ],
                "review_reason": "The cell says Bardella / Le Pen and cannot be assigned to one named candidate despite its link.",
            }
            for locator in sorted(AMBIGUOUS_IDENTITY_LOCATORS)
        ],
    }
    validate_migration_registry(payload)
    return payload


def normalize_generic(value: str) -> bool:
    return value.startswith("Generic ")


def _addition_record(event: dict[str, Any], round_name: str) -> dict[str, Any]:
    canonical = _clone_for_key(event)
    reviewed_pollster: str | None = None
    reason = "Named French scenario is absent from the current corpus and is ready to add."
    evidence = [event["source_url"]]
    if round_name == FIRST_ROUND:
        sample_decision = SAMPLE_DECISIONS.get(
            (pollster_identity(event["pollster"]), event["fieldwork_start"])
        )
        if sample_decision:
            canonical["sample_size"] = sample_decision[0]
            canonical["sample_scope"] = sample_decision[1]
            reason = sample_decision[2] + " New named scenario is ready to add."
            evidence = [*sample_decision[3], *evidence]
        if event["fieldwork_start"] == "2025-03-21" and event["sample_size"] == 1119:
            canonical["fieldwork_start"] = "2025-03-26"
            canonical["fieldwork_end"] = "2025-03-27"
            reason = "Corrected to the original Ifop 26-27 March fieldwork window; named scenario is ready to add."
            evidence = [COMMISSION_IFOP_MARCH, *evidence]
        if event["fieldwork_start"] == "2025-04-11" and event["sample_size"] == 9128:
            reviewed_pollster = "ifop-hexagone"
            reason = "Named scenario belongs to the wave-scoped Ifop/Hexagone study and is ready to add."
            evidence = [HEXAGONE_REPORT, *evidence]
    key = exact_factual_key(
        canonical,
        sample_scope=canonical["sample_scope"],
        reviewed_pollster=reviewed_pollster,
    )
    return {
        "source_locator": event["source_locator"],
        "treatment": "add_new",
        "factual_key": key.to_dict(),
        "source_url": event["source_url"],
        "evidence_urls": list(dict.fromkeys(evidence)),
        "review_reason": reason,
    }


def canonical_registry_bytes(payload: dict[str, Any]) -> bytes:
    """Return the one canonical on-disk representation of a valid registry."""

    validate_migration_registry(payload)
    text = json.dumps(payload, ensure_ascii=False, indent=2) + "\n"
    return text.encode("utf-8")


def _parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description="Build the frozen FR27 French polling migration registry."
    )
    parser.add_argument(
        "--check",
        action="store_true",
        help="validate and compare with the committed registry without writing",
    )
    return parser


def main(argv: list[str] | None = None) -> int:
    arguments = _parser().parse_args(argv)
    generated = canonical_registry_bytes(build_registry())
    if arguments.check:
        try:
            committed = OUTPUT.read_bytes()
        except OSError as error:
            print(f"Registry check failed: cannot read {OUTPUT}: {error}")
            return 1
        if committed != generated:
            print(
                f"Registry check failed: {OUTPUT.name} is stale; "
                "run the builder without --check"
            )
            return 1
        print(f"Registry check passed: {OUTPUT.name} is current")
        return 0

    OUTPUT.write_bytes(generated)
    payload = json.loads(generated)
    print(
        f"Wrote {OUTPUT.name}: "
        f"{len(payload['source_only_identity_migrations'])} source-only, "
        f"{len(payload['reviewed_reconciliations'])} reviewed"
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
