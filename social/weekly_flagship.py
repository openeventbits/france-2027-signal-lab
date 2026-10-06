"""Monday's five fixed signals, resolved from one checked-out Git revision.

Page authorities own the ratios. This product selects three Issue levels and
two signed Agenda movements, never a numerical score across those families.
"""
from __future__ import annotations

import html
import hashlib
import json
import re
import subprocess
from dataclasses import dataclass, replace
from datetime import date, datetime, timedelta, timezone
from pathlib import Path
from typing import Any
from zoneinfo import ZoneInfo

import agenda_page_contract
import issue_page_contract
import coverage_metric_contract as metrics
from social.candidate_media_pulse import weighted_x_length
from social.newsroom_products import _range_piece

PRODUCT_TYPE = "weekly_flagship_fr"
SLOT = "09:30"
URL = "https://france2027.app/"
STATE_KEY = "weekly_flagship_published_weeks"
PARIS = ZoneInfo("Europe/Paris")
HEADLINE = "LA SEMAINE 2027 EN 5 SIGNAUX 📡"

# Readable first; explicit compact aliases are used only if the first copy is
# too long. No ampersand whitespace stripping or URL truncation is performed.
LABELS = {
    "work_purchasing_power_pensions": ("Travail/pouvoir d’achat", "Travail/pouvoir d’achat"),
    "economy_public_finances": ("Économie/finances", "Éco./finances"),
    "europe_defence_foreign_affairs": ("Europe/défense", "Europe/défense"),
    "immigration_identity_secularism": ("Immigration/identité", "Immigration/identité"),
    "security_justice": ("Sécurité/justice", "Sécurité/justice"),
    "health_education_public_services": ("Santé/services publics", "Santé/services"),
    "climate_energy_agriculture": ("Climat/énergie", "Climat/énergie"),
    "institutions_democracy_territories": ("Institutions/démocratie", "Institutions"),
    "rules_calendar": ("Règles/calendrier", "Règles/calendrier"),
    "selection_strategy": ("Primaires/stratégies", "Primaires/strat."),
    "candidacies_endorsements": ("Candidatures/soutiens", "Candid./soutiens"),
    "legal_eligibility": ("Justice/éligibilité", "Justice/éligibilité"),
    "positioning_integrity": ("Positionnement/image", "Positionnement"),
}


class FlagshipError(ValueError):
    pass


@dataclass(frozen=True)
class FlagshipInstruction:
    product_id: str
    slot: str = SLOT
    text: str = ""
    score: None = None


@dataclass(frozen=True)
class FlagshipProduct:
    product_id: str
    issues: metrics.MetricSnapshot
    agenda: metrics.MetricSnapshot
    issue_rows: tuple[metrics.MetricRow, ...]
    increase: metrics.MetricRow
    decrease: metrics.MetricRow
    text: str
    weighted_length: int
    revision: str | None = None


class CatchupCheckoutError(FlagshipError):
    """Authority-verified candidate copy, blocked by the final checkout guard."""
    def __init__(self, product: FlagshipProduct):
        super().__init__("publication checkout changed or contains uncommitted source artifacts")
        self.product = product


def expected_weeks(monday: date) -> tuple[str, str, str, str]:
    if monday.weekday() != 0:
        raise FlagshipError("flagship publication requires Monday in Paris")
    end = monday - timedelta(days=1)
    start = end - timedelta(days=6)
    previous_end = start - timedelta(days=1)
    return ((previous_end - timedelta(days=6)).isoformat(), previous_end.isoformat(),
            start.isoformat(), end.isoformat())


def slot_instruction(monday: date) -> FlagshipInstruction:
    _, _, start, end = expected_weeks(monday)
    return FlagshipInstruction(f"{PRODUCT_TYPE}:{start}:{end}:fr")


def published_weeks(planner: dict[str, Any]) -> dict[str, Any]:
    records = planner.get(STATE_KEY, {})
    if not isinstance(records, dict) or any(
        not isinstance(key, str) or not key.startswith(PRODUCT_TYPE + ":")
        or not isinstance(row, dict) or row.get("product_id") != key
        or not isinstance(row.get("buffer_post_id"), str) or not row["buffer_post_id"].strip()
        or not isinstance(row.get("published_at"), str)
        for key, row in records.items()
    ):
        raise FlagshipError("invalid completed-week publication receipts")
    return records


def publication_receipt(*, product_id: str, revision: str | None,
                        published_at: datetime, buffer_post_id: str) -> dict[str, str]:
    """The common Monday/recovery receipt; call only after Buffer resolution."""
    if (not product_id.startswith(PRODUCT_TYPE + ":") or not revision
            or published_at.tzinfo is None or not isinstance(buffer_post_id, str)
            or not buffer_post_id.strip()):
        raise FlagshipError("flagship publication requires a verified revision and successful Buffer receipt")
    return dict(product_id=product_id, revision=revision,
                published_at=published_at.astimezone(timezone.utc).isoformat().replace("+00:00", "Z"),
                buffer_post_id=buffer_post_id)


def record_receipt(planner: dict[str, Any], receipt: dict[str, str]) -> None:
    published_weeks(planner)
    planner.setdefault(STATE_KEY, {}).setdefault(receipt["product_id"], receipt)


def catchup_monday(now: datetime) -> date:
    """No historical override: only the Monday immediately before Tue/Wed."""
    if now.tzinfo is None:
        raise FlagshipError("catch-up requires an aware execution time")
    today = now.astimezone(PARIS).date()
    if today.weekday() not in (1, 2):
        raise FlagshipError("catch-up executes only Tuesday or Wednesday in Paris")
    return today - timedelta(days=today.weekday())


def _window(snapshot: metrics.MetricSnapshot) -> tuple[str, str, str, str]:
    return (snapshot.previous_start, snapshot.previous_end, snapshot.current_start, snapshot.current_end)


def render(issue_rows: tuple[metrics.MetricRow, ...], increase: metrics.MetricRow,
           decrease: metrics.MetricRow, start: str, end: str) -> str:
    if len(issue_rows) != 3 or len({r.entity_id for r in issue_rows}) != 3:
        raise FlagshipError("flagship requires exactly three distinct Issues and two Agenda rows")
    if increase.entity_id == decrease.entity_id or increase.display_delta < .1 or decrease.display_delta > -.1:
        raise FlagshipError("flagship requires two distinct signed Agenda movements")
    if "polls_race" in (increase.entity_id, decrease.entity_id):
        raise FlagshipError("polls cannot be a public flagship row")
    for compact in (False, True):
        label = lambda row: LABELS[row.entity_id][int(compact)]
        percentage = lambda value: f"{value:.1f}".replace(".", ",")
        # Enjeu ranks distinguish levels from the two signed Agenda changes.
        lines = [HEADLINE, _range_piece(start, end, "fr"), ""]
        lines.extend(f"Enjeu #{i} {label(row)} {percentage(row.current_display)} %"
                     for i, row in enumerate(issue_rows, 1))
        lines.extend([
            f"Agenda ↑ {label(increase)} +{percentage(increase.display_delta)} pp",
            f"Agenda ↓ {label(decrease)} −{percentage(abs(decrease.display_delta))} pp",
            "", "Couverture suivie · ≠ prévision.", URL,
        ])
        text = "\n".join(lines)
        if weighted_x_length(text) <= 280:
            return text
    raise FlagshipError("flagship exceeds X weighted length after approved aliases")


def build_product(*, issue_history: dict[str, Any], agenda_history: dict[str, Any],
                  news: dict[str, Any], candidate_history: dict[str, Any],
                  issue_manifest: dict[str, Any], routes: dict[str, Any],
                  monday: date) -> FlagshipProduct:
    """Pure source/page-authority parity and selection; no publication side effects.

    Historical previews may call this directly. Execution additionally verifies
    freshness, page files and a pinned Git revision through load_product.
    """
    weeks = expected_weeks(monday)
    for history in (issue_history, agenda_history):
        period = history["period"]
        if period.get("day_boundary") != "UTC" or period.get("current_utc_day_excluded") is not True:
            raise FlagshipError("weekly histories must prove complete UTC day boundaries")
    issues = metrics.build_issue_metric_snapshot(issue_history, window_mode=metrics.WINDOW_COMPLETE_WEEK)
    agenda = metrics.build_agenda_metric_snapshot(agenda_history, window_mode=metrics.WINDOW_COMPLETE_WEEK)
    if _window(issues) != weeks or _window(agenda) != weeks:
        raise FlagshipError("Issue and Agenda inputs must match the exact completed calendar weeks")
    if any(row.previous_denominator < 100 or row.current_denominator < 100
           for snapshot in (issues, agenda) for row in snapshot.rows):
        raise FlagshipError("both families require at least 100 source-days in both weeks")

    projection = issue_page_contract.project_issue_pages(
        news, candidate_history, previous_manifest=issue_manifest, coverage_history=issue_history,
    )
    evolution = news["policy_agenda"]["evolution"]
    agenda_evolution = news["campaign_agenda"]["evolution"]
    for start, end, prefix in ((weeks[0], weeks[1], "previous"), (weeks[2], weeks[3], "current")):
        issue_period = issue_page_contract.build_issue_period_metric(
            evolution["topics"], start_date=start, end_date=end,
            daily_denominators=evolution["accepted_daily_activity"],
        )
        agenda_period = agenda_page_contract.build_agenda_period_metric(
            [{"id": topic["id"], "daily": topic["daily_activity"]}
             for topic in agenda_evolution["topics"]], start_date=start, end_date=end,
        )
        for snapshot, period in ((issues, issue_period), (agenda, agenda_period)):
            if len(period.rows) != len(snapshot.rows):
                raise FlagshipError("page/shared row parity failed")
            for shared, row in zip(period.rows, snapshot.rows):
                identifier = getattr(shared, "issue_id", getattr(shared, "topic_id", None))
                if (row.entity_id != identifier
                        or getattr(row, prefix + "_evidence") != shared.numerator
                        or getattr(row, prefix + "_denominator") != shared.denominator
                        or getattr(row, prefix + "_raw") != shared.raw_share * 100.0):
                    raise FlagshipError("page/shared numerator, denominator or raw-share parity failed")

    qualified = {row["issue_id"] for row in projection["issues"]
                 if row["public"] and row["qualification"]["current"]}
    daily = {row["id"]: row["daily"] for row in issue_history["issues"]}
    selected, increase, decrease = select_rows(issues, agenda, qualified, daily)
    matches = [r for r in routes["routes"] if r.get("family") == "core" and r.get("kind") == "home"
               and r.get("entity_id") == "home" and r.get("language") == "fr"]
    if len(matches) != 1 or matches[0].get("canonical_url") != URL or matches[0].get("path") != "/":
        raise FlagshipError("flagship requires the exact canonical FR homepage")
    text = render(selected, increase, decrease, weeks[2], weeks[3])
    return FlagshipProduct(slot_instruction(monday).product_id, issues, agenda, selected,
                           increase, decrease, text, weighted_x_length(text))


def select_rows(issues: metrics.MetricSnapshot, agenda: metrics.MetricSnapshot,
                qualified: set[str], daily: dict[str, list[dict[str, Any]]]):
    """Fixed family roles after authority parity; evidence filters precede ranking."""
    qualified_rows = [row for row in issues.rows if row.entity_id in qualified
                      and row.current_evidence >= 5 and sum(
                          point["publisher_count"] > 0 for point in daily[row.entity_id]
                          if issues.current_start <= point["date"] <= issues.current_end) >= 2]
    selected = tuple(sorted(qualified_rows, key=lambda row: (
        -row.current_display, -row.current_evidence, row.entity_id))[:3])
    if len(selected) != 3:
        raise FlagshipError("fewer than three qualified Issues with five source-days across two dates")
    positive = [row for row in agenda.rows if row.entity_id != "polls_race" and row.display_delta >= .1]
    negative = [row for row in agenda.rows if row.entity_id != "polls_race" and row.display_delta <= -.1]
    if not positive or not negative:
        raise FlagshipError("both positive and negative non-poll Agenda movements are required")
    order = lambda row: (-abs(row.display_delta), -(row.previous_evidence + row.current_evidence), row.entity_id)
    increase, decrease = min(positive, key=order), min(negative, key=order)
    return selected, increase, decrease


def verify_pages(product: FlagshipProduct, news: dict[str, Any], read_text: Any) -> None:
    """Require the checked-in destination cards to match the shared projection.

    Issue page raw deltas intentionally are not copied: social deltas reconcile
    displayed endpoints. Agenda's visible endpoints and source-days are checked.
    """
    expected = _window(product.issues)
    for family in ("policy_agenda", "campaign_agenda"):
        evolution = news[family]["evolution"]
        actual = tuple(evolution[k] for k in ("previous_start", "previous_end", "latest_start", "latest_end"))
        if actual != expected:
            raise FlagshipError("destination comparison dates are not the completed calendar weeks")
    home = read_text("index.html")
    if not re.search(r'<link\s+rel="canonical"\s+href="https://france2027\.app/"', home):
        raise FlagshipError("missing canonical homepage")

    def activity(document: str, family: str, canonical: str):
        if f'<link rel="canonical" href="{canonical}"' not in document:
            raise FlagshipError("missing canonical signal destination")
        points = re.findall(
            rf'<i class="{family}-detail-activity-bar (is-[^\"]+)" data-date="([^\"]+)"', document,
        )
        for kind, start, end in (("is-previous", expected[0], expected[1]),
                                 ("is-latest", expected[2], expected[3])):
            required = [(date.fromisoformat(start) + timedelta(days=i)).isoformat() for i in range(7)]
            if [day for role, day in points if role == kind] != required or required[-1] != end:
                raise FlagshipError("published signal activity dates do not match the exact weeks")
    for row in product.issue_rows:
        path = row.canonical_url_fr.removeprefix(URL) + "index.html"
        document = read_text(path)
        activity(document, "issue", row.canonical_url_fr)
        pairs = re.findall(r'data-previous-incidence="([^"]+)" data-latest-incidence="([^"]+)"', document)
        if (len(pairs) != 1 or tuple(map(float, pairs[0])) != (
                round(row.previous_raw / 100, 6), round(row.current_raw / 100, 6))):
            raise FlagshipError("published Issue page parity failed")
    for row in (product.increase, product.decrease):
        document = html.unescape(read_text(row.canonical_url_fr.removeprefix(URL) + "index.html"))
        activity(document, "agenda", row.canonical_url_fr)
        topic = next(t for t in news["campaign_agenda"]["evolution"]["topics"] if t["id"] == row.entity_id)
        counts = {p["date"]: p["source_day_count"] for p in topic["daily_activity"]
                  if expected[0] <= p["date"] <= expected[3]}
        observed = re.findall(r'<i class="agenda-detail-activity-bar is-[^\"]+" data-date="([^\"]+)" data-source-days="(\d+)"', document)
        if {day: int(count) for day, count in observed if day in counts} != counts:
            raise FlagshipError("published Agenda daily source-day parity failed")
        pairs = re.findall(r'Jours-sources : (\d+) → (\d+).*?Part agenda : ([\d,]+) % → ([\d,]+) %', document, re.S)
        previous, current = (float(f"{raw:.1f}") for raw in (row.previous_raw, row.current_raw))
        if len(pairs) != 1 or (int(pairs[0][0]), int(pairs[0][1]),
                              float(pairs[0][2].replace(",", ".")), float(pairs[0][3].replace(",", "."))) != (
                row.previous_evidence, row.current_evidence, previous, current):
            raise FlagshipError("published Agenda page parity failed")


def load_product(*, root: Path, now: datetime) -> FlagshipProduct:
    if now.tzinfo is None or now.astimezone(PARIS).date().weekday() != 0:
        raise FlagshipError("flagship executes only on an aware Monday in Paris")
    monday = now.astimezone(PARIS).date()
    if now.astimezone(timezone.utc).date() != monday:
        raise FlagshipError("Sunday UTC has not yet closed")
    return _load_revision_product(root=root, now=now, monday=monday, catchup=False)


def load_catchup_product(*, root: Path, now: datetime) -> FlagshipProduct:
    return _load_revision_product(root=root, now=now, monday=catchup_monday(now), catchup=True)


def _page_periods(news: dict[str, Any], window: tuple[str, str, str, str]):
    policy = news["policy_agenda"]["evolution"]
    campaign = news["campaign_agenda"]["evolution"]
    return tuple((
        issue_page_contract.build_issue_period_metric(
            policy["topics"], start_date=start, end_date=end,
            daily_denominators=policy["accepted_daily_activity"]),
        agenda_page_contract.build_agenda_period_metric(
            [{"id": t["id"], "daily": t["daily_activity"]} for t in campaign["topics"]],
            start_date=start, end_date=end),
    ) for start, end in ((window[0], window[1]), (window[2], window[3])))


def verify_catchup_authority(product: FlagshipProduct, news: dict[str, Any], monday: date) -> None:
    """Prove both target calendar weeks, independently of the live card dates.

    build_product constructs history snapshots and binds them to this derived
    Monday. Reconcile every row with the site's page calculations over these
    explicit dates, including the shared displayed endpoints and signed delta.
    """
    target = expected_weeks(monday)
    if (_window(product.issues) != target or _window(product.agenda) != target
            or product.product_id != slot_instruction(monday).product_id):
        raise FlagshipError("catch-up snapshots must match the derived target calendar weeks")
    periods = _page_periods(news, target)
    for index, prefix in enumerate(("previous", "current")):
        for snapshot, period in zip((product.issues, product.agenda), periods[index]):
            if ((period.start_date, period.end_date) != target[index * 2:index * 2 + 2]
                    or period.aggregation_unit != snapshot.aggregation_unit
                    or period.denominator_id != snapshot.denominator_id
                    or len(period.rows) != len(snapshot.rows)):
                raise FlagshipError("catch-up target dates or metric semantics parity failed")
            for row, authority in zip(snapshot.rows, period.rows):
                identity = getattr(authority, "issue_id", getattr(authority, "topic_id", None))
                raw = authority.raw_share * 100.0
                if (row.entity_id != identity
                        or getattr(row, prefix + "_evidence") != authority.numerator
                        or getattr(row, prefix + "_denominator") != authority.denominator
                        or getattr(row, prefix + "_raw") != raw
                        or getattr(row, prefix + "_display") != metrics.display_round(raw)
                        or (row.previous_display, row.current_display, row.display_delta)
                           != metrics.display_triplet(row.previous_raw, row.current_raw)):
                    raise FlagshipError(f"catch-up {snapshot.family} {row.entity_id} {prefix} authority parity failed")


def _live_page_product(product: FlagshipProduct, news: dict[str, Any]) -> FlagshipProduct:
    """A verification-only view of today's cards; never returned for publishing."""
    windows = [tuple(news[family]["evolution"][k] for k in (
        "previous_start", "previous_end", "latest_start", "latest_end"))
        for family in ("policy_agenda", "campaign_agenda")]
    if windows[0] != windows[1]:
        raise FlagshipError("catch-up live page comparison windows are not synchronized")
    window = windows[0]
    previous, current = _page_periods(news, window)

    def snapshot(original: metrics.MetricSnapshot, index: int) -> metrics.MetricSnapshot:
        if len(previous[index].rows) != len(original.rows) or len(current[index].rows) != len(original.rows):
            raise FlagshipError("catch-up live page row parity failed")
        rows = []
        for row, before, after in zip(original.rows, previous[index].rows, current[index].rows):
            if (row.entity_id != getattr(before, "issue_id", getattr(before, "topic_id", None))
                    or row.entity_id != getattr(after, "issue_id", getattr(after, "topic_id", None))):
                raise FlagshipError("catch-up live page entity parity failed")
            raw_before, raw_after = before.raw_share * 100.0, after.raw_share * 100.0
            display_before, display_after, delta = metrics.display_triplet(raw_before, raw_after)
            rows.append(replace(row, previous_raw=raw_before, current_raw=raw_after,
                previous_display=display_before, current_display=display_after, display_delta=delta,
                previous_evidence=before.numerator, current_evidence=after.numerator,
                previous_denominator=before.denominator, current_denominator=after.denominator))
        return replace(original, previous_start=window[0], previous_end=window[1],
                       current_start=window[2], current_end=window[3], rows=tuple(rows))

    issues, agenda = snapshot(product.issues, 0), snapshot(product.agenda, 1)
    issue_rows = {r.entity_id: r for r in issues.rows}
    agenda_rows = {r.entity_id: r for r in agenda.rows}
    return replace(product, issues=issues, agenda=agenda,
        issue_rows=tuple(issue_rows[r.entity_id] for r in product.issue_rows),
        increase=agenda_rows[product.increase.entity_id], decrease=agenda_rows[product.decrease.entity_id])


def _verify_catchup_history_html(product: FlagshipProduct, inputs: dict[str, Any],
                                read_text: Any, now: datetime) -> None:
    """Reconcile exposed historical ledger dates; absent old HTML is permitted.

    Issue HTML exposes topic source-days and article counts, not the source-day
    denominator. Agenda HTML also exposes its daily source-day denominator.
    Never reinterpret the Issue ledger's CORPUS article count as that denominator.
    """
    start, _, _, end = _window(product.issues)
    for family, rows, name, kind in (
            ("issues", product.issue_rows, "issue_coverage_history.json", "issue-history-detail"),
            ("agenda", (product.increase, product.decrease), "agenda_coverage_history.json", "agenda-history-detail")):
        history = inputs[name]
        source_rows = history["issues" if family == "issues" else "topics"]
        for row in rows:
            daily = {p["date"]: p for r in source_rows if r["id"] == row.entity_id for p in r["daily"]}
            # Today's 30-day chart can expose older target dates even outside
            # its two highlighted comparison bands. Check any such data too.
            current = read_text(row.canonical_url_fr.removeprefix(URL) + "index.html")
            chart_family = "issue" if family == "issues" else "agenda"
            seen = set()
            for day, attributes in re.findall(
                    rf'<i class="{chart_family}-detail-activity-bar is-[^\"]+" data-date="([^\"]+)"([^>]*)>', current):
                if not start <= day <= end:
                    continue
                if day in seen or day not in daily:
                    raise FlagshipError("catch-up historical activity dates parity failed")
                seen.add(day)
                pattern = (r'title="[^\"]*· (\d+) articles?"' if family == "issues"
                           else r'data-source-days="(\d+)"')
                counts = re.findall(pattern, attributes)
                field = "item_count" if family == "issues" else "source_day_count"
                if counts and (len(counts) != 1 or int(counts[0]) != daily[day][field]):
                    raise FlagshipError(f"catch-up historical {family} {row.entity_id} {day} activity parity failed")
            routes = [r for r in inputs["route_registry.json"]["routes"] if r.get("family") == family
                      and r.get("kind") == kind and r.get("entity_id") == row.entity_id and r.get("language") == "fr"]
            if not routes:
                continue
            if len(routes) != 1:
                raise FlagshipError("catch-up historical route is ambiguous")
            route = routes[0]
            document = _verify_catchup_route(route["canonical_url"], inputs["route_registry.json"], read_text, now)
            observed = set()
            for table in re.findall(r'<table class="(?:issue|agenda)-history-table"[^>]*>(.*?)</table>', document, re.S):
                for record in re.findall(r'<tr>(.*?)</tr>', table, re.S):
                    dates = re.findall(r'<time datetime="([^\"]+)"', record)
                    if not dates or not start <= dates[0] <= end:
                        continue
                    day = dates[0]
                    if len(dates) != 1 or day in observed or day not in daily:
                        raise FlagshipError("catch-up historical HTML dates parity failed")
                    observed.add(day)
                    cells = dict(re.findall(r'<td data-label="([^\"]+)">\s*([^<]*?)\s*</td>', record))
                    point = daily[day]
                    expected = ({"ARTICLES": point["item_count"], "MÉDIAS": point["publisher_count"],
                                 "CORPUS": point["corpus_item_count"]} if family == "issues" else
                                {"ARTICLES": point["item_count"], "JOURS-SOURCES": point["source_day_count"],
                                 "TOTAL ARTICLES": point["total_classified_agenda_items"],
                                 "TOTAL JOURS-SOURCES": point["total_agenda_topic_source_days"]})
                    if any(cells.get(key) != str(value) for key, value in expected.items()):
                        raise FlagshipError(f"catch-up historical {family} {row.entity_id} {day} HTML parity failed")
                    share = (point["corpus_share_percent"] if family == "issues"
                             else point["topic_source_day_share"] * 100.0)
                    try:
                        displayed = float(cells["PART"].removesuffix("%").replace(",", "."))
                    except (KeyError, ValueError) as error:
                        raise FlagshipError("catch-up historical HTML displayed share is invalid") from error
                    if displayed != float(f"{share:.2f}"):
                        raise FlagshipError(f"catch-up historical {family} {row.entity_id} {day} displayed share parity failed")


def verify_catchup_product(product: FlagshipProduct, inputs: dict[str, Any],
                           monday: date, read_text: Any, now: datetime) -> None:
    verify_catchup_authority(product, inputs["news_wire.json"], monday)
    # Keep today's cards reconciled to today's producer. Their rolling window
    # is allowed to advance; the target product above remains fixed to Monday.
    verify_pages(_live_page_product(product, inputs["news_wire.json"]), inputs["news_wire.json"], read_text)
    _verify_catchup_routes(product, inputs["route_registry.json"], read_text, now)
    _verify_catchup_history_html(product, inputs, read_text, now)


def _validate_catchup_artifacts(inputs: dict[str, Any], now: datetime) -> None:
    """Require today's synchronized refresh and histories through yesterday UTC.

    Target weeks use the unchanged history/page authorities. Live comparison
    cards reconcile separately to their current producer window.
    """
    news = inputs["news_wire.json"]
    today = now.astimezone(timezone.utc).date()
    stamps = [news["generated_at"], inputs["issue_coverage_history.json"]["data_as_of"],
              inputs["agenda_coverage_history.json"]["data_as_of"]]
    generated = [datetime.fromisoformat(t.replace("Z", "+00:00")) for t in stamps]
    if (any(t.tzinfo is None or t > now or t.astimezone(timezone.utc).date() != today
            for t in generated) or len(set(generated)) != 1):
        raise FlagshipError("catch-up source artifacts are stale, future or from different refreshes")
    yesterday = (today - timedelta(days=1)).isoformat()
    if any(inputs[name]["period"]["end_date"] != yesterday for name in (
            "issue_coverage_history.json", "agenda_coverage_history.json")):
        raise FlagshipError("catch-up histories must end on the latest complete UTC day")
    if (inputs["candidate_agenda_history.json"]["tracking"]["data_as_of"] != today.isoformat()
            or inputs["issue_pages_manifest.json"]["data_as_of"] != today.isoformat()):
        raise FlagshipError("catch-up candidate history and Issue manifest must match the refresh date")
    # A fresh producer may retain Monday's weekly page view while extending
    # the complete-day histories. Do not confuse its analytical cutoff with
    # the artifact refresh clock. Both page families must share that cutoff;
    # historical target authority and current visible-page parity follow below.
    cutoffs = [news[family]["evolution"]["period_end"]
               for family in ("policy_agenda", "campaign_agenda")]
    if (len(set(cutoffs)) != 1
            or not catchup_monday(now).isoformat() <= cutoffs[0] <= today.isoformat()):
        raise FlagshipError("catch-up page source cutoffs must be synchronized within the recovery interval")


def _verify_catchup_routes(product: FlagshipProduct, routes: dict[str, Any],
                           read_text: Any, now: datetime) -> None:
    """Bind every destination to the same generated route-registry blobs."""
    urls = [URL, *(r.canonical_url_fr for r in product.issue_rows),
            product.increase.canonical_url_fr, product.decrease.canonical_url_fr]
    for url in urls:
        _verify_catchup_route(url, routes, read_text, now)


def _verify_catchup_route(url: str, routes: dict[str, Any], read_text: Any, now: datetime) -> str:
    from build_route_registry import _semantic_html_bytes
    matches = [r for r in routes["routes"] if r.get("canonical_url") == url and r.get("language") == "fr"]
    if not url.startswith(URL):
        raise FlagshipError("catch-up route must use the canonical FR27 origin")
    path = url.removeprefix(URL) + "index.html"
    if (len(matches) != 1 or matches[0].get("source_file") != path
            or matches[0].get("lastmod") != now.astimezone(timezone.utc).date().isoformat()):
        raise FlagshipError(f"catch-up route/page refresh or content parity failed: {path}")
    document = read_text(path)
    if (matches[0].get("content_sha256") != hashlib.sha256(_semantic_html_bytes(document.encode("utf-8"))).hexdigest()
            or f'<link rel="canonical" href="{url}"' not in document):
        raise FlagshipError(f"catch-up route/page refresh or content parity failed: {path}")
    return document


def _load_revision_product(*, root: Path, now: datetime, monday: date,
                            catchup: bool) -> FlagshipProduct:

    def git(*args: str) -> str:
        try:
            return subprocess.check_output(["git", *args], cwd=root, encoding="utf-8", stderr=subprocess.PIPE)
        except (OSError, subprocess.CalledProcessError) as error:
            raise FlagshipError("cannot verify the checked-out publication revision") from error

    revision = git("rev-parse", "HEAD").strip()
    paths = ["issue_page_contract.py", "agenda_page_contract.py", "coverage_metric_contract.py",
             "candidate_agenda_history_contract.py", "fetch_news_wire.py",
             "social/weekly_flagship.py", "social/newsroom_products.py",
             "social/candidate_media_pulse.py", "social/daily_plan.py", "social/daily_queue.py",
             "social/queue_metadata.py"]
    if catchup:
        paths.extend(["social/weekly_flagship_catchup.py", "social/social_publish.py", "build_route_registry.py"])

    def read_text(path: str) -> str:
        paths.append(path)
        return git("show", f"{revision}:{path}")

    inputs = {name: json.loads(read_text(name)) for name in (
        "news_wire.json", "issue_coverage_history.json", "agenda_coverage_history.json",
        "candidate_agenda_history.json", "issue_pages_manifest.json", "route_registry.json",
    )}
    news = inputs["news_wire.json"]
    if catchup:
        _validate_catchup_artifacts(inputs, now)
    else:
        _validate_monday_artifacts(inputs, now, monday)
    result = build_product(issue_history=inputs["issue_coverage_history.json"],
        agenda_history=inputs["agenda_coverage_history.json"], news=news,
        candidate_history=inputs["candidate_agenda_history.json"],
        issue_manifest=inputs["issue_pages_manifest.json"], routes=inputs["route_registry.json"], monday=monday)
    if catchup:
        verify_catchup_product(result, inputs, monday, read_text, now)
    else:
        verify_pages(result, news, read_text)
    # Blobs above all come from one SHA. Reject a checkout change or uncommitted
    # artifact refresh rather than silently publish an older committed snapshot.
    if (git("rev-parse", "HEAD").strip() != revision
            or git("diff", "--name-only", "HEAD", "--", *paths).strip()
            or (catchup and git("ls-files", "--others", "--exclude-standard", "--", *paths).strip())):
        if catchup:
            raise CatchupCheckoutError(replace(result, revision=revision))
        raise FlagshipError("publication checkout changed or contains uncommitted source artifacts")
    return replace(result, revision=revision)


def _validate_monday_artifacts(inputs: dict[str, Any], now: datetime, monday: date) -> None:
    news = inputs["news_wire.json"]
    timestamps = [news["generated_at"], inputs["issue_coverage_history.json"]["data_as_of"],
                  inputs["agenda_coverage_history.json"]["data_as_of"]]
    generated = [datetime.fromisoformat(t.replace("Z", "+00:00")) for t in timestamps]
    if any(t.tzinfo is None or t > now or t.astimezone(timezone.utc).date() != monday for t in generated) or len(set(generated)) != 1:
        raise FlagshipError("weekly source artifacts are stale, future or from different refreshes")
    sunday = (monday - timedelta(days=1)).isoformat()
    if any(inputs[name]["period"]["end_date"] != sunday for name in (
            "issue_coverage_history.json", "agenda_coverage_history.json")):
        raise FlagshipError("Monday source histories must end on the latest complete UTC Sunday")
