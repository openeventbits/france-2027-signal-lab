"""Conservative identities for source-confirmed campaign-launch occurrences.

Occurrences are reviewed facts, not article membership lists. Unknown, ambiguous,
future, unlocated and compound reports never receive a broad grouping identity.
"""
from __future__ import annotations

import json
import re
from datetime import date, datetime, timedelta, timezone
from pathlib import Path
from zoneinfo import ZoneInfo

from fetch_news_wire import normalize

OCCURRENCES_PATH = Path(__file__).with_name("campaign_event_occurrences.json")
LAUNCH = re.compile(
    r"\b(?:lance\s+sa\s+campagne(?:\s+presidentielle)?|"
    r"se\s+lance\s+dans\s+la\s+course\s+a\s+l\s+elysee|"
    r"a\s+lance\s+sa\s+campagne(?:\s+presidentielle)?)\b"
)
SEPARATE_ACTION = re.compile(
    r"\b(?:reorganise|remanie|nomme|designe|investit|renonce|se\s+retire|"
    r"vise\s+matignon|devoile|annonce\s+(?:un|une|son|sa)|"
    r"soutient|se\s+rallie|porte\s+plainte|depose\s+plainte|"
    r"comite\s+de\s+soutien|reelection|reelu|primaire|"
    r"est\s+(?:investi[e]?|designe[e]?)|"
    r"(?:nouveau|deuxieme|second|autre)\s+meeting)\b"
)
ROUNDUP = re.compile(r"\b(?:le\s+point\s+sur|la\s+semaine|tour\s+d\s+horizon|revue\s+de)\b")
FUTURE = re.compile(r"\b(?:demain|tiendra|lancera|doit\s+(?:prononcer|lancer)|va\s+lancer)\b")
MONTHS = {"janvier": 1, "fevrier": 2, "mars": 3, "avril": 4, "mai": 5,
          "juin": 6, "juillet": 7, "aout": 8, "septembre": 9,
          "octobre": 10, "novembre": 11, "decembre": 12}
PREVIEW_SUMMARY = "Advance campaign-launch coverage; not a completed-event report."


def headline_places(headline):
    return {
        normalize(match.group(1)) for match in re.finditer(
            r"(?i:\b(?:à|a|depuis))\s+([A-ZÀ-ÖØ-Ý][a-zà-öø-ÿ]+(?:-[A-ZÀ-ÖØ-Ý]?[a-zà-öø-ÿ]+)*)",
            headline,
        )
    }


def launch_preview(item, occurrences):
    """Label short advance coverage, without making it an occurred event.

    An unlocated advance headline remains a separate source claim, never a
    member of the occurrence group. Compound/roundup claims are not relabeled.
    """
    headline = str(item.get("headline") or "")
    text = normalize(headline)
    names, ids = item.get("candidate_names", []), item.get("candidate_ids", [])
    published = instant(item.get("published_at"))
    if (not launch_report(item) or not published or len(ids) != 1 or len(names) != 1
            or f" {normalize(names[0])} " not in f" {text} " or ROUNDUP.search(text) or SEPARATE_ACTION.search(text)):
        return False
    places = headline_places(headline)
    matches = [r for r in occurrences if ids[0] == r["actor_id"]
               and normalize(names[0]) == normalize(r["actor_name"])
               and (not places or places == {normalize(r["place"])})
               and instant(r["scheduled_start_at"]) - timedelta(hours=48) <= published < instant(r["scheduled_start_at"])]
    return len(matches) == 1


def instant(value):
    try:
        parsed = datetime.fromisoformat(str(value).replace("Z", "+00:00"))
        return parsed.astimezone(timezone.utc) if parsed.tzinfo else None
    except ValueError:
        return None


def validate_occurrences(payload):
    if (not isinstance(payload, dict) or set(payload) != {"schema_version", "occurrences"}
            or type(payload["schema_version"]) is not int or payload["schema_version"] != 1
            or not isinstance(payload["occurrences"], list)):
        raise ValueError("invalid campaign occurrence registry")
    seen = set()
    for row in payload["occurrences"]:
        if not isinstance(row, dict) or set(row) != {"actor_id", "actor_name", "action", "place", "event_date", "scheduled_start_at", "evidence_urls"}:
            raise ValueError("invalid campaign occurrence fields")
        start = instant(row["scheduled_start_at"])
        try:
            day = date.fromisoformat(row["event_date"])
        except (TypeError, ValueError):
            raise ValueError("invalid campaign occurrence date") from None
        key = (row["actor_id"], row["action"], row["place"], row["event_date"])
        if (key in seen or row["action"] != "campaign_launch" or not start
                or start.astimezone(ZoneInfo("Europe/Paris")).date() != day
                or not all(isinstance(row[k], str) and row[k].strip() for k in ("actor_id", "actor_name", "place"))
                or not isinstance(row["evidence_urls"], list) or not row["evidence_urls"]
                or not all(isinstance(url, str) and url.startswith("https://") for url in row["evidence_urls"])):
            raise ValueError("invalid or duplicate campaign occurrence")
        seen.add(key)
    return payload["occurrences"]


def load_occurrences():
    return validate_occurrences(json.loads(OCCURRENCES_PATH.read_text(encoding="utf-8")))


def launch_identity(item, occurrences):
    """Return (actor, action, place, occurrence date), never a fuzzy story key.

    Publication time only bounds eligibility relative to an independently
    confirmed occurrence; it never supplies the occurrence date. The 48-hour
    reporting window permits midnight and next-day coverage, not an open-ended
    transitive extension. All members must independently establish this key.
    """
    headline = str(item.get("headline") or "")
    text = normalize(headline)
    if item.get("category") != "campaign" or not LAUNCH.search(text):
        return None
    if ROUNDUP.search(text) or SEPARATE_ACTION.search(text) or FUTURE.search(text):
        return None
    names, ids = item.get("candidate_names", []), item.get("candidate_ids", [])
    # A broad/summary-only candidate association is not evidence of a sole actor.
    if len(names) != 1 or len(ids) != 1 or f" {normalize(names[0])} " not in f" {text} ":
        return None
    # Explicit, grammatically located places only. A reference to another city
    # after the action cannot silently override the actual launch's location.
    places = headline_places(headline)
    published = instant(item.get("published_at"))
    if not published:
        return None
    matches = []
    for row in occurrences:
        if ids[0] != row["actor_id"] or normalize(names[0]) != normalize(row["actor_name"]):
            continue
        if places != {normalize(row["place"])}:
            continue
        start = instant(row["scheduled_start_at"])
        if not start <= published <= start + timedelta(hours=48):
            continue
        # Explicit occurrence dates must agree, including a different launch
        # by the same actor in the same city inside the reporting window.
        explicit_dates = set(re.findall(r"\b20\d{2}-\d{2}-\d{2}\b", headline))
        for day, month, year in re.findall(
            r"\b(\d{1,2})\s+(" + "|".join(MONTHS) + r")(?:\s+(20\d{2}))?\b", text
        ):
            explicit_dates.add(f"{year or row['event_date'][:4]}-{MONTHS[month]:02d}-{int(day):02d}")
        if explicit_dates and explicit_dates != {row["event_date"]}:
            continue
        supplied_date = item.get("event_date")
        if supplied_date and supplied_date != row["event_date"]:
            continue
        occurrence_day = date.fromisoformat(row["event_date"])
        weekdays = ("lundi", "mardi", "mercredi", "jeudi", "vendredi", "samedi", "dimanche")
        if any(re.search(rf"\b{word}\b", text) and index != occurrence_day.weekday()
               for index, word in enumerate(weekdays)):
            continue
        if "hier" in text.split() and published.astimezone(ZoneInfo("Europe/Paris")).date() - timedelta(days=1) != occurrence_day:
            continue
        matches.append((row["actor_id"], row["action"], normalize(row["place"]), row["event_date"]))
    return matches[0] if len(matches) == 1 else None


def launch_report(item):
    headline = str(item.get("headline") or "")
    text = normalize(headline)
    return (item.get("category") == "campaign" and bool(LAUNCH.search(text))
            and ("lance sa campagne" in text or bool(headline_places(headline))
                 or bool(re.search(r"\b(?:meeting|congres)\b", text))))
