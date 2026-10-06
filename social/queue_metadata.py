"""Additive queue identity copied from product contracts, never metric arithmetic.

Schema 1 readers already tolerate extra fields. Old items have no metadata and
are read unchanged. Unresolved candidate/Radar boundaries remain null until a
successful execution records the actual product, rather than morning values.
"""
from __future__ import annotations

from datetime import datetime
from typing import Any

FIELDS = (
    "post_type", "family", "metric_id", "aggregation_unit", "denominator_id",
    "window_mode", "window_start", "window_end", "comparison_start",
    "comparison_end", "rank_kind", "canonical_url", "late_bound",
)


def identity(*, post_type: str, family: str, late_bound: bool = False, **values: Any) -> dict[str, Any]:
    result = dict.fromkeys(FIELDS)
    result.update(post_type=post_type, family=family, late_bound=late_bound, **values)
    return validate(result)


def validate(value: dict[str, Any]) -> dict[str, Any]:
    if set(value) != set(FIELDS):
        raise ValueError("structured queue identity requires its complete field set")
    for name in FIELDS[:-1]:
        if value[name] is not None and (not isinstance(value[name], str) or not value[name].strip()):
            raise ValueError(f"invalid queue metadata {name}")
    if not value["post_type"] or not value["family"] or type(value["late_bound"]) is not bool:
        raise ValueError("queue identity requires a post type, family and boolean late_bound")
    for start, end in (("window_start", "window_end"), ("comparison_start", "comparison_end")):
        if (value[start] is None) != (value[end] is None):
            raise ValueError("queue period boundaries must be supplied together")
        if value[start] is not None:
            try:
                first = datetime.fromisoformat(value[start].replace("Z", "+00:00"))
                last = datetime.fromisoformat(value[end].replace("Z", "+00:00"))
                if first > last:
                    raise ValueError("reversed queue period")
            except (ValueError, TypeError) as error:
                raise ValueError("invalid structured queue period") from error
    return dict(value)


def from_item(item: dict[str, Any]) -> dict[str, Any] | None:
    if not any(name in item for name in FIELDS):
        return None
    return validate({name: item[name] for name in FIELDS if name in item})


def newsroom(product: Any) -> dict[str, Any]:
    movement = product.rank_kind == "movers"
    return identity(post_type="newsroom", family=product.family,
        metric_id=product.metric_id, aggregation_unit=product.aggregation_unit,
        denominator_id=product.denominator_id, window_mode=product.window_mode,
        window_start=product.current_start, window_end=product.current_end,
        comparison_start=product.previous_start if movement else None,
        comparison_end=product.previous_end if movement else None,
        rank_kind=product.rank_kind, canonical_url=product.destination_url)


def candidate(product: Any = None) -> dict[str, Any]:
    import candidate_media_pulse as contract
    return identity(post_type="candidate_media_pulse", family="candidate", late_bound=True,
        metric_id=contract.METRIC_ID, aggregation_unit=contract.AGGREGATION_UNIT,
        denominator_id=contract.DENOMINATOR_ID, window_mode=contract.WINDOW_MODE,
        window_start=product.current_start if product else None,
        window_end=product.current_end if product else None,
        canonical_url=product.destination_url if product else None)


def radar(product: Any = None) -> dict[str, Any]:
    import radar_media as contract
    return identity(post_type="radar_media", family="media", late_bound=True,
        metric_id=contract.METRIC_ID, aggregation_unit=contract.AGGREGATION_UNIT,
        denominator_id=contract.DENOMINATOR_ID, window_mode=contract.WINDOW_MODE,
        window_start=product.window_start if product else None,
        window_end=product.window_end if product else None, canonical_url=contract.URL)


def flagship(monday: Any, product: Any = None) -> dict[str, Any]:
    import weekly_flagship as contract
    previous_start, previous_end, start, end = contract.expected_weeks(monday)
    if product is not None:
        previous_start, previous_end = product.issues.previous_start, product.issues.previous_end
        start, end = product.issues.current_start, product.issues.current_end
    # A composite has two authorities, not one invented metric/denominator.
    return identity(post_type="weekly_flagship", family="cross_signal", late_bound=True,
        window_mode=contract.metrics.WINDOW_COMPLETE_WEEK, window_start=start, window_end=end,
        comparison_start=previous_start, comparison_end=previous_end, canonical_url=contract.URL)


def events(canonical_url: str) -> dict[str, Any]:
    return identity(post_type="events", family="campaign_events", canonical_url=canonical_url)
