"""Manual Tue/Wed recovery outside the immutable daily queue.

The CLI has no clock, Monday or week override. Workflow schedules never invoke
it. Production reads the same pinned authorities and receipt ledger as Monday.
"""
from __future__ import annotations

import argparse
import copy
import json
import sys
from datetime import datetime, timedelta, timezone
from pathlib import Path

# Support both direct CLI execution and imports from the repository root.
ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))
if str(ROOT / "social") not in sys.path:
    sys.path.insert(0, str(ROOT / "social"))

from social import daily_plan, social_publish, weekly_flagship


def run_catchup(args: argparse.Namespace, *, now: datetime | None = None) -> int:
    now = now if now is not None else datetime.now(timezone.utc)
    monday = weekly_flagship.catchup_monday(now)
    _, _, start, end = weekly_flagship.expected_weeks(monday)
    identity = weekly_flagship.slot_instruction(monday).product_id
    print(f"target_monday={monday.isoformat()}")
    print(f"completed_week={start}..{end}")
    print(f"product_id={identity}")

    # Validation may upgrade legacy state in memory. Work on a copy so preview,
    # skips and failures leave even the caller's loaded object untouched.
    state = copy.deepcopy(json.loads(Path(args.state).read_text(encoding="utf-8-sig")))
    social_publish._validate_state(state)
    planner = daily_plan.planner_state_from_social_state(state)
    if identity in weekly_flagship.published_weeks(planner):
        print("catchup_skipped=completed week already published")
        return 0
    try:
        product = weekly_flagship.load_catchup_product(root=ROOT, now=now)
    except weekly_flagship.CatchupCheckoutError as error:
        if args.dry_run:
            # Make the verified canonical copy reviewable in an uncommitted
            # development checkout. This remains a failed, non-publishable
            # preview; the loader never returns a publishable product.
            print("publishable=false")
            print(f"revision={error.product.revision}")
            print(f"weighted_length={error.product.weighted_length}")
            print(error.product.text)
            print("dry_run=true")
        raise
    if product.product_id != identity or not product.revision:
        raise weekly_flagship.FlagshipError("catch-up must resolve the expected week from a verified revision")
    print(f"revision={product.revision}")
    print(f"weighted_length={product.weighted_length}")
    print(product.text)
    if args.dry_run:
        print("dry_run=true")
        return 0

    client = social_publish.BufferClient.from_env()
    # Monday lies at most two Paris days back; include the complete recovery
    # interval. Use the same exact-text recovery semantics as regular slots.
    recent = client.recent_post_texts(since=now - timedelta(days=3))
    if product.text.strip() in recent:
        post_id = "buffer-existing"
        print("already present in Buffer; resolving state")
    else:
        post_id = client.create_post(product.text)
    receipt = weekly_flagship.publication_receipt(
        product_id=identity, revision=product.revision, published_at=now, buffer_post_id=post_id)
    weekly_flagship.record_receipt(planner, receipt)
    state["updated_at"] = receipt["published_at"]
    daily_plan.save_social_state(Path(args.state_output), state)
    print(f"state_output={Path(args.state_output).resolve()}")
    return 0


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--state", required=True, help="Loaded social-assets state (temporary bootstrap allowed for preview)")
    parser.add_argument("--state-output", required=True)
    parser.add_argument("--dry-run", action="store_true", help="Print validated copy; never call Buffer or write state")
    return parser


def main() -> int:
    for stream in (sys.stdout, sys.stderr):
        if callable(getattr(stream, "reconfigure", None)):
            stream.reconfigure(encoding="utf-8")
    try:
        return run_catchup(build_parser().parse_args())
    except (ValueError, KeyError, OSError) as error:
        print(f"catchup_failed_closed={error}", file=sys.stderr)
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
