"""Late-bound publisher composition from the shared dashboard Media authority.

Counts, ordering and raw shares belong to buildMediaViewModel. This consumer
validates the source and published destination, rounds display endpoints and
compares only with the last successful Radar publication.
"""
from __future__ import annotations

import hashlib
import json
import math
import re
import sys
from dataclasses import dataclass
from datetime import date, datetime, timedelta, timezone
from pathlib import Path
from typing import Any
from zoneinfo import ZoneInfo

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from build_search_entrypoints import media_snapshot_model
from coverage_metric_contract import display_round
from social.candidate_media_pulse import load_json, weighted_x_length
from social.newsroom_products import _date_piece

PRODUCT_TYPE = "radar_media_publishers_current"
METRIC_ID = "accepted_election_news_publisher_share_snapshot_30d"
AGGREGATION_UNIT = "accepted_election_news_article"
DENOMINATOR_ID = "all_accepted_election_news_articles"
WINDOW_MODE = "rolling_30d_snapshot"
SLOT = "18:30"
URL = "https://france2027.app/"
STATE_KEY = "radar_media_last_published"
PARIS = ZoneInfo("Europe/Paris")


class RadarError(ValueError):
    pass


@dataclass(frozen=True)
class RadarSlotInstruction:
    product_id: str
    slot: str = SLOT
    text: str = ""
    score: None = None


@dataclass(frozen=True)
class RadarProduct:
    product_id: str
    generated_at: str
    window_start: str
    window_end: str
    denominator: int
    publisher_count: int
    rows: tuple[dict[str, Any], ...]
    payload: dict[str, Any]
    fingerprint: str
    text: str
    weighted_length: int


def slot_instruction(planner_date: date) -> RadarSlotInstruction:
    return RadarSlotInstruction(f"{PRODUCT_TYPE}:slot:{planner_date.isoformat()}:fr")


def fingerprint(payload: dict[str, Any]) -> str:
    encoded = json.dumps(payload, ensure_ascii=False, sort_keys=True, separators=(",", ":"))
    return hashlib.sha256(encoded.encode("utf-8")).hexdigest()


def meaningful_change(payload: dict[str, Any], last_publication: Any) -> bool:
    if last_publication is None:
        return True
    if not isinstance(last_publication, dict):
        raise RadarError("invalid last successful Radar publication")
    previous = last_publication.get("payload")
    if (not isinstance(previous, dict) or set(previous) != {"family", "rows"}
            or previous.get("family") != PRODUCT_TYPE
            or not isinstance(previous.get("rows"), list) or len(previous["rows"]) != 3
            or any(not isinstance(row, dict) or set(row) != {"label", "display_tenths"}
                   or not isinstance(row.get("label"), str)
                   or not row["label"].strip() or type(row.get("display_tenths")) is not int
                   or not 0 <= row["display_tenths"] <= 1000 for row in previous["rows"])
            or last_publication.get("fingerprint") != fingerprint(previous)):
        raise RadarError("invalid last successful Radar fingerprint")
    return payload != previous


def _timestamp(value: Any) -> datetime:
    if not isinstance(value, str):
        raise RadarError("missing Media timestamp")
    parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
    if parsed.tzinfo is None or parsed.utcoffset() is None:
        raise RadarError("Media timestamp must include timezone")
    return parsed.astimezone(timezone.utc)


def canonical_home(routes: dict[str, Any]) -> str:
    matches = [row for row in routes["routes"] if row.get("family") == "core"
               and row.get("kind") == "home" and row.get("entity_id") == "home"
               and row.get("language") == "fr"]
    if len(matches) != 1 or matches[0].get("canonical_url") != URL or matches[0].get("path") != "/":
        raise RadarError("Radar requires the exact canonical FR homepage")
    return URL


def published_media(root: Path) -> dict[str, Any]:
    document = (root / "index.html").read_text(encoding="utf-8")
    matches = re.findall(r'<script[^>]*id="published-media-snapshot"[^>]*>(.*?)</script>', document, re.S)
    if len(matches) != 1 or not re.search(r'<link\s+rel="canonical"\s+href="https://france2027\.app/"', document):
        raise RadarError("missing canonical published Media snapshot")
    return json.loads(matches[0])


def build_product(
    *, news: dict[str, Any], shared_model: dict[str, Any], page_model: dict[str, Any],
    routes: dict[str, Any], now: datetime, last_publication: Any = None,
) -> RadarProduct | None:
    if now.tzinfo is None:
        raise RadarError("publication time must include timezone")
    generated = _timestamp(news["generated_at"])
    if generated > now or generated.astimezone(PARIS).date() != now.astimezone(PARIS).date():
        raise RadarError("Media snapshot is stale or future dated")
    if news.get("schema_version") != 1 or news.get("window_days") != 30:
        raise RadarError("Radar requires the current 30-day news corpus")
    # The production collector uses --max-items 0. Consume its full array,
    # never feedItems/topPublishers; reject explicit caps and count drift.
    if news.get("max_items", 0) != 0:
        raise RadarError("capped news corpus")
    items = news["election_news"]
    denominator = len(items)
    if news["counts"].get("election_news") != denominator or denominator < 100:
        raise RadarError("insufficient or incomplete election-news corpus")
    health = news["feed_coverage"]
    if (type(health.get("feeds_due_this_run")) is not int or health["feeds_due_this_run"] <= 0
            or health.get("feeds_successful_this_run") != health["feeds_due_this_run"]
            or not news["sources"] or any(row.get("status") != "ok" for row in news["sources"])):
        raise RadarError("required news feeds are unhealthy")
    start = generated - timedelta(days=30)
    ids, urls = set(), set()
    for item in items:
        identifier, url = item.get("id"), item.get("url")
        if (not isinstance(identifier, str) or not identifier.strip() or identifier in ids
                or not isinstance(url, str) or not url.startswith(("https://", "http://")) or url in urls
                or not isinstance(item.get("publisher"), str) or not item["publisher"].strip()
                or item.get("explicit_election") is not True
                or not start <= _timestamp(item.get("published_at")) <= generated):
            raise RadarError("invalid, duplicated or out-of-window source identity")
        ids.add(identifier)
        urls.add(url)
    rows = shared_model["publisherRanking"]
    if (shared_model.get("state") != "ready" or shared_model.get("generatedAt") != news["generated_at"]
            or shared_model.get("windowDays") != 30 or shared_model.get("electionNewsCount") != denominator
            or shared_model.get("acceptedNewsPublisherCount") != len(rows) or len(rows) < 5):
        raise RadarError("invalid shared Media corpus")
    names = set()
    for row in rows:
        label, count, share = row.get("name"), row.get("count"), row.get("rawShare")
        if (not isinstance(label, str) or not label.strip() or label != label.strip() or label in names
                or type(count) is not int or not 0 < count <= denominator
                or type(row.get("denominator")) is not int or row["denominator"] != denominator
                or type(share) not in (int, float) or not math.isfinite(share) or not 0 < share <= 1):
            raise RadarError("invalid shared publisher row")
        names.add(label)
    if sum(row["count"] for row in rows) != denominator:
        raise RadarError("publisher counts do not cover the full denominator")
    if not math.isclose(sum(row["rawShare"] for row in rows), 1.0, rel_tol=0, abs_tol=1e-12):
        raise RadarError("shared publisher shares do not cover the full corpus")
    # Preserve the shared authority's order and raw values. No social sort,
    # publisher regrouping or count/denominator division occurs here.
    for field in ("state", "generatedAt", "windowDays", "electionNewsCount",
                  "acceptedNewsPublisherCount", "publisherRanking", "topPublishers"):
        if page_model.get(field) != shared_model.get(field):
            raise RadarError(f"published Media parity failed: {field}")
    canonical_home(routes)
    selected = tuple(dict(row, display_share=display_round(row["rawShare"] * 100)) for row in rows[:3])
    if len(selected) != 3:
        raise RadarError("fewer than three valid public rows")
    payload = {"family": PRODUCT_TYPE, "rows": [
        {"label": row["name"], "display_tenths": int(round(row["display_share"] * 10))} for row in selected
    ]}
    if not meaningful_change(payload, last_publication):
        return None
    publication_date = generated.astimezone(PARIS).date()
    text = ("RADAR MÉDIAS 📡\n"
            f"{_date_piece(publication_date.isoformat(), 'fr')} · instantané sur 30 j\n\n"
            "Sources les plus représentées :\n"
            + "\n".join(f"{i}. {row['name']} — " + f"{row['display_share']:.1f}".replace(".", ",") + " %"
                for i, row in enumerate(selected, 1))
            + "\n\nCouverture suivie · ≠ opinion.\n" + URL)
    length = weighted_x_length(text)
    if length > 280:
        raise RadarError("Radar exceeds X weighted length")
    digest = fingerprint(payload)
    return RadarProduct(
        f"{PRODUCT_TYPE}:{publication_date.isoformat()}:{digest}:fr", news["generated_at"],
        start.isoformat(), news["generated_at"], denominator, len(rows), selected, payload,
        digest, text, length,
    )


def load_product(*, root: Path, now: datetime, last_publication: Any = None) -> RadarProduct | None:
    news = load_json(root / "news_wire.json")
    # Publisher composition has no dependency on candidate eligibility or the
    # 16:45 product. The shared model supports an unavailable candidate lane.
    shared = media_snapshot_model({"active_field_visibility": None}, news_payload=news)["fr"]["model"]
    return build_product(news=news, shared_model=shared, page_model=published_media(root),
                         routes=load_json(root / "route_registry.json"), now=now,
                         last_publication=last_publication)
