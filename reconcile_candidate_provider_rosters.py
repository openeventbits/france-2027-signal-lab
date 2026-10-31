"""Extend stored provider evidence to an authenticated registry, without collection.

Only candidates with no reviewed provider mapping may acquire empty rows. Existing
rows, history points, unavailable states and collection clocks are copied exactly.
All three providers participate because the manifest requires their full rosters.
"""
from __future__ import annotations

import argparse
import copy
import hashlib
import importlib
import json
from pathlib import Path

from build_candidate_signals import atomic_write
from candidate_candidacy_status import validate_candidate_candidacy_status


MAPPINGS = {
    "bluesky": "bluesky_candidate_accounts.json",
    "youtube": "youtube_candidate_channels.json",
    "polymarket": "polymarket_candidate_markets.json",
}
OUTPUTS = tuple(
    f"candidate_{provider}{suffix}.json"
    for provider in MAPPINGS for suffix in ("", "_history")
)


def require(condition, message):
    if not condition:
        raise ValueError(message)


def registry_ids(registry):
    validate_candidate_candidacy_status(registry)
    return {row["candidate_id"] for row in registry["candidates"]}


def evidence_hash(content):
    # Match the manifest's cross-platform CRLF normalization.
    return hashlib.sha256(content.replace(b"\r\n", b"\n")).hexdigest()


def reconcile_provider(provider, snapshot, history, mapping, previous_registry, registry):
    """Validate the old evidence against its own roster before extending it."""
    old_ids, ids = registry_ids(previous_registry), registry_ids(registry)
    require(old_ids <= ids, "registry removed historical candidates; explicit review required")
    require(previous_registry["source"]["revision_id"] <= registry["source"]["revision_id"],
            "registry source revision moved backwards")
    old_rows = {r["candidate_id"]: r for r in previous_registry["candidates"]}
    for row in registry["candidates"]:
        prior = old_rows.get(row["candidate_id"])
        if prior:
            require(prior.get("wikipedia_article") == row.get("wikipedia_article"),
                    "registry article identity changed; explicit review required")

    contract = importlib.import_module(f"candidate_{provider}")
    history_contract = importlib.import_module(f"candidate_{provider}_history")
    validate_snapshot = getattr(contract, f"validate_candidate_{provider}")
    validate_history = getattr(history_contract, f"validate_candidate_{provider}_history")
    validate_snapshot(snapshot, mapping=mapping, candidate_ids=old_ids)
    validate_history(history, mapping=mapping, candidate_ids=old_ids, snapshot=snapshot)
    # Mapping validation against old_ids also rejects a newly mapped candidate:
    # only a real provider collection can establish that candidate's evidence.
    reconciled, retained = copy.deepcopy(snapshot), copy.deepcopy(history)
    for cid in sorted(ids - old_ids):
        if provider == "polymarket":
            # candidate_record starts from a set of keys: canonicalize the new
            # empty row across Python processes so final manifest hashes agree.
            empty = contract.candidate_record(snapshot, cid)
            row = {key: empty[key] for key in sorted(empty)}
            history_row = dict(candidate_id=cid, market_id=None, yes_token_id=None,
                               points=[], source_checked_through=None, latest_source_point=None)
        else:
            row = contract.empty_record(cid)
            identity = "did" if provider == "bluesky" else "channel_id"
            history_row = {"candidate_id": cid, identity: None, "points": []}
        reconciled["candidates"].append(row)
        retained["candidates"].append(history_row)
    for payload in (reconciled, retained):
        payload["candidates"].sort(key=lambda row: row["candidate_id"])
    validate_snapshot(reconciled, mapping=mapping, candidate_ids=ids)
    validate_history(retained, mapping=mapping, candidate_ids=ids, snapshot=reconciled)
    return reconciled, retained


def reconcile(root, *, previous_registry_path, expected_registry_path, evidence_root=None):
    """Prepare/validate the entire bundle, recheck pinned inputs, then write.

    Post-rebase callers supply origin/main's evidence directory so a newer genuine
    collection always wins over the pre-rebase stored evidence. Current mappings
    must match that directory exactly; reconciliation cannot authorize a review.
    Git publication remains one commit/push after the complete manifest validates.
    """
    root = Path(root)
    evidence_root = Path(evidence_root) if evidence_root is not None else root
    registry_path = root / "candidate_candidacy_status.json"
    previous_path, expected_path = Path(previous_registry_path), Path(expected_registry_path)
    inputs = {registry_path, previous_path, expected_path}
    inputs.update(evidence_root / name for name in (*OUTPUTS, *MAPPINGS.values()))
    inputs.update(root / name for name in MAPPINGS.values())
    manifest_path = evidence_root / "publication_manifest.json"
    inputs.add(manifest_path)
    pinned = {path: path.read_bytes() for path in inputs}
    read = lambda path: json.loads(pinned[Path(path)].decode("utf-8"))
    registry, previous = read(registry_path), read(previous_path)
    require(registry == read(expected_path), "registry source/roster changed since authentication")
    from build_publication_manifest import validate_manifest
    manifest = read(manifest_path)
    validate_manifest(manifest)
    require(evidence_hash(pinned[previous_path]) == manifest["lanes"]["candidacy_status"]["sha256"],
            "previous registry differs from authenticated publication")
    prepared = {}
    for provider, mapping_file in MAPPINGS.items():
        require(evidence_hash(pinned[root / mapping_file]) == evidence_hash(pinned[evidence_root / mapping_file]),
                "reviewed provider mapping changed during rebase")
        snapshot_file, history_file = f"candidate_{provider}.json", f"candidate_{provider}_history.json"
        # Bind retained evidence and reviewed mappings to the last publication;
        # structural validation alone cannot authenticate a changed review URL.
        for lane_name in (f"candidate_{provider}", f"candidate_{provider}_history"):
            lane = manifest["lanes"][lane_name]
            require(lane["valid"], "prior provider publication is invalid")
            for record in (lane, *lane["related_files"]):
                name = record["file"]
                require(record["available"] and record["sha256"] == evidence_hash(pinned[evidence_root / name]),
                        "published provider evidence or reviewed mapping changed: " + name)
        snapshot, history = reconcile_provider(
            provider, read(evidence_root / snapshot_file), read(evidence_root / history_file),
            read(root / mapping_file), previous, registry,
        )
        for name, payload in ((snapshot_file, snapshot), (history_file, history)):
            original = pinned[evidence_root / name]
            prepared[name] = original if json.loads(original) == payload else (
                json.dumps(payload, ensure_ascii=False, indent=2, allow_nan=False) + "\n"
            ).encode("utf-8")
    require(all(path.read_bytes() == data for path, data in pinned.items()),
            "source revision, roster or provider evidence changed during reconciliation")
    for name, data in prepared.items():
        if (root / name).read_bytes() != data:
            atomic_write(root / name, data)
    return prepared


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--previous-registry", required=True)
    parser.add_argument("--expected-registry", required=True)
    parser.add_argument("--evidence-root")
    args = parser.parse_args()
    reconcile(Path.cwd(), previous_registry_path=args.previous_registry,
              expected_registry_path=args.expected_registry, evidence_root=args.evidence_root)


if __name__ == "__main__":
    main()
