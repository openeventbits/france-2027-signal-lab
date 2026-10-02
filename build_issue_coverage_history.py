"""Build persistent article-derived issue coverage history for FR27.

The history is reconstructed from retained ``news_wire.json`` snapshots.  It
uses Policy Agenda evolution generated from accepted article evidence and never
uses candidate-association history as a coverage proxy.
"""

from __future__ import annotations

import argparse
import json
import os
import re
import subprocess
import tempfile
from datetime import date, datetime, time, timedelta, timezone
from pathlib import Path
from typing import Any, Iterable

from issue_page_contract import ISSUE_DEFINITIONS


ROOT = Path(__file__).resolve().parent
NEWS_WIRE_PATH = ROOT / "news_wire.json"
OUTPUT_PATH = ROOT / "issue_coverage_history.json"
SCHEMA_VERSION = "1.0"


class IssueCoverageHistoryError(ValueError):
    """Raised when retained article coverage cannot be reconstructed safely."""


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
        raise IssueCoverageHistoryError(
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
            raise IssueCoverageHistoryError(f"malformed Git history row for {path}")
        blob = fields[3]
        if blob == "0" * 40:
            continue
        moment = datetime.fromisoformat(committed_at).astimezone(timezone.utc)
        observations.append(
            {
                "commit": commit,
                "committed_at": moment,
                "blob": blob,
            }
        )
    if not observations:
        raise IssueCoverageHistoryError(f"no retained history for {path}")
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
        raise IssueCoverageHistoryError("could not open Git object reader")
    try:
        for observation in observations:
            process.stdin.write((observation["blob"] + "\n").encode("ascii"))
            process.stdin.flush()
            header = process.stdout.readline().decode("ascii").strip().split()
            if len(header) != 3 or header[1] != "blob":
                raise IssueCoverageHistoryError(
                    f"retained object is not a JSON blob: {observation['blob']}"
                )
            content = process.stdout.read(int(header[2]))
            process.stdout.read(1)
            try:
                payload = json.loads(content)
            except (UnicodeDecodeError, json.JSONDecodeError) as error:
                raise IssueCoverageHistoryError(
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
        raise IssueCoverageHistoryError(f"Git object reader failed: {detail}")


def _parse_timestamp(value: Any, label: str) -> datetime:
    if not isinstance(value, str) or not value:
        raise IssueCoverageHistoryError(f"{label} is missing")
    try:
        parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
    except ValueError as error:
        raise IssueCoverageHistoryError(f"{label} is invalid") from error
    if parsed.tzinfo is None or parsed.utcoffset() is None:
        raise IssueCoverageHistoryError(f"{label} must be timezone-aware")
    return parsed.astimezone(timezone.utc)


def _first_inventory_timestamp(root: Path) -> tuple[datetime, str]:
    first = _history_observations(root, "news_inventory.json")[0]
    (_, payload), = _read_blobs(root, [first])
    generated_at = _parse_timestamp(payload.get("generated_at"), "inventory generated_at")
    return generated_at, first["commit"]


def _policy_introduction_date(root: Path) -> date:
    output = _run_git(
        root,
        [
            "log",
            "--reverse",
            "-S",
            '"policy_agenda"',
            "--format=%cI",
            "--",
            "news_wire.json",
        ],
    )
    first = next((line.strip() for line in output.splitlines() if line.strip()), "")
    if not first:
        raise IssueCoverageHistoryError("no retained Policy Agenda snapshots")
    return _parse_timestamp(first, "Policy Agenda introduction").date()


def _calendar_days(start: date, end: date) -> list[date]:
    if start > end:
        raise IssueCoverageHistoryError("historical period is empty")
    return [start + timedelta(days=offset) for offset in range((end - start).days + 1)]


def _snapshot_days(
    payload: dict[str, Any],
    *,
    start: date,
    end: date,
) -> dict[str, dict[str, Any]]:
    generated_at = _parse_timestamp(payload.get("generated_at"), "news generated_at")
    policy = payload.get("policy_agenda")
    relevant_news = payload.get("relevant_news")
    if not isinstance(policy, dict) or not isinstance(relevant_news, list):
        return {}
    evolution = policy.get("evolution")
    if not isinstance(evolution, dict):
        return {}

    definitions = {item.issue_id: item for item in ISSUE_DEFINITIONS}
    topics = evolution.get("topics")
    if not isinstance(topics, list):
        raise IssueCoverageHistoryError("Policy Agenda evolution topics are invalid")
    topic_by_id = {
        item.get("id"): item for item in topics if isinstance(item, dict)
    }
    if not set(topic_by_id).issubset(definitions):
        raise IssueCoverageHistoryError(
            "retained Policy Agenda contains a non-canonical issue"
        )

    accepted = evolution.get("accepted_daily_activity")
    if not isinstance(accepted, list):
        raise IssueCoverageHistoryError("accepted daily activity is invalid")
    corpus_publishers = {
        item.get("date"): item.get("source_day_count")
        for item in accepted
        if isinstance(item, dict)
    }
    relevant_by_day: dict[str, dict[str, dict[str, Any]]] = {}
    for item in relevant_news:
        if not isinstance(item, dict):
            continue
        item_id = str(item.get("id") or "")
        published_at = str(item.get("published_at") or "")
        if not item_id or len(published_at) < 10:
            continue
        relevant_by_day.setdefault(published_at[:10], {})[item_id] = item

    issue_daily: dict[str, dict[str, dict[str, Any]]] = {}
    for issue_id in definitions:
        topic = topic_by_id.get(issue_id)
        if topic is None:
            issue_daily[issue_id] = {}
            continue
        points = topic.get("daily_activity")
        if not isinstance(points, list):
            raise IssueCoverageHistoryError(f"{issue_id} daily activity is invalid")
        issue_daily[issue_id] = {
            point.get("date"): point
            for point in points
            if isinstance(point, dict)
        }

    result: dict[str, dict[str, Any]] = {}
    for current in _calendar_days(start, end):
        day = current.isoformat()
        if day not in corpus_publishers:
            continue
        corpus_items = relevant_by_day.get(day, {})
        publisher_names = sorted(
            {
                str(item.get("publisher") or "")
                for item in corpus_items.values()
                if str(item.get("publisher") or "")
            },
            key=str.casefold,
        )
        corpus_publisher_count = corpus_publishers[day]
        if type(corpus_publisher_count) is not int or corpus_publisher_count < 0:
            raise IssueCoverageHistoryError("corpus publisher denominator is invalid")
        if corpus_publisher_count != len(publisher_names):
            raise IssueCoverageHistoryError(
                f"corpus publisher denominator mismatch on {day}"
            )
        issues: dict[str, dict[str, int]] = {}
        for issue_id in definitions:
            point = issue_daily[issue_id].get(day)
            if point is None and issue_id not in topic_by_id:
                item_count = 0
                publisher_count = 0
            elif isinstance(point, dict):
                item_count = point.get("item_count")
                publisher_count = point.get("source_day_count")
            else:
                raise IssueCoverageHistoryError(
                    f"missing retained {issue_id} coverage on {day}"
                )
            if (
                type(item_count) is not int
                or item_count < 0
                or type(publisher_count) is not int
                or publisher_count < 0
                or publisher_count > item_count
                or item_count > len(corpus_items)
            ):
                raise IssueCoverageHistoryError(
                    f"invalid retained {issue_id} coverage on {day}"
                )
            issues[issue_id] = {
                "item_count": item_count,
                "publisher_count": publisher_count,
            }
        result[day] = {
            "date": day,
            "source_snapshot_at": generated_at.isoformat().replace("+00:00", "Z"),
            "corpus_item_count": len(corpus_items),
            "corpus_publisher_count": corpus_publisher_count,
            "corpus_publishers": publisher_names,
            "issues": issues,
        }
    return result


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
        raise IssueCoverageHistoryError("no complete reconstructable UTC days")

    introduction = _policy_introduction_date(root)
    wire_observations = [
        item
        for item in _daily_latest(_history_observations(root, "news_wire.json"))
        if item["committed_at"].date() >= introduction
    ]
    snapshots = [payload for _, payload in _read_blobs(root, wire_observations)]
    snapshots.append(current_payload)
    snapshots.sort(key=lambda item: _parse_timestamp(item.get("generated_at"), "news generated_at"))

    reconstructed: dict[str, dict[str, Any]] = {}
    for snapshot in snapshots:
        for day, observation in _snapshot_days(
            snapshot,
            start=period_start,
            end=period_end,
        ).items():
            previous = reconstructed.get(day)
            if previous is None or observation["source_snapshot_at"] > previous["source_snapshot_at"]:
                reconstructed[day] = observation

    expected_days = [item.isoformat() for item in _calendar_days(period_start, period_end)]
    missing = [day for day in expected_days if day not in reconstructed]
    if missing:
        raise IssueCoverageHistoryError(
            "retained Policy Agenda snapshots do not cover complete days: "
            + ", ".join(missing)
        )

    corpus_daily = []
    corpus_publishers: set[str] = set()
    for day in expected_days:
        observation = reconstructed[day]
        corpus_publishers.update(observation["corpus_publishers"])
        corpus_daily.append(
            {
                "date": day,
                "item_count": observation["corpus_item_count"],
                "publisher_count": observation["corpus_publisher_count"],
                "source_snapshot_at": observation["source_snapshot_at"],
            }
        )

    issue_payloads = []
    for definition in ISSUE_DEFINITIONS:
        daily = []
        for day in expected_days:
            observation = reconstructed[day]
            point = observation["issues"][definition.issue_id]
            denominator = observation["corpus_item_count"]
            daily.append(
                {
                    "date": day,
                    "item_count": point["item_count"],
                    "publisher_count": point["publisher_count"],
                    "corpus_item_count": denominator,
                    "corpus_publisher_count": observation["corpus_publisher_count"],
                    "corpus_share_percent": (
                        round(point["item_count"] / denominator * 100, 4)
                        if denominator
                        else 0.0
                    ),
                }
            )
        observed = [point for point in daily if point["item_count"]]
        peak = max(
            daily,
            key=lambda point: (point["item_count"], point["date"]),
        )
        issue_payloads.append(
            {
                "id": definition.issue_id,
                "labels": {"fr": definition.label_fr, "en": definition.label_en},
                "total_item_count": sum(point["item_count"] for point in daily),
                "publisher_day_count": sum(point["publisher_count"] for point in daily),
                "active_day_count": len(observed),
                "first_observation": observed[0]["date"] if observed else None,
                "last_observation": observed[-1]["date"] if observed else None,
                "peak": {"date": peak["date"], "item_count": peak["item_count"]},
                "daily": daily,
            }
        )

    return {
        "schema_version": SCHEMA_VERSION,
        "data_as_of": data_as_of.isoformat().replace("+00:00", "Z"),
        "period": {
            "start_date": period_start.isoformat(),
            "end_date": period_end.isoformat(),
            "days": len(expected_days),
            "day_boundary": "UTC",
            "current_utc_day_excluded": True,
        },
        "reconstruction": {
            "source": "retained news_wire.json Policy Agenda evolution snapshots",
            "initial_inventory_at": inventory_started_at.isoformat().replace("+00:00", "Z"),
            "initial_inventory_commit": inventory_commit,
            "start_rule": "first complete UTC day after persistent relevant-news inventory initialization",
            "coverage_measure": "article-derived multilabel Policy Agenda item counts",
            "prohibited_proxy": "candidate association history is not used",
        },
        "denominator": {
            "name": "accepted relevant-news article corpus",
            "unit": "unique accepted relevant-news article IDs by UTC publication day",
            "formula": "issue item_count / corpus item_count × 100",
            "multilabel": True,
            "note_fr": "Un article peut relever de plusieurs enjeux; la somme des parts peut donc dépasser 100 %.",
            "note_en": "An article may belong to several issues, so issue shares may sum above 100%.",
        },
        "corpus": {
            "total_item_count": sum(point["item_count"] for point in corpus_daily),
            "publisher_count": len(corpus_publishers),
            "publisher_day_count": sum(point["publisher_count"] for point in corpus_daily),
            "first_observation": next(
                (point["date"] for point in corpus_daily if point["item_count"]),
                None,
            ),
            "last_observation": next(
                (point["date"] for point in reversed(corpus_daily) if point["item_count"]),
                None,
            ),
            "daily": corpus_daily,
        },
        "issues": issue_payloads,
    }


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
    file_descriptor, temporary_name = tempfile.mkstemp(
        prefix=f".{path.name}.", suffix=".tmp", dir=path.parent
    )
    temporary = Path(temporary_name)
    try:
        with os.fdopen(file_descriptor, "wb") as handle:
            handle.write(content)
            handle.flush()
            os.fsync(handle.fileno())
        os.replace(temporary, path)
    except BaseException:
        temporary.unlink(missing_ok=True)
        raise


def _parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Build FR27 issue coverage history")
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
                raise IssueCoverageHistoryError("issue coverage history is stale")
            print(
                "issue coverage history check clean: "
                f"{payload['period']['days']} complete days"
            )
            return 0
        _atomic_write(arguments.output, content)
    except (IssueCoverageHistoryError, OSError, json.JSONDecodeError) as error:
        print(f"issue coverage history error: {error}")
        return 1
    print(
        "built issue coverage history: "
        f"{payload['period']['start_date']} to {payload['period']['end_date']} "
        f"({payload['period']['days']} complete days)"
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
