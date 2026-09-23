from __future__ import annotations

import argparse
import json
import os
import tempfile
from datetime import datetime, timezone
from pathlib import Path
from typing import Any


SCHEMA_VERSION = 1


class CorpusLedgerError(ValueError):
    """Raised when the cumulative news corpus contract is invalid."""


def parse_utc_timestamp(value: Any, *, field: str) -> datetime:
    if not isinstance(value, str) or not value.strip():
        raise CorpusLedgerError(f"{field} must be a UTC ISO-8601 timestamp")

    try:
        parsed = datetime.fromisoformat(
            value.strip().replace("Z", "+00:00")
        )
    except ValueError as error:
        raise CorpusLedgerError(
            f"{field} must be a UTC ISO-8601 timestamp"
        ) from error

    if parsed.tzinfo is None or parsed.utcoffset() is None:
        raise CorpusLedgerError(f"{field} must include a UTC offset")

    return parsed.astimezone(timezone.utc)


def format_utc_timestamp(value: datetime) -> str:
    return (
        value.astimezone(timezone.utc)
        .isoformat()
        .replace("+00:00", "Z")
    )


def load_json_object(path: Path) -> dict[str, Any]:
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as error:
        raise CorpusLedgerError(
            f"could not read {path}: {error}"
        ) from error

    if not isinstance(payload, dict):
        raise CorpusLedgerError(f"{path} must contain a JSON object")

    return payload


def validate_string_set(
    payload: dict[str, Any],
    field: str,
) -> list[str]:
    values = payload.get(field)

    if not isinstance(values, list):
        raise CorpusLedgerError(f"{field} must be an array")

    if any(
        not isinstance(value, str) or not value.strip()
        for value in values
    ):
        raise CorpusLedgerError(
            f"{field} must contain non-empty strings"
        )

    if values != sorted(set(values)):
        raise CorpusLedgerError(
            f"{field} must be sorted and unique"
        )

    return values


def validate_ledger(payload: dict[str, Any]) -> None:
    expected_fields = {
        "schema_version",
        "observation_start_at",
        "updated_at",
        "counts",
        "accepted_election_news_ids",
        "candidate_watch_ids",
        "accepted_news_publishers",
    }

    if set(payload) != expected_fields:
        raise CorpusLedgerError(
            "ledger contains unexpected or missing fields"
        )

    if payload.get("schema_version") != SCHEMA_VERSION:
        raise CorpusLedgerError(
            f"unsupported ledger schema version: "
            f"{payload.get('schema_version')!r}"
        )

    observation_start = parse_utc_timestamp(
        payload.get("observation_start_at"),
        field="observation_start_at",
    )
    updated_at = parse_utc_timestamp(
        payload.get("updated_at"),
        field="updated_at",
    )

    if updated_at < observation_start:
        raise CorpusLedgerError(
            "updated_at cannot precede observation_start_at"
        )

    accepted_ids = validate_string_set(
        payload,
        "accepted_election_news_ids",
    )
    candidate_ids = validate_string_set(
        payload,
        "candidate_watch_ids",
    )
    publishers = validate_string_set(
        payload,
        "accepted_news_publishers",
    )

    counts = payload.get("counts")

    if not isinstance(counts, dict):
        raise CorpusLedgerError("counts must be an object")

    expected_count_fields = {
        "accepted_election_news",
        "candidate_watch",
        "accepted_news_publishers",
    }

    if set(counts) != expected_count_fields:
        raise CorpusLedgerError(
            "counts contains unexpected or missing fields"
        )

    expected_counts = {
        "accepted_election_news": len(accepted_ids),
        "candidate_watch": len(candidate_ids),
        "accepted_news_publishers": len(publishers),
    }

    if counts != expected_counts:
        raise CorpusLedgerError(
            "counts do not match cumulative ledger arrays"
        )


def wire_identity_set(
    wire: dict[str, Any],
    field: str,
) -> set[str]:
    items = wire.get(field)

    if not isinstance(items, list):
        raise CorpusLedgerError(
            f"news wire {field} must be an array"
        )

    result: set[str] = set()

    for item in items:
        if not isinstance(item, dict):
            raise CorpusLedgerError(
                f"news wire {field} contains a non-object item"
            )

        item_id = item.get("id")

        if not isinstance(item_id, str) or not item_id.strip():
            raise CorpusLedgerError(
                f"news wire {field} item is missing id"
            )

        result.add(item_id.strip())

    return result


def update_ledger(
    ledger: dict[str, Any],
    wire: dict[str, Any],
) -> dict[str, Any]:
    validate_ledger(ledger)

    wire_generated_at = parse_utc_timestamp(
        wire.get("generated_at"),
        field="news wire generated_at",
    )

    observation_start = parse_utc_timestamp(
        ledger["observation_start_at"],
        field="observation_start_at",
    )
    previous_updated_at = parse_utc_timestamp(
        ledger["updated_at"],
        field="updated_at",
    )

    previous_accepted_ids = set(
        ledger["accepted_election_news_ids"]
    )
    previous_candidate_ids = set(
        ledger["candidate_watch_ids"]
    )
    previous_publishers = set(
        ledger["accepted_news_publishers"]
    )

    accepted_ids = set(previous_accepted_ids)
    candidate_ids = set(previous_candidate_ids)
    publishers = set(previous_publishers)

    accepted_ids.update(
        wire_identity_set(
            wire,
            "election_news",
        )
    )

    candidate_ids.update(
        wire_identity_set(
            wire,
            "candidate_watch",
        )
    )

    for item in wire.get("election_news", []):
        publisher = str(
            item.get("publisher") or ""
        ).strip()

        if publisher:
            publishers.add(publisher)

    corpus_changed = (
        accepted_ids != previous_accepted_ids
        or candidate_ids != previous_candidate_ids
        or publishers != previous_publishers
    )

    effective_updated_at = (
        max(previous_updated_at, wire_generated_at)
        if corpus_changed
        else previous_updated_at
    )

    updated = {
        "schema_version": SCHEMA_VERSION,
        "observation_start_at": format_utc_timestamp(
            observation_start
        ),
        "updated_at": format_utc_timestamp(
            effective_updated_at
        ),
        "counts": {
            "accepted_election_news": len(accepted_ids),
            "candidate_watch": len(candidate_ids),
            "accepted_news_publishers": len(publishers),
        },
        "accepted_election_news_ids": sorted(accepted_ids),
        "candidate_watch_ids": sorted(candidate_ids),
        "accepted_news_publishers": sorted(publishers),
    }

    validate_ledger(updated)
    return updated


def corpus_counts(
    ledger: dict[str, Any],
) -> dict[str, Any]:
    validate_ledger(ledger)

    return {
        "observation_start_at": ledger["observation_start_at"],
        "updated_at": ledger["updated_at"],
        "accepted_election_news": ledger["counts"][
            "accepted_election_news"
        ],
        "candidate_watch": ledger["counts"][
            "candidate_watch"
        ],
        "accepted_news_publishers": ledger["counts"][
            "accepted_news_publishers"
        ],
    }


def write_json_atomic(
    path: Path,
    payload: dict[str, Any],
) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)

    fd, temporary_name = tempfile.mkstemp(
        prefix=f".{path.name}.",
        suffix=".tmp",
        dir=path.parent,
        text=True,
    )

    try:
        with os.fdopen(
            fd,
            "w",
            encoding="utf-8",
            newline="\n",
        ) as handle:
            json.dump(
                payload,
                handle,
                ensure_ascii=False,
                indent=2,
            )
            handle.write("\n")

        os.replace(
            temporary_name,
            path,
        )
    except Exception:
        try:
            os.unlink(temporary_name)
        except OSError:
            pass
        raise


def main() -> int:
    parser = argparse.ArgumentParser(
        description=(
            "Update the monotonic FR27 news corpus ledger and "
            "publish cumulative counts into news_wire.json."
        )
    )
    parser.add_argument(
        "--ledger",
        type=Path,
        default=Path("news_corpus_ledger.json"),
    )
    parser.add_argument(
        "--wire",
        type=Path,
        default=Path("news_wire.json"),
    )

    arguments = parser.parse_args()

    ledger = load_json_object(arguments.ledger)
    wire = load_json_object(arguments.wire)

    updated_ledger = update_ledger(
        ledger,
        wire,
    )

    wire["corpus_counts"] = corpus_counts(
        updated_ledger
    )

    write_json_atomic(
        arguments.ledger,
        updated_ledger,
    )
    write_json_atomic(
        arguments.wire,
        wire,
    )

    counts = updated_ledger["counts"]

    print("News corpus ledger updated.")
    print(
        "Cumulative accepted election news: "
        f"{counts['accepted_election_news']}"
    )
    print(
        "Cumulative candidate watch: "
        f"{counts['candidate_watch']}"
    )
    print(
        "Cumulative accepted-news publishers: "
        f"{counts['accepted_news_publishers']}"
    )
    print(
        f"Observation start: "
        f"{updated_ledger['observation_start_at']}"
    )
    print(
        f"Updated through: "
        f"{updated_ledger['updated_at']}"
    )

    return 0


if __name__ == "__main__":
    raise SystemExit(main())
