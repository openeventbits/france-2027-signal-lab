"""Current dossier Media Pulse resolved at execution of the French 16:45 slot.

This product uses Candidate Signals, never complete-day visibility history.
The morning queue stores an empty instruction. Invalid sources or destination
parity cause execution to skip without substituting a different product.
"""

from __future__ import annotations

import json
import math
import re
import sys
from dataclasses import dataclass
from datetime import date
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from candidate_candidacy_status import active_candidate_records
from social.newsroom_products import _range_piece


PRODUCT_TYPE = "candidate_media_pulse_current"
SLOT = "16:45"
MAX_X_WEIGHTED_LENGTH = 280
URL_RE = re.compile(r"https?://\S+", re.IGNORECASE)


@dataclass(frozen=True)
class CandidateMediaPulseProduct:
    product_id: str
    product_type: str
    locale: str
    slot: str
    candidate_id: str
    candidate_name: str
    current_start: str
    current_end: str
    stored_share: float
    displayed_percentage: str
    destination_url: str
    score: float
    text: str
    weighted_length: int


@dataclass(frozen=True)
class CandidateSlotInstruction:
    product_id: str
    slot: str = SLOT
    text: str = ""
    score: None = None


def slot_instruction(planner_date: date) -> CandidateSlotInstruction:
    return CandidateSlotInstruction(
        product_id=f"{PRODUCT_TYPE}:slot:{planner_date.isoformat()}:fr",
    )


def weighted_x_length(text: str) -> int:
    """X weights for this single-emoji template, with URLs weighted as 23.

    The fixed eye emoji is two units, as is the not-equal sign. The X
    single-weight Unicode ranges also cover the registry's French names.
    """
    def text_weight(value: str) -> int:
        return sum(
            1 if (
                ord(char) <= 0x10FF
                or 0x2000 <= ord(char) <= 0x200D
                or 0x2010 <= ord(char) <= 0x201F
                or 0x2032 <= ord(char) <= 0x2037
            ) else 2
            for char in value
        )

    total = 0
    cursor = 0
    for match in URL_RE.finditer(text):
        total += text_weight(text[cursor:match.start()]) + 23
        cursor = match.end()
    return total + text_weight(text[cursor:])


def canonical_candidate_url(
    routes: dict[str, Any], candidate_id: str,
) -> str:
    matches = [
        route for route in routes["routes"]
        if route.get("family") == "candidates"
        and route.get("kind") == "candidate-detail"
        and route.get("entity_id") == candidate_id
        and route.get("language") == "fr"
    ]
    if len(matches) != 1:
        raise ValueError("expected exactly one canonical FR candidate-detail route")
    canonical = matches[0].get("canonical_url")
    if canonical != f"https://france2027.app/candidates/{candidate_id}/":
        raise ValueError("candidate route is not the canonical FR27 detail URL")
    return canonical


def load_json(path: Path) -> dict[str, Any]:
    value = json.loads(path.read_text(encoding="utf-8-sig"))
    if not isinstance(value, dict):
        raise ValueError(f"{path.name} must contain an object")
    return value


def build_product(
    *,
    candidate_signals: dict[str, Any],
    candidacy_registry: dict[str, Any],
    route_registry: dict[str, Any],
    planner_date: date,
    site_root: Path = ROOT,
) -> CandidateMediaPulseProduct | None:
    visibility = candidate_signals["visibility"]
    period = visibility["current_period"]
    start = date.fromisoformat(period["start_date"])
    end = date.fromisoformat(period["end_date"])
    if end != planner_date:
        return None
    if (end - start).days != 6:
        raise ValueError("candidate Media Pulse must use seven inclusive dates")
    if (
        visibility["method"] != "share_of_candidate_linked_records"
        or visibility["primary_scopes"] != ["election", "campaign"]
    ):
        raise ValueError("candidate source is not dossier campaign_attention")

    active = {
        record["candidate_id"]: record
        for record in active_candidate_records(candidacy_registry)
    }
    ranked = []
    seen = set()
    for candidate in candidate_signals["candidates"]:
        identifier = candidate["candidate_id"]
        if identifier in seen:
            raise ValueError("duplicate Candidate Signals identity")
        seen.add(identifier)
        if identifier not in active:
            continue
        metric = candidate["campaign_attention"]
        share = metric.get("share")
        if metric.get("evidence_state") != "reported" or share is None:
            continue
        if (
            isinstance(share, bool)
            or not isinstance(share, (int, float))
            or not math.isfinite(share)
            or not 0 <= share <= 1
        ):
            raise ValueError("invalid reported Media Pulse share")
        count = metric.get("record_count")
        if type(count) is not int or count <= 0:
            raise ValueError("invalid reported Media Pulse record count")
        name = candidate["candidate_name"]
        if name != active[identifier]["candidate_name"]:
            raise ValueError("Candidate Signals name differs from registry")
        # Match the dossier's one-decimal percentage before ranking.
        display = float(f"{share * 100:.1f}")
        ranked.append(((-display, -count, identifier), candidate))
    if not ranked:
        return None

    candidate = min(ranked, key=lambda entry: entry[0])[1]
    identifier = candidate["candidate_id"]
    name = candidate["candidate_name"]
    metric = candidate["campaign_attention"]
    canonical = canonical_candidate_url(route_registry, identifier)
    dossier = load_json(site_root / "candidates" / identifier / "data.json")
    page_metric = dossier["dossier"]["media_pulse"]
    if (
        dossier["candidate_id"] != identifier
        or page_metric.get("evidence_state") != "reported"
        or page_metric.get("share") != metric["share"]
        or page_metric.get("record_count") != metric["record_count"]
        or dossier["media"]["period"] != {
            "start_date": period["start_date"],
            "end_date": period["end_date"],
        }
    ):
        raise ValueError("selected candidate dossier Media Pulse parity failed")

    display = f"{metric['share'] * 100:.1f}".replace(".", ",") + " %"
    text = (
        "VISIBILITÉ MÉDIATIQUE 👀\n"
        f"{_range_piece(start.isoformat(), end.isoformat(), 'fr')}\n\n"
        f"{name} — {display}\n\n"
        "Couverture élection + campagne suivie.\n"
        "Associations non exclusives · ≠ soutien.\n"
        f"{canonical}"
    )
    length = weighted_x_length(text)
    if length > MAX_X_WEIGHTED_LENGTH:
        raise ValueError("candidate Media Pulse exceeds X weighted limit")
    return CandidateMediaPulseProduct(
        product_id=f"{PRODUCT_TYPE}:{identifier}:{end.isoformat()}:fr",
        product_type=PRODUCT_TYPE,
        locale="fr",
        slot=SLOT,
        candidate_id=identifier,
        candidate_name=name,
        current_start=start.isoformat(),
        current_end=end.isoformat(),
        stored_share=metric["share"],
        displayed_percentage=display,
        destination_url=canonical,
        score=float(f"{metric['share'] * 100:.1f}"),
        text=text,
        weighted_length=length,
    )
