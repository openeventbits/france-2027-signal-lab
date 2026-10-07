"""Read-only readiness barrier for the frozen X queue. Never imports Buffer.

Run under production-data-update, after checking out main with full history.
Producer completion is only a retry signal: both families must reproduce from
the SAME current news snapshot, including their pages and registered routes.
"""
from __future__ import annotations

import argparse
import hashlib
import json
import subprocess
import sys
import tempfile
from datetime import datetime, timedelta, timezone
from pathlib import Path
from zoneinfo import ZoneInfo

ROOT = Path(__file__).resolve().parents[1]
PARIS = ZoneInfo("Europe/Paris")
MAX_NEWS_AGE = timedelta(hours=6)
# Prevent an hourly completion just after midnight freezing yesterday's day.
EARLIEST_PLANNING_HOUR = 6
FROZEN_INPUTS = ("news_wire.json", "issue_coverage_history.json",
                 "agenda_coverage_history.json", "campaign_events.json",
                 "recent_changes.json", "route_registry.json")


def snapshot_proof(*, root: Path, now: datetime) -> dict:
    return {"schema_version": 1, "date": now.astimezone(PARIS).date().isoformat(),
            "inputs": {name: hashlib.sha256((root / name).read_bytes()).hexdigest()
                       for name in FROZEN_INPUTS}}


def validate_proof(proof: dict, *, root: Path, now: datetime) -> None:
    if proof != snapshot_proof(root=root, now=now):
        raise ValueError("planner readiness receipt does not match this day's frozen inputs")


def validate_queue_proof(proof: dict, *, queue_date: str) -> None:
    # An already frozen queue may retain a different, previously proven news
    # snapshot. Never relabel a legacy/heartbeat queue with today's new proof.
    if (not isinstance(proof, dict) or proof.get("schema_version") != 1
            or proof.get("date") != queue_date or not isinstance(proof.get("inputs"), dict)
            or set(proof["inputs"]) != set(FROZEN_INPUTS)
            or any(not isinstance(value, str) or len(value) != 64
                   or any(c not in "0123456789abcdef" for c in value)
                   for value in proof["inputs"].values())):
        raise ValueError("existing daily queue has no valid planner readiness receipt")


def load_json(root: Path, name: str) -> dict:
    payload = json.loads((root / name).read_text(encoding="utf-8-sig"))
    if not isinstance(payload, dict):
        raise ValueError(f"{name} must contain an object")
    return payload


def timestamp(value: str) -> datetime:
    instant = datetime.fromisoformat(value.replace("Z", "+00:00"))
    if instant.tzinfo is None:
        raise ValueError("readiness timestamps must be timezone-aware")
    return instant.astimezone(timezone.utc)


def check_command(root: Path, script: str, *args: str) -> None:
    # Every command is local and read-only (--check), except the Campaign Events
    # reproduction which writes exclusively into a temporary directory.
    subprocess.run([sys.executable, "-B", str(root / script), *args],
                   cwd=root, check=True, timeout=180)


def verify_readiness(*, root: Path, now: datetime) -> None:
    if now.tzinfo is None:
        raise ValueError("planner clock must be timezone-aware")
    local = now.astimezone(PARIS)
    if local.hour < EARLIEST_PLANNING_HOUR:
        raise ValueError("daily planning starts at 06:00 Europe/Paris")
    news = timestamp(load_json(root, "news_wire.json")["generated_at"])
    if (news.astimezone(PARIS).date() != local.date()
            or not timedelta(0) <= now - news <= MAX_NEWS_AGE):
        raise ValueError("news must be from today's Paris date and at most six hours old")

    for family in ("issue", "agenda"):
        history = load_json(root, f"{family}_coverage_history.json")
        if timestamp(history["data_as_of"]) != news:
            raise ValueError(f"{family} history does not match the current news snapshot")
        # Timestamps alone cannot detect missing/partial/stale historical rows.
        check_command(root, f"build_{family}_coverage_history.py", "--check")
        check_command(root, f"build_{family}_pages.py", "--check")

    # Verifies manifests, canonical destinations, HTML hashes and route coverage.
    check_command(root, "build_route_registry.py", "--check")

    # Campaign Events generation timestamps intentionally survive semantic
    # no-ops. Reproduce from registry/seeds/manual events/updates rather than
    # rejecting valid long-lived milestones based on age or fetching sources.
    events = load_json(root, "campaign_events.json")
    with tempfile.TemporaryDirectory(prefix="fr27-planner-") as temporary:
        output = Path(temporary) / "campaign_events.json"
        check_command(root, "build_campaign_events.py",
                      "--generated-at", events["generated_at"],
                      "--preserve-generated-at-from", str(root / "campaign_events.json"),
                      "--output", str(output))
        if load_json(output.parent, output.name) != events:
            raise ValueError("campaign events do not match authoritative inputs")

    # The ledger is read by the planner for diagnostics (max_updates=0); it
    # supplies no frozen posts. Still require readable JSON, just as build does.
    load_json(root, "recent_changes.json")


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--now", help="timezone-aware clock for local verification")
    parser.add_argument("--proof-output", type=Path, help="write a verified snapshot receipt outside main")
    args = parser.parse_args(argv)
    try:
        now = timestamp(args.now) if args.now else datetime.now(timezone.utc)
        verify_readiness(root=ROOT, now=now)
        if args.proof_output:
            args.proof_output.parent.mkdir(parents=True, exist_ok=True)
            args.proof_output.write_text(json.dumps(snapshot_proof(root=ROOT, now=now)), encoding="utf-8")
    except (OSError, ValueError, KeyError, TypeError, AttributeError,
            subprocess.SubprocessError) as error:
        print(f"PLANNER_READINESS=DEFERRED reason={error}")
        return 1
    print("PLANNER_READINESS=READY")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
