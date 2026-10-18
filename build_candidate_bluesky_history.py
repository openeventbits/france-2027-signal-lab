"""Append validated bluesky snapshot observations without any provider request."""
import argparse
import json
from candidate_history import update_file
from candidate_bluesky_history import build_history, validate_candidate_bluesky_history


def update(output="candidate_bluesky_history.json", *, snapshot_path="candidate_bluesky.json",
           mapping_path="bluesky_candidate_accounts.json", registry_path="candidate_candidacy_status.json", check=False):
    return update_file(output, snapshot_path, mapping_path, registry_path, build_history,
                       validate_candidate_bluesky_history, check=check)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output", default="candidate_bluesky_history.json")
    parser.add_argument("--check", action="store_true")
    args = parser.parse_args()
    try:
        result = update(args.output, check=args.check)
    except (ValueError, OSError) as error:
        print(json.dumps({"provider": "bluesky", "status": "failed", "error": str(error)}))
        return 1
    print(json.dumps({"provider": "bluesky", "observed_at": result["observed_at"],
                      "points": sum(len(r["points"]) for r in result["candidates"])}))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
