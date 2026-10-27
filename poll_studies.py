"""Finite reviewed study projections; never mutate numerical observations.

The original Python JSON-object pins preserve the audit's number types. The
browser pins hash the same complete objects with integral JSON numbers rendered
as integers, since JavaScript does not distinguish 100 from 100.0.
"""
from __future__ import annotations

import argparse
from functools import lru_cache
import hashlib
import json
from pathlib import Path

ROOT = Path(__file__).resolve().parent
BINDING_PATH = ROOT / "poll_study_bindings.json"
BINDING_SHA256 = "38126d09b740bdb82aba2d6dd6318640a560d6209265a0e3a28e6617df4b463d"


def object_digest(value):
    return hashlib.sha256(json.dumps(value, sort_keys=True, ensure_ascii=True,
                                     separators=(",", ":")).encode()).hexdigest()


def _browser_value(value):
    if isinstance(value, float) and value.is_integer():
        return int(value)
    if isinstance(value, dict):
        return {key: _browser_value(child) for key, child in value.items()}
    if isinstance(value, list):
        return [_browser_value(child) for child in value]
    return value


def load_binding(path=BINDING_PATH):
    value = json.loads(Path(path).read_text(encoding="utf-8"))
    if object_digest(value) != BINDING_SHA256:
        raise ValueError("Reviewed polling study binding changed")
    return value


@lru_cache(maxsize=1)
def _binding():
    return load_binding()


def reviewed_member(event):
    binding = _binding()
    member = next((row for row in binding["members"]
                   if row["event_id"] == event.get("event_id")), None)
    if member is not None:
        if (object_digest(event) != member["object_sha256"]
                or object_digest(_browser_value(event)) != member["browser_object_sha256"]):
            raise ValueError("Reviewed polling study event changed: " + event["event_id"])
    return member


def validate_study_membership(events):
    """A collection may predate the study; a partial/duplicated binding fails."""
    ids = [event.get("event_id") for event in events]
    expected = {row["event_id"] for row in _binding()["members"]}
    present = expected.intersection(ids)
    if present and (present != expected or any(ids.count(key) != 1 for key in expected)):
        raise ValueError("Reviewed polling study requires its three exact events")
    canonical_key = (_binding()["canonical_pollster"], _binding()["fieldwork_start"],
                     _binding()["fieldwork_end"], _binding()["sample_size"])
    for event in events:
        reviewed_member(event)
        if present and event.get("event_id") not in expected and package_key(event) == canonical_key:
            raise ValueError("Unreviewed event collides with the authenticated polling study")


def projected_pollster(event):
    return _binding()["canonical_pollster"] if reviewed_member(event) else event["pollster"]


def package_key(event):
    return (projected_pollster(event), event["fieldwork_start"],
            event["fieldwork_end"], event.get("sample_size"))


def scenario_order(event):
    member = reviewed_member(event)
    return member["canonical_anchor_index"] if member else 0


def compatibility_pages(waves):
    binding = _binding()
    matches = [wave for wave in waves if wave["wave_id"] == binding["canonical_wave_id"]]
    if not matches:
        return []
    wave = matches[0]
    if {s["event_id"] for s in wave["scenarios"]} != {m["event_id"] for m in binding["members"]}:
        raise ValueError("Canonical reviewed study has incorrect membership")
    return [{**binding["compatibility"], "canonical_wave_id": wave["wave_id"],
             "canonical_path_fr": wave["page_path_fr"],
             "canonical_path_en": wave["page_path_en"]}]


def authenticate_document(path):
    actual = hashlib.sha256(Path(path).read_bytes()).hexdigest()
    if actual != _binding()["source_document"]["sha256"]:
        raise ValueError("Reviewed Cluster17 original PDF hash changed")
    return actual


def browser_script():
    template = (ROOT / "poll_study_runtime.js").read_text(encoding="utf-8")
    return template.replace("/* REVIEWED_STUDY_BINDING */", json.dumps(
        load_binding(), ensure_ascii=True, sort_keys=True, separators=(",", ":")))


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--check", action="store_true")
    parser.add_argument("--authenticate-pdf", type=Path)
    args = parser.parse_args()
    if args.authenticate_pdf:
        print("Authenticated original PDF: " + authenticate_document(args.authenticate_pdf))
    output = ROOT / "assets/poll-study-bindings.js"
    expected = browser_script()
    if args.check:
        if not output.exists() or output.read_text(encoding="utf-8") != expected:
            raise ValueError("Reviewed study browser projection is out of date")
    else:
        output.write_text(expected, encoding="utf-8", newline="\n")


if __name__ == "__main__":
    main()
