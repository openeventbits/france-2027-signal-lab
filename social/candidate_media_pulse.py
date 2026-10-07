"""Canonical candidate visibility comparison for the existing late-bound 16:45 slot.

History owns counts; Signals and the active registry own readiness and eligibility.
Missing or stale inputs leave the existing slot unavailable.
"""

from __future__ import annotations

import json
import math
import re
import sys
from dataclasses import dataclass
from datetime import date, timedelta
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from candidate_candidacy_status import active_candidate_records
from candidate_visibility_history_contract import (
    CAMPAIGN_LANE, GENERAL_LANE, validate_candidate_visibility_history,
)
from coverage_metric_contract import display_triplet
from social.newsroom_products import _fr_percent, _fr_delta


PRODUCT_TYPE = "candidate_media_pulse_current"
METRIC_ID = "candidate_share_of_lane_records"
AGGREGATION_UNIT = "candidate_linked_record"
DENOMINATOR_ID = "candidate_linked_lane_records"
WINDOW_MODE = "complete_day_or_week"
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
    lane: str
    window_mode: str
    previous_start: str
    previous_end: str
    previous_percentage: float
    current_percentage: float
    delta_pp: float
    current_numerator: int
    current_denominator: int
    previous_numerator: int
    previous_denominator: int


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
    """Preserve X Unicode weights and the fixed 23-unit URL weight."""
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
    visibility_history: dict[str, Any],
    site_root: Path = ROOT,
    utc_date: date | None = None,
) -> CandidateMediaPulseProduct | None:
    # Runtime supplies the UTC date; planner_date still owns the Paris cadence.
    utc_date = utc_date or planner_date
    validate_candidate_visibility_history(visibility_history)
    period = visibility_history["period"]
    end = date.fromisoformat(period["end_date"])
    if end != utc_date - timedelta(days=1):
        return None
    visibility = candidate_signals["visibility"]
    if (visibility["current_period"]["end_date"] != planner_date.isoformat()
            or visibility["method"] != "share_of_candidate_linked_records"
            or visibility["primary_scopes"] != ["election", "campaign"]):
        return None
    start = date.fromisoformat(visibility["current_period"]["start_date"])
    if (planner_date - start).days != 6:
        raise ValueError("candidate Signals readiness requires seven inclusive dates")

    days = 7 if planner_date.weekday() == 0 else 1
    window_mode = "complete_week" if days == 7 else "complete_day"
    current_dates = tuple((end - timedelta(days=offset)).isoformat()
                          for offset in reversed(range(days)))
    previous_dates = tuple((end - timedelta(days=days + offset)).isoformat()
                           for offset in reversed(range(days)))
    active = {row["candidate_id"]: row for row in active_candidate_records(candidacy_registry)}
    signals = {}
    for row in candidate_signals["candidates"]:
        identifier = row["candidate_id"]
        if identifier in signals:
            raise ValueError("duplicate Candidate Signals identity")
        signals[identifier] = row

    ranked = []
    # Stable general-then-campaign lane order is the final tie-break.
    for candidate in visibility_history["candidates"]:
        identifier = candidate["candidate_id"]
        if identifier not in active or identifier not in signals:
            continue
        name = candidate["candidate_name"]
        if name != active[identifier]["candidate_name"] or name != signals[identifier]["candidate_name"]:
            raise ValueError("candidate history identity differs from active registry or Signals")
        for lane_index, lane in enumerate((GENERAL_LANE, CAMPAIGN_LANE)):
            # Reuse existing reported-evidence readiness, without borrowing its values.
            readiness = signals[identifier][lane]
            if readiness.get("evidence_state") != "reported" or readiness.get("share") is None:
                continue
            share = readiness["share"]
            if (isinstance(share, bool) or not isinstance(share, (int, float))
                    or not math.isfinite(share) or not 0 <= share <= 1
                    or type(readiness.get("record_count")) is not int
                    or readiness["record_count"] <= 0):
                raise ValueError("invalid reported candidate visibility readiness")
            if (lane == GENERAL_LANE and
                    visibility["general_current_period"]["end_date"] != planner_date.isoformat()):
                continue
            denominator = {row["date"]: row["record_count"] for row in
                           visibility_history["lanes"][lane]["daily_denominators"]}
            numerator = {row["date"]: row["record_count"] for row in candidate[lane]["daily_series"]}
            required = previous_dates + current_dates
            if any(day not in denominator or day not in numerator or denominator[day] <= 0
                   for day in required):
                continue
            previous_n = sum(numerator[day] for day in previous_dates)
            previous_d = sum(denominator[day] for day in previous_dates)
            current_n = sum(numerator[day] for day in current_dates)
            current_d = sum(denominator[day] for day in current_dates)
            previous_raw = previous_n / previous_d * 100
            current_raw = current_n / current_d * 100
            previous, current, delta = display_triplet(previous_raw, current_raw)
            ranked.append(((-abs(current_raw - previous_raw), -(current_n + previous_n),
                            identifier, lane_index), candidate, lane,
                           previous, current, delta, previous_n, previous_d, current_n, current_d))
    if not ranked:
        return None
    (_, candidate, lane, previous, current, delta,
     previous_n, previous_d, current_n, current_d) = min(ranked, key=lambda entry: entry[0])
    identifier = candidate["candidate_id"]
    name = candidate["candidate_name"]
    canonical = canonical_candidate_url(route_registry, identifier)
    campaign = lane == CAMPAIGN_LANE
    title = "VISIBILITÉ DE CAMPAGNE" if campaign else "VISIBILITÉ MÉDIATIQUE"
    horizon = "7 JOURS · VS 7 JOURS PRÉCÉDENTS" if days == 7 else "24 H · VS 24 H PRÉCÉDENTES"
    # Lane denominator counts records once even with multiple candidate matches.
    # It is not the sum of candidate shares, nor an active-field-only denominator.
    base = "des articles de campagne liés aux candidats suivis" if campaign else "des articles hors campagne liés aux candidats suivis"
    boundary = "Visibilité de campagne, pas intentions de vote." if campaign else "Visibilité médiatique, pas intentions de vote."
    text = (f"{title} · {horizon}\n\n"
            f"{name} : {_fr_percent(current)} {base}, contre {_fr_percent(previous)}. "
            f"Écart : {_fr_delta(delta)}.\n\n{boundary}\n\n{canonical}")
    length = weighted_x_length(text)
    if length > MAX_X_WEIGHTED_LENGTH:
        # The headline and boundary already identify the lane; shorten only the base.
        text = text.replace(base, "des articles liés aux candidats suivis")
        # General's out-of-campaign scope must remain explicit.
        if not campaign:
            text = text.replace("Visibilité médiatique,", "Visibilité hors campagne,")
        length = weighted_x_length(text)
    if length > MAX_X_WEIGHTED_LENGTH:
        raise ValueError("candidate Media Pulse exceeds X weighted limit")
    return CandidateMediaPulseProduct(
        # Keep the queue's established type and publication-date identity.
        product_id=f"{PRODUCT_TYPE}:{identifier}:{planner_date.isoformat()}:fr",
        product_type=PRODUCT_TYPE, locale="fr", slot=SLOT,
        candidate_id=identifier, candidate_name=name,
        current_start=current_dates[0], current_end=current_dates[-1],
        stored_share=current_n / current_d, displayed_percentage=_fr_percent(current),
        destination_url=canonical, score=abs(current_n / current_d * 100 - previous_n / previous_d * 100),
        text=text, weighted_length=length, lane=lane, window_mode=window_mode,
        previous_start=previous_dates[0], previous_end=previous_dates[-1],
        previous_percentage=previous, current_percentage=current, delta_pp=delta,
        current_numerator=current_n, current_denominator=current_d,
        previous_numerator=previous_n, previous_denominator=previous_d,
    )
