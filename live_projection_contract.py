"""Compact current coverage from published classifications; no history or I/O."""
from copy import deepcopy
from datetime import datetime, timezone
from typing import Any

from fetch_news_wire import validate_campaign_agenda, validate_policy_agenda
from agenda_page_contract import CANONICAL_AGENDA_IDS, agenda_source_day_rows
from issue_page_contract import (
    CANONICAL_ISSUE_IDS, build_issue_period_metric, _campaign_agenda_summary,
    CURRENT_ITEM_MIN, CURRENT_SOURCE_DAY_MIN, CURRENT_PUBLISHER_MIN,
)

SCHEMA_VERSION = "1.0"
PERIOD_KEYS = (
    "period_days", "period_start", "period_end", "period_end_partial",
    "comparison_days", "previous_start", "previous_end", "latest_start", "latest_end",
)


def _source(news: Any, field: str) -> tuple[dict, dict]:
    if not isinstance(news, dict):
        raise ValueError("news_wire must be an object")
    stamp = news.get("generated_at")
    if not isinstance(stamp, str):
        raise ValueError("generated_at must be a source timestamp")
    instant = datetime.fromisoformat(stamp.replace("Z", "+00:00"))
    if instant.tzinfo is None:
        raise ValueError("generated_at requires a timezone")
    agenda = news.get(field)
    validator = validate_campaign_agenda if field == "campaign_agenda" else validate_policy_agenda
    validator(agenda, news.get("relevant_news"))
    evolution = agenda["evolution"]
    if evolution["period_end"] != instant.astimezone(timezone.utc).date().isoformat():
        raise ValueError("rolling period does not match source snapshot UTC day")
    return agenda, evolution


def _envelope(news: dict, agenda: dict, evolution: dict, family: str) -> dict:
    counts = {key: agenda[key] for key in (
        "input_item_count", "classified_item_count", "unclassified_item_count",
    )}
    if family == "issues":
        counts["label_assignment_count"] = agenda["label_assignment_count"]
    return {
        "schema_version": SCHEMA_VERSION, "family": family,
        "generated_at": news["generated_at"], "source_snapshot": news["generated_at"],
        "source": "news_wire.json:" + ("campaign_agenda" if family == "agenda" else "policy_agenda"),
        "period": {key: evolution[key] for key in PERIOD_KEYS},
        "counts": counts, "topics": [],
    }


def _total(series: list, period: dict, window: str, field: str) -> int:
    return sum(point[field] for point in series
               if period[window + "_start"] <= point["date"] <= period[window + "_end"])


def _supporting_evidence(agenda: dict) -> list[dict]:
    """Bounded published evidence, with no generated prose or candidate positions."""
    records = {}
    for topic in agenda["topics"]:
        for item in topic["supporting_items"]:
            key = (item["id"], item["url"])
            record = records.setdefault(key, {
                field: item[field] for field in ("id", "headline", "url", "publisher", "published_at")
            })
            record.setdefault("topic_ids", []).append(topic["id"])
    for record in records.values():
        record["topic_ids"].sort()
    return sorted(records.values(), key=lambda row: (row["published_at"], row["id"], row["url"]), reverse=True)[:6]


def build_agenda_live_projection(news: Any) -> dict:
    agenda, evolution = _source(news, "campaign_agenda")
    result = _envelope(news, agenda, evolution, "agenda")
    base = {topic["id"]: topic for topic in agenda["topics"]}
    series = {topic["id"]: topic for topic in evolution["topics"]}
    if not set(base).issubset(CANONICAL_AGENDA_IDS):
        raise ValueError("noncanonical Agenda topic")
    dates = next(iter(series.values()))["daily_activity"] if series else []
    if not dates:
        from datetime import date, timedelta
        start = date.fromisoformat(evolution["period_start"])
        dates = [{"date": (start + timedelta(days=i)).isoformat()}
                 for i in range(evolution["period_days"])]
    daily = {key: series[key]["daily_activity"] if key in series else [
        {"date": point["date"], "item_count": 0, "source_day_count": 0} for point in dates
    ] for key in CANONICAL_AGENDA_IDS}
    metrics = {}
    for window in ("previous", "latest"):
        metrics[window] = {row.topic_id: row for row in agenda_source_day_rows(
            {key: _total(daily[key], evolution, window, "source_day_count")
             for key in CANONICAL_AGENDA_IDS}, allow_empty_observation=True,
        )}
    result["denominator"] = {
        "id": "all_canonical_agenda_topic_source_days", "unit": "agenda_topic_source_day",
        "single_label": True, "multilabel": False,
        "current": sum(t["source_day_count"] for t in series.values()),
        "previous": next(iter(metrics["previous"].values())).denominator,
        "latest": next(iter(metrics["latest"].values())).denominator,
    }
    result["counts"]["publisher_count"] = len({name for t in base.values() for name in t["publisher_names"]})
    result["counts"]["rolling_assignment_count"] = sum(t["item_count"] for t in series.values())
    for key in CANONICAL_AGENDA_IDS:
        previous, latest = metrics["previous"][key], metrics["latest"][key]
        t = series.get(key, {})
        result["topics"].append({
            "id": key, "item_count": t.get("item_count", 0),
            "source_day_count": t.get("source_day_count", 0),
            "publisher_count": base.get(key, {}).get("publisher_count", 0),
            "active_day_count": t.get("active_day_count", 0),
            "display_eligible": base.get(key, {}).get("display_eligible", False),
            "daily_activity": daily[key],
            "previous_share": previous.raw_share, "latest_share": latest.raw_share,
            "movement_pp": (latest.raw_share - previous.raw_share) * 100,
            "matched_term_counts": t.get("matched_term_counts", []),
        })
    result["supporting_evidence"] = _supporting_evidence(agenda)
    return deepcopy(result)


def build_issue_live_projection(news: Any) -> dict:
    policy, evolution = _source(news, "policy_agenda")
    # Issues' companion panel uses article composition, not Agenda source-day shares.
    _source(news, "campaign_agenda")
    result = _envelope(news, policy, evolution, "issues")
    topics = {t["id"]: t for t in evolution["topics"]}
    base = {t["id"]: t for t in policy["topics"]}
    if not set(topics).issubset(CANONICAL_ISSUE_IDS) or not set(base).issubset(CANONICAL_ISSUE_IDS):
        raise ValueError("noncanonical Issues topic")
    accepted = evolution["accepted_daily_activity"]
    # Valid sparse published snapshots omit zero topics; canonical metric rows
    # still require zero observations for every day and every Issue.
    for key in CANONICAL_ISSUE_IDS:
        topics.setdefault(key, {
            "id": key, "item_count": 0, "source_day_count": 0,
            "publisher_count": 0, "active_day_count": 0,
            "daily_activity": [
                {"date": point["date"], "item_count": 0, "source_day_count": 0,
                 "accepted_source_day_count": point["source_day_count"], "incidence": 0.0}
                for point in accepted
            ],
        })
        base.setdefault(key, {
            "publisher_names": [], "candidate_counts": [],
            "display_eligible": False, "subtopic_counts": [],
        })
    metrics = {}
    for window in ("previous", "latest", "period"):
        metrics[window] = build_issue_period_metric(
            list(topics.values()), start_date=evolution[window + "_start"],
            end_date=evolution[window + "_end"], daily_denominators=accepted,
            allow_empty_denominator=True,
        )
    result["denominator"] = {
        "id": "accepted_relevant_news_source_days", "unit": "issue_source_day",
        "single_label": False, "multilabel": True,
        "corpus_item_count": policy["input_item_count"],
        **{("current" if key == "period" else key): metric.denominator
           for key, metric in metrics.items()},
    }
    result["counts"]["rolling_assignment_count"] = sum(t["item_count"] for t in topics.values())
    result["accepted_daily_activity"] = accepted
    result["counts"]["publisher_count"] = len({name for t in base.values() for name in t["publisher_names"]})
    result["counts"]["candidate_count"] = len({item["candidate"] for t in base.values() for item in t["candidate_counts"]})
    for key in CANONICAL_ISSUE_IDS:
        t = topics[key]
        previous = next(row for row in metrics["previous"].rows if row.issue_id == key)
        latest = next(row for row in metrics["latest"].rows if row.issue_id == key)
        current = next(row for row in metrics["period"].rows if row.issue_id == key)
        result["topics"].append({
            "id": key, **{field: t[field] for field in (
                "item_count", "source_day_count", "publisher_count", "active_day_count", "daily_activity",
            )}, "display_eligible": base[key]["display_eligible"],
            "current_qualified": (t["item_count"] >= CURRENT_ITEM_MIN
                                  and t["source_day_count"] >= CURRENT_SOURCE_DAY_MIN
                                  and t["publisher_count"] >= CURRENT_PUBLISHER_MIN),
            "current_share": current.raw_share,
            "previous_share": round(previous.raw_share, 6),
            "latest_share": round(latest.raw_share, 6),
            "movement_pp": round((latest.raw_share - previous.raw_share) * 100, 3),
            "subtopic_counts": base[key]["subtopic_counts"],
        })
    companion = _campaign_agenda_summary(news)
    companion["topics"] = [{key: value for key, value in topic.items() if key != "label"}
                           for topic in companion["topics"]]
    # Keep zero canonical topics addressable even when the current source omits
    # them; this is zero-fill, not classification or route lifecycle inference.
    present = {topic["id"] for topic in companion["topics"]}
    for key in CANONICAL_AGENDA_IDS:
        if key not in present:
            companion["topics"].append({
                "id": key, "position": len(companion["topics"]),
                "previous_item_count": 0, "latest_item_count": 0,
                "previous_share": 0.0, "latest_share": 0.0,
            })
    result["campaign_agenda"] = companion
    result["supporting_evidence"] = _supporting_evidence(policy)
    return deepcopy(result)


def validate_live_projection(projection: Any, news: Any, family: str) -> None:
    if family not in ("agenda", "issues"):
        raise ValueError("unknown live projection family")
    builder = build_agenda_live_projection if family == "agenda" else build_issue_live_projection
    if projection != builder(news):
        raise ValueError(f"{family} live projection differs from authoritative source snapshot")
