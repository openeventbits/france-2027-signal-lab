"""Build persistent topic-oriented Campaign Agenda coverage history.

History is reconstructed from the published classifications retained in Git
under ``news_wire.json:campaign_agenda.evolution``.  Old headlines are never
reclassified, and candidate association history is never used as a proxy for
media volume. Historical source-linked observations are materialized from the
matching retained published supporting items for artifact-only page rendering.
"""

from __future__ import annotations

import argparse
import json
import os
import subprocess
import tempfile
from datetime import date, datetime, time, timedelta, timezone
from pathlib import Path
from typing import Any, Iterable

from agenda_page_contract import (
    AGENDA_DEFINITIONS,
    CURRENT_SOURCE_DAY_MIN,
    HISTORY_SCHEMA_VERSION,
    HISTORICAL_EVIDENCE_SELECTION_RULE,
    HISTORICAL_EVIDENCE_SOURCE,
    ROLLING_HISTORY_DAYS,
    validate_agenda_coverage_history,
)


ROOT = Path(__file__).resolve().parent
NEWS_WIRE_PATH = ROOT / "news_wire.json"
OUTPUT_PATH = ROOT / "agenda_coverage_history.json"


class AgendaCoverageHistoryError(ValueError):
    """Raised when retained Agenda history cannot be reconstructed safely."""


def _run_git(root: Path, arguments: list[str]) -> str:
    try:
        return subprocess.check_output(
            ["git", *arguments],
            cwd=root,
            text=True,
            encoding="utf-8",
            stderr=subprocess.PIPE,
        )
    except (OSError, subprocess.CalledProcessError) as error:
        raise AgendaCoverageHistoryError(
            f"could not inspect retained Git data: {error}"
        ) from error


def _history_observations(root: Path, path: str) -> list[dict[str, Any]]:
    output = _run_git(
        root,
        [
            "log",
            "--reverse",
            "--format=COMMIT %H %cI",
            "--raw",
            "--no-abbrev",
            "--",
            path,
        ],
    )
    observations: list[dict[str, Any]] = []
    commit = ""
    committed_at = ""
    for line in output.splitlines():
        if line.startswith("COMMIT "):
            _, commit, committed_at = line.split(" ", 2)
            continue
        if not line.startswith(":") or not line.endswith("\t" + path):
            continue
        fields = line.split()
        if len(fields) < 5:
            raise AgendaCoverageHistoryError(f"malformed Git history row for {path}")
        blob = fields[3]
        if blob == "0" * 40:
            continue
        observations.append(
            {
                "commit": commit,
                "committed_at": datetime.fromisoformat(committed_at).astimezone(
                    timezone.utc
                ),
                "blob": blob,
            }
        )
    if not observations:
        raise AgendaCoverageHistoryError(f"no retained history for {path}")
    return observations


def _daily_latest(observations: Iterable[dict[str, Any]]) -> list[dict[str, Any]]:
    latest: dict[date, dict[str, Any]] = {}
    for observation in observations:
        latest[observation["committed_at"].date()] = observation
    return [latest[current] for current in sorted(latest)]


def _read_blobs(
    root: Path,
    observations: Iterable[dict[str, Any]],
) -> Iterable[tuple[dict[str, Any], dict[str, Any]]]:
    process = subprocess.Popen(
        ["git", "cat-file", "--batch"],
        cwd=root,
        stdin=subprocess.PIPE,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
    )
    if process.stdin is None or process.stdout is None:
        raise AgendaCoverageHistoryError("could not open Git object reader")
    try:
        for observation in observations:
            process.stdin.write((observation["blob"] + "\n").encode("ascii"))
            process.stdin.flush()
            header = process.stdout.readline().decode("ascii").strip().split()
            if len(header) != 3 or header[1] != "blob":
                raise AgendaCoverageHistoryError(
                    f"retained object is not a JSON blob: {observation['blob']}"
                )
            content = process.stdout.read(int(header[2]))
            process.stdout.read(1)
            try:
                payload = json.loads(content)
            except (UnicodeDecodeError, json.JSONDecodeError) as error:
                raise AgendaCoverageHistoryError(
                    f"invalid retained JSON blob: {observation['blob']}"
                ) from error
            yield observation, payload
    finally:
        process.stdin.close()
        process.wait()
    if process.returncode:
        detail = (
            process.stderr.read().decode("utf-8", errors="replace")
            if process.stderr is not None
            else ""
        )
        process.stdout.close()
        process.stderr.close()
        raise AgendaCoverageHistoryError(f"Git object reader failed: {detail}")
    process.stdout.close()
    process.stderr.close()


def _parse_timestamp(value: Any, label: str) -> datetime:
    if not isinstance(value, str) or not value:
        raise AgendaCoverageHistoryError(f"{label} is missing")
    try:
        parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
    except ValueError as error:
        raise AgendaCoverageHistoryError(f"{label} is invalid") from error
    if parsed.tzinfo is None or parsed.utcoffset() is None:
        raise AgendaCoverageHistoryError(f"{label} must be timezone-aware")
    return parsed.astimezone(timezone.utc)


def _first_inventory_timestamp(root: Path) -> tuple[datetime, str]:
    first = _history_observations(root, "news_inventory.json")[0]
    ((_, payload),) = _read_blobs(root, [first])
    generated_at = _parse_timestamp(payload.get("generated_at"), "inventory generated_at")
    return generated_at, first["commit"]


def _campaign_introduction_date(root: Path) -> date:
    output = _run_git(
        root,
        [
            "log",
            "--reverse",
            "-S",
            '"campaign_agenda"',
            "--format=%cI",
            "--",
            "news_wire.json",
        ],
    )
    first = next((line.strip() for line in output.splitlines() if line.strip()), "")
    if not first:
        raise AgendaCoverageHistoryError("no retained Campaign Agenda snapshots")
    return _parse_timestamp(first, "Campaign Agenda introduction").date()


def _calendar_days(start: date, end: date) -> list[date]:
    if start > end:
        raise AgendaCoverageHistoryError("historical period is empty")
    return [start + timedelta(days=offset) for offset in range((end - start).days + 1)]


def _snapshot_days(
    payload: dict[str, Any],
    *,
    start: date,
    end: date,
) -> dict[str, dict[str, Any]]:
    """Extract complete daily classifications from one retained snapshot."""

    generated_at = _parse_timestamp(payload.get("generated_at"), "news generated_at")
    agenda = payload.get("campaign_agenda")
    if not isinstance(agenda, dict):
        return {}
    evolution = agenda.get("evolution")
    if not isinstance(evolution, dict):
        return {}
    if evolution.get("period_end_partial") is not True:
        raise AgendaCoverageHistoryError(
            "Campaign Agenda evolution partial-day contract is invalid"
        )

    try:
        evolution_start = date.fromisoformat(evolution["period_start"])
        evolution_end = date.fromisoformat(evolution["period_end"])
    except (KeyError, TypeError, ValueError) as error:
        raise AgendaCoverageHistoryError(
            "Campaign Agenda evolution period is invalid"
        ) from error
    expected_evolution_days = [
        current.isoformat() for current in _calendar_days(evolution_start, evolution_end)
    ]
    if (
        len(expected_evolution_days) != ROLLING_HISTORY_DAYS
        or evolution.get("period_days") != ROLLING_HISTORY_DAYS
        or evolution_end != generated_at.date()
    ):
        raise AgendaCoverageHistoryError(
            "Campaign Agenda evolution does not contain the canonical 30-day period"
        )

    raw_topics = evolution.get("topics")
    if not isinstance(raw_topics, list):
        raise AgendaCoverageHistoryError("Campaign Agenda evolution topics are invalid")
    canonical = {definition.topic_id: definition for definition in AGENDA_DEFINITIONS}
    topics: dict[str, dict[str, Any]] = {}
    for raw_topic in raw_topics:
        if not isinstance(raw_topic, dict):
            raise AgendaCoverageHistoryError("Campaign Agenda evolution topic is invalid")
        topic_id = raw_topic.get("id")
        if topic_id not in canonical:
            raise AgendaCoverageHistoryError(
                "retained Campaign Agenda contains an unknown taxonomy id"
            )
        if topic_id in topics:
            raise AgendaCoverageHistoryError(
                "retained Campaign Agenda contains a duplicate topic"
            )
        if raw_topic.get("label") != canonical[topic_id].label_en:
            raise AgendaCoverageHistoryError(
                f"retained Campaign Agenda label mismatch for {topic_id}"
            )
        points = raw_topic.get("daily_activity")
        if not isinstance(points, list):
            raise AgendaCoverageHistoryError(f"{topic_id} daily activity is invalid")
        if [
            point.get("date") if isinstance(point, dict) else None for point in points
        ] != expected_evolution_days:
            raise AgendaCoverageHistoryError(
                f"{topic_id} retained daily activity is not contiguous"
            )
        point_index: dict[str, dict[str, int]] = {}
        for point in points:
            item_count = point.get("item_count")
            source_day_count = point.get("source_day_count")
            if (
                type(item_count) is not int
                or item_count < 0
                or type(source_day_count) is not int
                or source_day_count < 0
                or source_day_count > item_count
            ):
                raise AgendaCoverageHistoryError(
                    f"{topic_id} retained daily count is invalid"
                )
            point_index[point["date"]] = {
                "item_count": item_count,
                "source_day_count": source_day_count,
            }
        if raw_topic.get("item_count") != sum(
            point["item_count"] for point in point_index.values()
        ) or raw_topic.get("source_day_count") != sum(
            point["source_day_count"] for point in point_index.values()
        ):
            raise AgendaCoverageHistoryError(
                f"{topic_id} retained evolution totals do not reconcile"
            )
        topics[topic_id] = point_index

    result: dict[str, dict[str, Any]] = {}
    for current in _calendar_days(start, end):
        if current < evolution_start or current > evolution_end:
            continue
        day = current.isoformat()
        topic_points: dict[str, dict[str, int]] = {}
        for definition in AGENDA_DEFINITIONS:
            point_index = topics.get(definition.topic_id)
            # Older retained snapshots may predate a canonical topic's first
            # non-zero classification.  Absence means zero, never taxonomy removal.
            point = (
                point_index[day]
                if point_index is not None
                else {"item_count": 0, "source_day_count": 0}
            )
            topic_points[definition.topic_id] = point
        result[day] = {
            "date": day,
            "source_snapshot_at": generated_at.isoformat().replace("+00:00", "Z"),
            "total_classified_agenda_items": sum(
                point["item_count"] for point in topic_points.values()
            ),
            "total_agenda_topic_source_days": sum(
                point["source_day_count"] for point in topic_points.values()
            ),
            "topics": topic_points,
        }
    return result


def _rolling_30d_maximum(points: list[dict[str, Any]]) -> int:
    if len(points) < ROLLING_HISTORY_DAYS:
        return 0
    window = sum(
        point["source_day_count"] for point in points[:ROLLING_HISTORY_DAYS]
    )
    maximum = window
    for index in range(ROLLING_HISTORY_DAYS, len(points)):
        window += points[index]["source_day_count"]
        window -= points[index - ROLLING_HISTORY_DAYS]["source_day_count"]
        maximum = max(maximum, window)
    return maximum


def _historical_evidence(
    retained: list[tuple[dict[str, Any], dict[str, Any]]],
    daily: list[dict[str, Any]],
    topics: list[dict[str, Any]],
) -> dict[str, Any]:
    """Materialize the historical hub's existing per-theme selection unchanged.

    Only retained published supporting items whose snapshot matches the coverage
    day's authority are eligible. Current-only items are never a fallback.
    """
    authority = {point["date"]: point["source_snapshot_at"] for point in daily}
    selected_topics = [topic for topic in topics if topic["active_days"] > 0]
    candidates = {topic["id"]: [] for topic in selected_topics}
    for observation, snapshot in retained:
        snapshot_at = snapshot.get("generated_at")
        for topic in snapshot.get("campaign_agenda", {}).get("topics", []):
            if topic["id"] not in candidates:
                continue
            for item in topic.get("supporting_items", []):
                day = item["published_at"][:10]
                if authority.get(day) != snapshot_at:
                    continue
                candidates[topic["id"]].append({
                    "id": item["id"], "topic_id": topic["id"],
                    "publisher": item["publisher"], "published_at": item["published_at"],
                    "date": day, "headline": item["headline"], "url": item["url"],
                    "source_snapshot_at": snapshot_at, "source_commit": observation["commit"],
                })
    rows = []
    for topic in selected_topics:
        source_days = {point["date"]: point["source_day_count"] for point in topic["daily"]}
        choices = candidates[topic["id"]]
        if not choices:
            raise AgendaCoverageHistoryError(f'No authoritative retained historical evidence for {topic["id"]}')
        rows.append(min(choices, key=lambda item: (
            -source_days[item["date"]], item["date"], item["published_at"], str(item["id"]), item["url"])))
    return {
        "source": HISTORICAL_EVIDENCE_SOURCE,
        "selection_rule": HISTORICAL_EVIDENCE_SELECTION_RULE,
        "items": sorted(rows, key=lambda item: (item["date"], item["published_at"], str(item["id"])), reverse=True),
    }


def build_history_payload(
    *,
    root: Path = ROOT,
    news_wire_path: Path = NEWS_WIRE_PATH,
) -> dict[str, Any]:
    current_payload = json.loads(news_wire_path.read_text(encoding="utf-8"))
    data_as_of = _parse_timestamp(current_payload.get("generated_at"), "news generated_at")
    period_end = data_as_of.date() - timedelta(days=1)

    inventory_started_at, inventory_commit = _first_inventory_timestamp(root)
    period_start = inventory_started_at.date()
    if inventory_started_at.timetz().replace(tzinfo=None) != time.min:
        period_start += timedelta(days=1)
    if period_start > period_end:
        raise AgendaCoverageHistoryError("no complete reconstructable UTC days")

    introduction = _campaign_introduction_date(root)
    observations = [
        observation
        for observation in _daily_latest(_history_observations(root, "news_wire.json"))
        if observation["committed_at"].date() >= introduction
    ]
    retained = list(_read_blobs(root, observations))
    snapshots = [payload for _, payload in retained]
    snapshots.append(current_payload)
    snapshots.sort(
        key=lambda payload: _parse_timestamp(payload.get("generated_at"), "news generated_at")
    )

    reconstructed: dict[str, dict[str, Any]] = {}
    for snapshot in snapshots:
        for day, observation in _snapshot_days(
            snapshot,
            start=period_start,
            end=period_end,
        ).items():
            previous = reconstructed.get(day)
            if previous is None or observation["source_snapshot_at"] > previous[
                "source_snapshot_at"
            ]:
                reconstructed[day] = observation

    expected_days = [day.isoformat() for day in _calendar_days(period_start, period_end)]
    missing = [day for day in expected_days if day not in reconstructed]
    if missing:
        raise AgendaCoverageHistoryError(
            "retained Campaign Agenda evolution snapshots do not cover complete days: "
            + ", ".join(missing)
        )

    daily = [
        {
            "date": day,
            "total_classified_agenda_items": reconstructed[day][
                "total_classified_agenda_items"
            ],
            "total_agenda_topic_source_days": reconstructed[day][
                "total_agenda_topic_source_days"
            ],
            "source_snapshot_at": reconstructed[day]["source_snapshot_at"],
        }
        for day in expected_days
    ]

    topic_payloads = []
    for definition in AGENDA_DEFINITIONS:
        points = []
        for day in expected_days:
            observation = reconstructed[day]
            topic = observation["topics"][definition.topic_id]
            item_denominator = observation["total_classified_agenda_items"]
            source_day_denominator = observation["total_agenda_topic_source_days"]
            points.append(
                {
                    "date": day,
                    "item_count": topic["item_count"],
                    "source_day_count": topic["source_day_count"],
                    "total_classified_agenda_items": item_denominator,
                    "total_agenda_topic_source_days": source_day_denominator,
                    "topic_item_share": (
                        topic["item_count"] / item_denominator
                        if item_denominator
                        else 0.0
                    ),
                    "topic_source_day_share": (
                        topic["source_day_count"] / source_day_denominator
                        if source_day_denominator
                        else 0.0
                    ),
                }
            )
        observed = [point for point in points if point["item_count"]]
        peak = min(
            points,
            key=lambda point: (
                -point["source_day_count"],
                -point["item_count"],
                point["date"],
            ),
        )
        rolling_maximum = _rolling_30d_maximum(points)
        topic_payloads.append(
            {
                "id": definition.topic_id,
                "labels": {"fr": definition.label_fr, "en": definition.label_en},
                "total_items": sum(point["item_count"] for point in points),
                "total_source_days": sum(point["source_day_count"] for point in points),
                "active_days": len(observed),
                "first_observation": observed[0]["date"] if observed else None,
                "last_observation": observed[-1]["date"] if observed else None,
                "peak_day": {
                    "date": peak["date"],
                    "item_count": peak["item_count"],
                    "source_day_count": peak["source_day_count"],
                },
                "maximum_rolling_30d_source_days": rolling_maximum,
                "historical_qualified": rolling_maximum >= CURRENT_SOURCE_DAY_MIN,
                "daily": points,
            }
        )

    payload = {
        "schema_version": HISTORY_SCHEMA_VERSION,
        "data_as_of": data_as_of.isoformat().replace("+00:00", "Z"),
        "period": {
            "start_date": period_start.isoformat(),
            "end_date": period_end.isoformat(),
            "days": len(expected_days),
            "day_boundary": "UTC",
            "current_utc_day_excluded": True,
        },
        "reconstruction": {
            "classification_source": (
                "retained news_wire.json campaign_agenda.evolution snapshots"
            ),
            "initial_inventory_at": inventory_started_at.isoformat().replace(
                "+00:00", "Z"
            ),
            "initial_inventory_commit": inventory_commit,
            "start_rule": (
                "first complete UTC day after persistent relevant-news inventory initialization"
            ),
            "historical_classifier_policy": (
                "retain each published snapshot classification; never reclassify old headlines"
            ),
            "missing_canonical_topic_policy": (
                "zero-fill canonical topics absent from an older snapshot"
            ),
            "peak_tie_break": (
                "source_day_count descending, item_count descending, date ascending"
            ),
            "prohibited_proxy": (
                "candidate_agenda_history.json is not used as media-volume history"
            ),
        },
        "denominator": {
            "single_label": True,
            "item_name": "classified Campaign Agenda items",
            "item_formula": "topic item_count / total classified Agenda items",
            "source_day_name": "Campaign Agenda topic source-days",
            "source_day_formula": (
                "topic source_day_count / total Agenda topic source-days"
            ),
            "zero_denominator_share": 0.0,
            "note": (
                "Source-days are summed within topics; one publisher/date may contribute "
                "to different topic source-day totals through different single-label items."
            ),
        },
        "daily": daily,
        "topics": topic_payloads,
        "historical_evidence": _historical_evidence(retained, daily, topic_payloads),
    }
    try:
        validate_agenda_coverage_history(payload)
    except ValueError as error:
        raise AgendaCoverageHistoryError(
            f"constructed Agenda history violates its contract: {error}"
        ) from error
    return payload


def serialize_history(payload: dict[str, Any]) -> bytes:
    return (
        json.dumps(payload, ensure_ascii=False, indent=2, separators=(",", ": "))
        + "\n"
    ).encode("utf-8")


def _atomic_write(path: Path, content: bytes) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    if path.exists() and path.read_bytes().replace(b"\r\n", b"\n") == content.replace(
        b"\r\n", b"\n"
    ):
        return
    descriptor, temporary_name = tempfile.mkstemp(
        prefix=f".{path.name}.", suffix=".tmp", dir=path.parent
    )
    temporary = Path(temporary_name)
    try:
        with os.fdopen(descriptor, "wb") as handle:
            handle.write(content)
            handle.flush()
            os.fsync(handle.fileno())
        os.replace(temporary, path)
    except BaseException:
        temporary.unlink(missing_ok=True)
        raise


def _parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Build FR27 Agenda coverage history")
    parser.add_argument("--root", type=Path, default=ROOT)
    parser.add_argument("--news-wire", type=Path, default=NEWS_WIRE_PATH)
    parser.add_argument("--output", type=Path, default=OUTPUT_PATH)
    parser.add_argument("--check", action="store_true")
    return parser


def main(argv: list[str] | None = None) -> int:
    arguments = _parser().parse_args(argv)
    try:
        payload = build_history_payload(
            root=arguments.root,
            news_wire_path=arguments.news_wire,
        )
        content = serialize_history(payload)
        if arguments.check:
            if not arguments.output.exists() or arguments.output.read_bytes().replace(
                b"\r\n", b"\n"
            ) != content.replace(b"\r\n", b"\n"):
                raise AgendaCoverageHistoryError("Agenda coverage history is stale")
            print(
                "Agenda coverage history check clean: "
                f"{payload['period']['days']} complete days"
            )
            return 0
        _atomic_write(arguments.output, content)
    except (AgendaCoverageHistoryError, OSError, json.JSONDecodeError) as error:
        print(f"Agenda coverage history error: {error}")
        return 1
    print(
        "built Agenda coverage history: "
        f"{payload['period']['start_date']} to {payload['period']['end_date']} "
        f"({payload['period']['days']} complete days)"
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
