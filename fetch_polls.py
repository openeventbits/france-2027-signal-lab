"""Fetch and normalize first-round France 2027 presidential polls."""

from __future__ import annotations

import argparse
import copy
import hashlib
import io
import json
import math
import os
import re
import tempfile
from datetime import datetime, timezone
from functools import lru_cache
from pathlib import Path
from typing import Any
from urllib.parse import urlencode, urljoin, urlparse
from urllib.request import Request, urlopen

import pandas as pd
from lxml import html as lxml_html
from pypdf import PdfReader

from commission_notice_discovery import (
    CommissionNoticeError,
    atomic_write_registry,
    discover_registry,
    fetch_official_url,
    load_registry,
    registry_event_notices,
)
from commission_notice_coverage import reconcile_commission_notices
from poll_contract import (
    FIRST_ROUND,
    PollContractError,
    apply_completeness_contract,
    make_event_id,
    make_scenario_key,
    normalize_identity,
    validate_poll_events,
)


SOURCE_URL = (
    "https://en.wikipedia.org/wiki/"
    "Opinion_polling_for_the_2027_French_presidential_election"
)
USER_AGENT = "France2027SignalLab/1.0 (contact: malatazen@gmail.com)"
MEDIAWIKI_API_URL = "https://en.wikipedia.org/w/api.php"
SOURCE_PAGE = "Opinion_polling_for_the_2027_French_presidential_election"
WIKIPEDIA_LICENSE = "CC BY-SA 4.0"
WIKIPEDIA_SOURCES = ("english", "french")
FRENCH_SOURCE_URL = (
    "https://fr.wikipedia.org/wiki/"
    "Liste_de_sondages_sur_l%27%C3%A9lection_pr%C3%A9sidentielle_"
    "fran%C3%A7aise_de_2027"
)
ROUND = FIRST_ROUND
SECOND_ROUND = "second_round"
DEFAULT_POLL_WAVE_OVERRIDES = Path(__file__).with_name(
    "poll_wave_overrides.json"
)
DASHES = {"", "-", "–", "—", "−", "nan", "none"}
# Reviewed source spellings support normalization and bounded adapters only.
# This catalog is not a candidate-membership allowlist: clean unknown names pass
# through every general poll contract and remain source evidence.
REVIEWED_CANDIDATE_SPELLINGS = (
    "Bernard Cazeneuve",
    "Bruno Le Maire",
    "Bruno Retailleau",
    "Carole Delga",
    "David Lisnard",
    "Dominique de Villepin",
    "Édouard Philippe",
    "Élisabeth Borne",
    "Éric Zemmour",
    "Fabien Roussel",
    "François Bayrou",
    "François Hollande",
    "François Ruffin",
    "Gabriel Attal",
    "Gérald Darmanin",
    "Jean Castex",
    "Jean Lassalle",
    "Jean-Luc Mélenchon",
    "Jordan Bardella",
    "Laurent Wauquiez",
    "Marine Le Pen",
    "Marine Tondelier",
    "Michel Barnier",
    "Nathalie Arthaud",
    "Nicolas Dupont-Aignan",
    "Olivier Faure",
    "Philippe Poutou",
    "Raphaël Glucksmann",
    "Sandrine Rousseau",
    "Sarah Knafo",
    "Sébastien Lecornu",
    "Xavier Bertrand",
    "Yaël Braun-Pivet",
    "Yannick Jadot",
)


def cell_text(cell: object) -> str:
    """Return the visible text from a pandas read_html cell."""
    value = cell[0] if isinstance(cell, tuple) else cell
    if value is None or pd.isna(value):
        return ""
    return re.sub(r"\s+", " ", str(value)).strip()


def cell_link(cell: object) -> str | None:
    """Return the hyperlink preserved by extract_links='body'."""
    if isinstance(cell, tuple) and len(cell) > 1 and cell[1]:
        return str(cell[1])
    return None


normalize = normalize_identity


CANDIDATE_NORMALIZATION_ALIASES = {
    normalize(name): name for name in REVIEWED_CANDIDATE_SPELLINGS
}
CANDIDATE_NORMALIZATION_ALIASES.update(
    {
        normalize("Edouard Philippe"): "Édouard Philippe",
        normalize("Eric Zemmour"): "Éric Zemmour",
        normalize("Dominique de VILLEPIN"): "Dominique de Villepin",
        normalize("Nicolas Dupont Aignan"): "Nicolas Dupont-Aignan",
        normalize("Glucksmann"): "Raphaël Glucksmann",
        # Elabe's embedded font maps these accented letters to U+FFFD.
        normalize("Jean-Luc M�LENCHON"): "Jean-Luc Mélenchon",
        normalize("Rapha�l GLUCKSMANN"): "Raphaël Glucksmann",
        normalize("�douard PHILIPPE"): "Édouard Philippe",
        normalize("�ric ZEMMOUR"): "Éric Zemmour",
        normalize("Fran�ois HOLLANDE"): "François Hollande",
        normalize("Fran�ois RUFFIN"): "François Ruffin",
        normalize("G�rald DARMANIN"): "Gérald Darmanin",
        normalize("S�bastien LECORNU"): "Sébastien Lecornu",
    }
)

RUNOFF_HEADING_CANDIDATE_ALIASES = {
    normalize("Attal"): "Gabriel Attal",
    normalize("Bardella"): "Jordan Bardella",
    normalize("Glucksmann"): "Raphaël Glucksmann",
    normalize("Mélenchon"): "Jean-Luc Mélenchon",
    normalize("Le Pen"): "Marine Le Pen",
    normalize("Philippe"): "Édouard Philippe",
    normalize("Retailleau"): "Bruno Retailleau",
    normalize("Ruffin"): "François Ruffin",
}


def canonical_candidate_name(value: str, *, strict: bool = False) -> str:
    """Normalize reviewed aliases while preserving clean source-reported names.

    ``strict`` protects source adapters from blank or visibly corrupted unknown
    text. It does not turn the reviewed alias catalog into a membership list.
    """

    name = re.sub(r"\s+", " ", value).strip()
    canonical = CANDIDATE_NORMALIZATION_ALIASES.get(normalize(name))
    if canonical:
        return canonical
    if strict and (not name or "�" in name):
        raise ValueError(f"invalid source candidate name: {value!r}")
    return name


CANONICAL_POLLSTERS = (
    "Cluster17",
    "Elabe",
    "Harris Interactive",
    "Ifop",
    "Ifop/Hexagone",
    "Ipsos",
    "Odoxa",
    "OpinionWay",
    "Verian",
)
POLLSTER_ALIASES = {
    normalize(name): name for name in CANONICAL_POLLSTERS
}
POLLSTER_ALIASES.update(
    {
        normalize("Harris Interactive / Toluna"): "Harris Interactive",
        normalize("Harris Interactive-Toluna"): "Harris Interactive",
        normalize("Ifop / Hexagone"): "Ifop/Hexagone",
        normalize("Opinion Way"): "OpinionWay",
    }
)


def canonical_pollster_name(value: str) -> str:
    """Return a stable known pollster label while preserving unknown firms."""
    name = re.sub(r"\s+", " ", value).strip()
    return POLLSTER_ALIASES.get(normalize(name), name)


def parse_date(value: str) -> datetime:
    return datetime.strptime(value.strip(), "%d %b %Y")


def parse_fieldwork(value: str) -> tuple[str, str]:
    """Parse the date formats currently used by the Wikipedia tables."""
    value = value.replace("—", "–").replace("−", "–")
    value = re.sub(r"\s+", " ", value).strip()

    if "–" not in value:
        date = parse_date(value)
        iso = date.date().isoformat()
        return iso, iso

    left, right = [part.strip() for part in value.split("–", 1)]
    end = parse_date(right)

    if re.fullmatch(r"\d{1,2}", left):
        start = end.replace(day=int(left))
    else:
        start = parse_date(f"{left} {end.year}")

    return start.date().isoformat(), end.date().isoformat()


def parse_sample_size(value: str) -> int | None:
    digits = re.sub(r"[,\s]", "", value)
    return int(digits) if digits.isdigit() else None


def parse_score(value: str) -> float | None:
    value = re.sub(r"\[[^\]]*]", "", value)
    value = value.replace(",", ".").replace("%", "").strip()

    if value.casefold() in DASHES:
        return None

    if value.startswith("<") or not re.fullmatch(r"\d+(?:\.\d+)?", value):
        raise ValueError(f"ambiguous score: {value}")

    return float(value)


def candidate_name(value: object) -> str:
    name = str(value).strip()
    name = re.sub(r"\s*\([^)]*\)\s*$", "", name)
    return re.sub(r"\s+", " ", name).strip()


PollWaveKey = tuple[str, str, str, int | None]
PollWaveOverrides = dict[PollWaveKey, dict[str, Any]]


def _override_wave_key(record: dict[str, Any], context: str) -> PollWaveKey:
    pollster = record.get("pollster")
    start = record.get("fieldwork_start")
    end = record.get("fieldwork_end")
    sample_size = record.get("sample_size")
    if not isinstance(pollster, str) or not pollster.strip():
        raise ValueError(f"{context}.pollster must be a non-empty string")
    for field, value in (("fieldwork_start", start), ("fieldwork_end", end)):
        if not isinstance(value, str) or not re.fullmatch(r"\d{4}-\d{2}-\d{2}", value):
            raise ValueError(f"{context}.{field} must use YYYY-MM-DD")
        try:
            parsed = datetime.strptime(value, "%Y-%m-%d")
        except ValueError as error:
            raise ValueError(f"{context}.{field} must be a valid date") from error
        if parsed.strftime("%Y-%m-%d") != value:
            raise ValueError(f"{context}.{field} must use YYYY-MM-DD")
    if start > end:
        raise ValueError(f"{context} fieldwork_start must not exceed fieldwork_end")
    if sample_size is not None and (
        not isinstance(sample_size, int)
        or isinstance(sample_size, bool)
        or sample_size <= 0
    ):
        raise ValueError(f"{context}.sample_size must be a positive integer or null")
    return normalize(pollster), start, end, sample_size


@lru_cache(maxsize=None)
def load_poll_wave_overrides(
    path: Path | str = DEFAULT_POLL_WAVE_OVERRIDES,
) -> PollWaveOverrides:
    """Load the small reviewed wave-level intervention registry."""
    source = Path(path)
    try:
        payload = json.loads(source.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as error:
        raise ValueError(f"cannot load poll wave overrides {source}: {error}") from error
    if not isinstance(payload, dict) or payload.get("schema_version") != "1.0":
        raise ValueError("poll wave overrides schema_version must equal 1.0")
    records = payload.get("waves")
    if not isinstance(records, list):
        raise ValueError("poll wave overrides waves must be a list")

    overrides: PollWaveOverrides = {}
    allowed_fields = {
        "pollster",
        "fieldwork_start",
        "fieldwork_end",
        "sample_size",
        "status",
        "official_source_url",
        "reporting_source_url",
        "corrections",
        "reason",
    }
    for index, record in enumerate(records):
        context = f"poll wave overrides waves[{index}]"
        if not isinstance(record, dict):
            raise ValueError(f"{context} must be an object")
        unexpected = set(record) - allowed_fields
        if unexpected:
            raise ValueError(f"{context} has unexpected fields: {sorted(unexpected)}")
        key = _override_wave_key(record, context)
        if key in overrides:
            raise ValueError(f"duplicate poll wave override identity: {key}")
        reason = record.get("reason")
        if not isinstance(reason, str) or not reason.strip():
            raise ValueError(f"{context}.reason must be a non-empty string")
        status = record.get("status")
        if status not in (None, "rejected"):
            raise ValueError(f"{context}.status must equal rejected when present")
        official_url = record.get("official_source_url")
        reporting_url = record.get("reporting_source_url")
        for field, value in (
            ("official_source_url", official_url),
            ("reporting_source_url", reporting_url),
        ):
            if value is not None and (
                not isinstance(value, str) or not valid_http_url(value)
            ):
                raise ValueError(f"{context}.{field} must be an HTTP(S) URL")
        corrections = record.get("corrections")
        if corrections is not None:
            if not isinstance(corrections, dict) or set(corrections) != {
                "fieldwork_start",
                "fieldwork_end",
            }:
                raise ValueError(
                    f"{context}.corrections must contain only both fieldwork dates"
                )
            corrected_record = {**record, **corrections}
            _override_wave_key(corrected_record, f"{context}.corrections")
        interventions = sum(
            value is not None
            for value in (status, official_url, corrections)
        )
        if interventions != 1:
            raise ValueError(f"{context} must define exactly one intervention")
        if reporting_url is not None and corrections is None:
            raise ValueError(
                f"{context}.reporting_source_url is only valid for corrections"
            )
        overrides[key] = record
    return overrides


def _reviewed_overrides(
    overrides: PollWaveOverrides | None,
) -> PollWaveOverrides:
    return load_poll_wave_overrides() if overrides is None else overrides


def apply_official_poll_metadata_correction(
    pollster: str,
    fieldwork_start: str,
    fieldwork_end: str,
    sample_size: int | None,
    source_url: str,
    overrides: PollWaveOverrides | None = None,
) -> tuple[str, str]:
    """Correct reviewed source metadata before deterministic event identity."""
    key: PollWaveKey = (
        normalize(pollster),
        fieldwork_start,
        fieldwork_end,
        sample_size,
    )
    reviewed = _reviewed_overrides(overrides).get(key)
    if reviewed is None or "corrections" not in reviewed:
        return fieldwork_start, fieldwork_end
    reporting_url = reviewed.get("reporting_source_url")
    if reporting_url is not None and reporting_url != source_url.strip():
        return fieldwork_start, fieldwork_end
    corrections = reviewed["corrections"]
    return corrections["fieldwork_start"], corrections["fieldwork_end"]


def official_poll_source_key(
    event: dict,
) -> PollWaveKey:
    return (
        normalize(str(event.get("pollster", ""))),
        str(event.get("fieldwork_start", "")),
        str(event.get("fieldwork_end", "")),
        event.get("sample_size"),
    )


def apply_official_poll_sources(
    events: list[dict],
    overrides: PollWaveOverrides | None = None,
) -> int:
    enriched_waves: set[PollWaveKey] = set()
    reviewed = _reviewed_overrides(overrides)

    for event in events:
        key = official_poll_source_key(event)
        entry = reviewed.get(key, {})
        official_url = entry.get("official_source_url")

        if official_url is None:
            existing = str(
                event.get("official_source_url", "")
            ).strip()

            if existing and not valid_http_url(existing):
                raise ValueError(
                    "invalid existing official_source_url: "
                    f"{existing!r}"
                )

            continue

        if not valid_http_url(official_url):
            raise ValueError(
                "invalid configured official poll source: "
                f"{official_url!r}"
            )

        event["official_source_url"] = official_url
        enriched_waves.add(key)

    return len(enriched_waves)


def logical_key(event: dict) -> tuple[str, str, str, str]:
    return (
        normalize(event["pollster"]),
        event["fieldwork_start"],
        event["fieldwork_end"],
        event["scenario_key"],
    )


def poll_wave_key(event: dict) -> PollWaveKey:
    return (
        normalize(event["pollster"]),
        event["fieldwork_start"],
        event["fieldwork_end"],
        event.get("sample_size"),
    )


def rejected_poll_wave_keys(
    events: list[dict],
    overrides: PollWaveOverrides | None = None,
) -> set[PollWaveKey]:
    reviewed = _reviewed_overrides(overrides)
    return {
        poll_wave_key(event)
        for event in events
        if reviewed.get(poll_wave_key(event), {}).get("status") == "rejected"
    }


def filter_rejected_poll_waves(
    events: list[dict],
    overrides: PollWaveOverrides | None = None,
) -> tuple[list[dict], int, int]:
    """Remove explicitly rejected wave identities from any publication input."""
    rejected = rejected_poll_wave_keys(events, overrides)
    retained = [event for event in events if poll_wave_key(event) not in rejected]
    return retained, len(events) - len(retained), len(rejected)


def validate_reporting_source_wave_anomalies(events: list[dict]) -> int:
    """Fail closed on exact same-sample source reuse across fieldwork windows."""
    grouped: dict[tuple[str, int, str], set[PollWaveKey]] = {}
    for event in events:
        sample_size = event.get("sample_size")
        source_url = str(event.get("source_url", "")).strip()
        if (
            not isinstance(sample_size, int)
            or isinstance(sample_size, bool)
            or source_url == SOURCE_URL
        ):
            continue
        key = (normalize(str(event.get("pollster", ""))), sample_size, source_url)
        grouped.setdefault(key, set()).add(poll_wave_key(event))
    conflicts = [
        (key, sorted(waves))
        for key, waves in grouped.items()
        if len(waves) > 1
    ]
    if conflicts:
        key, waves = conflicts[0]
        raise ValueError(
            "poll wave anomaly requires reviewed override: same pollster, sample "
            f"and reporting source span different fieldwork identities: {key} -> {waves}"
        )
    return 0


POLLSTER_HEADERS = {
    "polling firm",
    "polling firm client",
    "pollster",
}
FIELDWORK_HEADERS = {
    "date s conducted",
    "date conducted",
    "dates conducted",
    "fieldwork",
    "fieldwork date",
    "fieldwork dates",
}
SAMPLE_HEADERS = {
    "sample",
    "sample size",
}
EXCLUDED_ROUND_CONTEXT = {
    "second round",
    "runoff",
    "head to head",
    "head-to-head",
}


def column_header_text(column: object) -> str:
    values = column if isinstance(column, tuple) else (column,)
    for value in values:
        text = cell_text(value)
        if text and not text.startswith("Unnamed:"):
            # pandas disambiguates duplicate HTML headers with ".1", ".2", …
            # suffixes; remove only that parser-added suffix for validation.
            return re.sub(r"\.\d+$", "", text)
    return ""


def table_column_contract(
    frame: pd.DataFrame,
) -> tuple[dict[str, int], list[tuple[int, str]]] | None:
    """Return semantic metadata and candidate columns for an eligible table."""
    roles: dict[str, int] = {}
    candidate_columns: list[tuple[int, str]] = []

    for column_index, column in enumerate(frame.columns):
        header = column_header_text(column)
        normalized = normalize(header)
        if (
            normalized in {normalize(value) for value in POLLSTER_HEADERS}
            or normalized.startswith(("polling firm ", "pollster "))
        ):
            roles.setdefault("pollster", column_index)
        elif (
            normalized in {normalize(value) for value in FIELDWORK_HEADERS}
            or normalized.startswith(("fieldwork ", "date conducted "))
            or normalized.startswith("dates conducted ")
        ):
            roles.setdefault("fieldwork", column_index)
        elif (
            normalized in {normalize(value) for value in SAMPLE_HEADERS}
            or normalized.startswith("sample size ")
        ):
            roles.setdefault("sample_size", column_index)
        else:
            name = canonical_candidate_name(candidate_name(header))
            if name and not name.startswith("Unnamed:"):
                candidate_columns.append((column_index, name))

    if set(roles) != {"pollster", "fieldwork", "sample_size"}:
        return None
    if len(candidate_columns) < 3:
        return None

    normalized_names = [normalize(name) for _, name in candidate_columns]
    if len(normalized_names) != len(set(normalized_names)):
        raise ValueError("eligible first-round table has duplicate candidates")
    return roles, candidate_columns


def _table_heading_context(table: object) -> tuple[str, str | None]:
    headings = table.xpath(
        "preceding::*[self::h2 or self::h3 or self::h4 or self::h5]"
    )
    recent = [
        re.sub(r"\s+", " ", heading.text_content()).strip()
        for heading in headings[-4:]
    ]
    round_heading: str | None = None
    for heading in reversed(recent):
        normalized = normalize(heading)
        if "first round" in normalized or any(
            normalize(marker) in normalized
            for marker in EXCLUDED_ROUND_CONTEXT
        ):
            round_heading = normalized
            break
    return " / ".join(recent), round_heading


def discover_first_round_tables(
    page_html: str,
) -> list[tuple[int, pd.DataFrame, dict[str, int], list[tuple[int, str]]]]:
    """Discover first-round polling tables in deterministic document order."""
    document = lxml_html.fromstring(page_html)
    discovered = []

    for table_order, table in enumerate(document.xpath("//table")):
        # A structural wrapper may contain several real data tables.
        # Passing the wrapper to pandas.read_html() returns one frame for
        # each nested table and can duplicate or reject valid poll tables.
        # Process only leaf tables; nested tables are visited separately
        # in their original deterministic document order.
        if table.xpath(".//table"):
            continue

        context, round_heading = _table_heading_context(table)
        normalized_context = normalize(context)
        if round_heading and (
            "first round" not in round_heading
            or any(
                normalize(marker) in round_heading
                for marker in EXCLUDED_ROUND_CONTEXT
            )
        ):
            continue
        if any(
            normalize(marker) in normalized_context
            for marker in EXCLUDED_ROUND_CONTEXT
        ) and "first round" not in normalize(round_heading or ""):
            continue

        frames = pd.read_html(
            io.StringIO(lxml_html.tostring(table, encoding="unicode")),
            extract_links="body",
        )
        if len(frames) != 1:
            raise ValueError(
                f"table {table_order}: expected one parsed frame"
            )
        frame = frames[0]
        contract = table_column_contract(frame)
        if contract is None:
            continue
        roles, candidate_columns = contract
        discovered.append(
            (table_order, frame, roles, candidate_columns)
        )

    return discovered


def parse_wikipedia_first_round_html(
    page_html: str,
    overrides: PollWaveOverrides | None = None,
) -> tuple[list[dict], list[str]]:
    tables = discover_first_round_tables(page_html)
    if not tables:
        raise ValueError("no eligible first-round polling tables discovered")

    events: list[dict] = []
    skipped: list[str] = []

    for table_order, frame, roles, candidate_columns in tables:
        for row_index, row in frame.iterrows():
            pollster = canonical_pollster_name(
                cell_text(row.iloc[roles["pollster"]])
            )
            fieldwork_raw = cell_text(row.iloc[roles["fieldwork"]])

            if not pollster or normalize(pollster) in {"2022 election", "election"}:
                continue

            try:
                fieldwork_start, fieldwork_end = parse_fieldwork(fieldwork_raw)
            except ValueError as error:
                raise ValueError(
                    f"table {table_order} row {row_index}: "
                    f"unparsed fieldwork date {fieldwork_raw!r}"
                ) from error

            candidates: list[dict] = []
            censored_scores: list[tuple[str, str]] = []

            for column_index, name in candidate_columns:
                raw_score = cell_text(row.iloc[column_index])

                normalized_score = re.sub(
                    r"\[[^\]]*]",
                    "",
                    raw_score,
                )
                normalized_score = (
                    normalized_score
                    .replace(",", ".")
                    .replace("%", "")
                    .strip()
                )

                if re.fullmatch(
                    r"<\s*\d+(?:\.\d+)?",
                    normalized_score,
                ):
                    censored_scores.append(
                        (name, normalized_score)
                    )
                    continue

                try:
                    score = parse_score(raw_score)
                except ValueError as error:
                    raise ValueError(
                        f"{pollster} {fieldwork_raw} table {table_order} "
                        f"row {row_index}: {name}: {error}"
                    ) from error

                if score is not None:
                    candidates.append({"name": name, "score": score})

            if censored_scores:
                details = ", ".join(
                    f"{name} {value!r}"
                    for name, value in censored_scores
                )
                skipped.append(
                    f"{pollster} {fieldwork_raw} "
                    f"table {table_order} row {row_index} "
                    f"skipped because the source reports "
                    f"censored score(s): {details}"
                )
                continue

            if len(candidates) < 2:
                continue

            source_url = (
                cell_link(row.iloc[roles["pollster"]]) or SOURCE_URL
            )
            sample_size = parse_sample_size(
                cell_text(row.iloc[roles["sample_size"]])
            )
            fieldwork_start, fieldwork_end = (
                apply_official_poll_metadata_correction(
                    pollster,
                    fieldwork_start,
                    fieldwork_end,
                    sample_size,
                    source_url,
                    overrides,
                )
            )
            names = [candidate["name"] for candidate in candidates]
            hypothesis = "First round — " + ", ".join(names)

            try:
                event = apply_completeness_contract({
                    "event_id": make_event_id(
                        pollster,
                        fieldwork_start,
                        fieldwork_end,
                        hypothesis,
                        source_url,
                    ),
                    "pollster": pollster,
                    "commissioner": None,
                    "publication_date": None,
                    "fieldwork_start": fieldwork_start,
                    "fieldwork_end": fieldwork_end,
                    "sample_size": sample_size,
                    "round": ROUND,
                    "hypothesis": hypothesis,
                    "scenario_key": make_scenario_key(names),
                    "source_url": source_url,
                    "candidates": candidates,
                })
            except PollContractError as error:
                if not str(error).startswith(
                    "reported total is impossible:"
                ):
                    raise

                skipped.append(
                    f"{pollster} {fieldwork_raw} "
                    f"table {table_order} row {row_index}: "
                    f"Wikipedia row rejected by poll contract: "
                    f"{error}"
                )
                continue

            events.append(event)

    validate_poll_events(events)
    return events, skipped


def fetch_wikipedia_events(
    overrides: PollWaveOverrides | None = None,
) -> tuple[list[dict], list[str]]:
    request = Request(SOURCE_URL, headers={"User-Agent": USER_AGENT})
    with urlopen(request, timeout=60) as response:
        page_html = response.read().decode("utf-8")
    return parse_wikipedia_first_round_html(page_html, overrides)


def fetch_mediawiki_parse(parameters: dict[str, str]) -> dict:
    """Fetch a parsed MediaWiki response with the repository User-Agent."""
    query = {
        "action": "parse",
        "format": "json",
        "formatversion": "2",
        **parameters,
    }
    request = Request(
        f"{MEDIAWIKI_API_URL}?{urlencode(query)}",
        headers={"User-Agent": USER_AGENT},
    )
    with urlopen(request, timeout=60) as response:
        payload = json.load(response)
    if "error" in payload:
        raise ValueError(f"MediaWiki parse error: {payload['error']}")
    if "parse" not in payload:
        raise ValueError("MediaWiki response is missing parsed page data")
    return payload["parse"]


def canonical_matchup_candidate(value: str) -> str:
    """Resolve a full name or explicitly reviewed runoff-heading alias."""
    raw_name = candidate_name(value)
    heading_alias = RUNOFF_HEADING_CANDIDATE_ALIASES.get(normalize(raw_name))
    if heading_alias:
        return heading_alias
    direct = CANDIDATE_NORMALIZATION_ALIASES.get(normalize(raw_name))
    if direct:
        return direct
    if len(raw_name.split()) >= 2 and "�" not in raw_name:
        return raw_name
    raise ValueError(
        f"matchup candidate is not uniquely identifiable: {value!r}"
    )


def matchup_candidates_from_heading(heading: str) -> list[str]:
    parts = re.split(r"\s+vs\.?\s+", heading.strip(), flags=re.IGNORECASE)
    if len(parts) != 2 or not all(part.strip() for part in parts):
        raise ValueError(f"invalid matchup section heading: {heading!r}")
    candidates = [canonical_matchup_candidate(part) for part in parts]
    if len(set(candidates)) != 2:
        raise ValueError(f"duplicate candidate in matchup heading: {heading!r}")
    return candidates


def discover_second_round_sections() -> tuple[int, list[dict]]:
    """Discover main second-round matchup sections from MediaWiki hierarchy."""
    parsed = fetch_mediawiki_parse(
        {"page": SOURCE_PAGE, "prop": "tocdata|revid"}
    )
    revision_id = parsed.get("revid")
    tocdata = parsed.get("tocdata")
    sections = tocdata.get("sections") if isinstance(tocdata, dict) else None
    if not revision_id or not isinstance(sections, list):
        raise ValueError("MediaWiki tocdata response lacks revision or sections")

    top_matches = [
        (index, section)
        for index, section in enumerate(sections)
        if section.get("tocLevel") == 1
        and normalize(str(section.get("line", ""))) == "second round"
    ]
    if len(top_matches) != 1:
        raise ValueError(
            "expected exactly one top-level 'Second round' section, found "
            f"{len(top_matches)}"
        )

    start_index, top = top_matches[0]
    boundary: list[dict] = [top]
    for section in sections[start_index + 1 :]:
        if int(section.get("tocLevel", 0)) <= int(top["tocLevel"]):
            break
        boundary.append(section)

    stack: list[dict] = []
    matchups: list[dict] = []
    for section in boundary:
        level = int(section["tocLevel"])
        while stack and int(stack[-1]["tocLevel"]) >= level:
            stack.pop()

        heading = str(section.get("line", "")).strip()
        if re.search(r"\s+vs\.?\s+", heading, flags=re.IGNORECASE):
            candidates = matchup_candidates_from_heading(heading)
            ancestry = [str(item["line"]).strip() for item in stack]
            declined = any(
                normalize(item) == "declined to be candidates"
                for item in ancestry
            )
            if declined:
                source_scope = "source_declined_candidate_section"
            elif len(stack) == 1 and stack[0] is top:
                source_scope = "current_tested"
            else:
                raise ValueError(
                    f"matchup section has unsupported ancestry: "
                    f"{' > '.join([*ancestry, heading])}"
                )
            matchups.append(
                {
                    "index": str(section["index"]),
                    "heading": heading,
                    "path": [*ancestry, heading],
                    "scope": source_scope,
                    "candidates": candidates,
                }
            )

        stack.append(section)

    if not matchups:
        raise ValueError("no matchup sections found in main Second round boundary")
    return int(revision_id), matchups


def table_header_columns(table: object) -> list[list[object]]:
    """Expand row/column spans into deterministic per-column header cells."""
    rows = table.xpath("./thead/tr | ./tbody/tr | ./tr")
    header_rows: list[object] = []
    for row in rows:
        if row.xpath("./td"):
            break
        if row.xpath("./th"):
            header_rows.append(row)
    if not header_rows:
        return []

    grid: dict[tuple[int, int], object] = {}
    for row_index, row in enumerate(header_rows):
        column_index = 0
        for cell in row.xpath("./th"):
            while (row_index, column_index) in grid:
                column_index += 1
            try:
                rowspan = int(cell.get("rowspan", "1"))
                colspan = int(cell.get("colspan", "1"))
            except ValueError as exc:
                raise ValueError("non-numeric table header span") from exc
            if rowspan < 1 or colspan < 1:
                raise ValueError("invalid table header span")
            for target_row in range(row_index, row_index + rowspan):
                for target_column in range(
                    column_index, column_index + colspan
                ):
                    position = (target_row, target_column)
                    if position in grid:
                        raise ValueError("overlapping table header spans")
                    grid[position] = cell
            column_index += colspan

    width = max(column for _, column in grid) + 1
    columns: list[list[object]] = []
    for column_index in range(width):
        cells: list[object] = []
        seen: set[int] = set()
        for row_index in range(len(header_rows)):
            cell = grid.get((row_index, column_index))
            if cell is not None and id(cell) not in seen:
                cells.append(cell)
                seen.add(id(cell))
        columns.append(cells)
    return columns


def header_text(cells: list[object]) -> str:
    parts = [
        re.sub(r"\s+", " ", cell.text_content()).strip() for cell in cells
    ]
    return " ".join(part for part in parts if part)


def header_candidate(
    cells: list[object], expected_candidates: list[str]
) -> str | None:
    values: list[str] = []
    for cell in cells:
        for anchor in cell.xpath(".//a"):
            values.extend(
                [anchor.get("title", ""), anchor.text_content().strip()]
            )

    matches: set[str] = set()
    for value in values:
        short = normalize(candidate_name(value))
        if not short:
            continue
        for expected in expected_candidates:
            full = normalize(expected)
            if short == full or full.endswith(f" {short}"):
                matches.add(expected)
    if len(matches) > 1:
        raise ValueError(
            f"ambiguous candidate links in table header: {sorted(matches)}"
        )
    return next(iter(matches), None)


def table_column_roles(
    table: object, expected_candidates: list[str]
) -> list[tuple[str, str | None]]:
    roles: list[tuple[str, str | None]] = []
    for cells in table_header_columns(table):
        text = normalize(header_text(cells))
        candidate = header_candidate(cells, expected_candidates)
        if candidate:
            roles.append(("candidate", candidate))
        elif text in {"polling firm", "pollingfirm", "pollster"}:
            roles.append(("pollster", None))
        elif text in {"fieldwork date", "fieldworkdate", "fieldwork"}:
            roles.append(("fieldwork", None))
        elif text in {"sample size", "samplesize", "sample"}:
            roles.append(("sample_size", None))
        elif "commissioner" in text or "client" in text:
            roles.append(("commissioner", None))
        elif "publication date" in text or "published" in text:
            roles.append(("publication_date", None))
        else:
            roles.append(("unknown", header_text(cells) or None))
    return roles


def valid_http_url(value: str) -> bool:
    parsed = urlparse(value)
    return parsed.scheme in {"http", "https"} and bool(parsed.netloc)


def compact_number(value: float) -> int | float:
    return int(value) if value.is_integer() else value


def parse_publication_date(value: str) -> str | None:
    if normalize(value) in DASHES:
        return None
    start, end = parse_fieldwork(value)
    if start != end:
        raise ValueError(f"ambiguous publication date range: {value!r}")
    return start


def qualify_second_round_table(
    table: object,
    frame: pd.DataFrame,
    section: dict,
) -> dict | None:
    roles = table_column_roles(table, section["candidates"])
    role_names = [role for role, _ in roles]
    required = {"pollster", "fieldwork", "sample_size"}
    candidate_count = role_names.count("candidate")

    if not required.issubset(role_names) or candidate_count != 2:
        return None
    if len(roles) != len(frame.columns):
        raise ValueError(
            f"{section['heading']}: rendered header has {len(roles)} columns "
            f"but pandas parsed {len(frame.columns)}"
        )

    duplicates = [
        role
        for role in (
            "pollster",
            "fieldwork",
            "sample_size",
            "commissioner",
            "publication_date",
        )
        if role_names.count(role) > 1
    ]
    if duplicates:
        raise ValueError(
            f"{section['heading']}: ambiguous duplicate fields {duplicates}"
        )

    unknown = [detail or "<blank>" for role, detail in roles if role == "unknown"]
    if unknown:
        raise ValueError(
            f"{section['heading']}: unknown structural columns {unknown}"
        )

    header_candidates = [detail for role, detail in roles if role == "candidate"]
    if set(header_candidates) != set(section["candidates"]):
        raise ValueError(
            f"{section['heading']}: heading candidates "
            f"{section['candidates']} disagree with table headers "
            f"{header_candidates}"
        )

    indexes: dict[str, int] = {}
    candidate_indexes: list[tuple[int, str]] = []
    for index, (role, detail) in enumerate(roles):
        if role == "candidate":
            if detail is None:
                raise ValueError(f"{section['heading']}: blank candidate header")
            candidate_indexes.append((index, detail))
        else:
            indexes[role] = index
    indexes["candidates"] = candidate_indexes  # type: ignore[assignment]
    return indexes


def validate_second_round_event(event: dict) -> None:
    candidates = event.get("candidates")
    if not isinstance(candidates, list) or len(candidates) != 2:
        raise ValueError("second-round event must have exactly two candidates")

    for candidate in candidates:
        name = candidate.get("name")
        score = candidate.get("score")
        if canonical_candidate_name(str(name), strict=True) != name:
            raise ValueError(f"non-canonical candidate name: {name!r}")
        if (
            isinstance(score, bool)
            or not isinstance(score, (int, float))
            or not math.isfinite(score)
            or not 0 <= score <= 100
        ):
            raise ValueError(f"invalid candidate score: {score!r}")

    total = sum(candidate["score"] for candidate in candidates)
    if not 99 <= total <= 101:
        raise ValueError(f"second-round candidate total is {total:g}")
    if not event.get("fieldwork_start") or not event.get("fieldwork_end"):
        raise ValueError("second-round event lacks parsed fieldwork dates")
    if not str(event.get("pollster", "")).strip():
        raise ValueError("second-round event lacks pollster")
    if not valid_http_url(str(event.get("source_url", ""))):
        raise ValueError(
            f"second-round event lacks direct HTTP source: "
            f"{event.get('source_url')!r}"
        )

    names = [candidate["name"] for candidate in candidates]
    expected_matchup_key = make_scenario_key(
        names, round_name=SECOND_ROUND
    )
    if event.get("matchup_key") != expected_matchup_key:
        raise ValueError("non-deterministic second-round matchup_key")
    expected_event_id = make_event_id(
        event["pollster"],
        event["fieldwork_start"],
        event["fieldwork_end"],
        event["hypothesis"],
        event["source_url"],
        round_name=SECOND_ROUND,
    )
    if event.get("event_id") != expected_event_id:
        raise ValueError("non-deterministic second-round event_id")
    expected_margin = abs(candidates[0]["score"] - candidates[1]["score"])
    if event.get("margin") != expected_margin:
        raise ValueError("second-round margin does not match exact scores")
    if event.get("round") != SECOND_ROUND:
        raise ValueError("second-round event has unexpected round")
    if event.get("source_scope") not in {
        "current_tested",
        "source_declined_candidate_section",
    }:
        raise ValueError("second-round event has unexpected source_scope")


def parse_second_round_section(
    section: dict, revision_id: int
) -> tuple[list[dict], int]:
    parsed = fetch_mediawiki_parse(
        {
            "oldid": str(revision_id),
            "prop": "text|revid",
            "section": section["index"],
        }
    )
    if int(parsed.get("revid", 0)) != revision_id:
        raise ValueError(
            f"{section['heading']}: MediaWiki revision changed while parsing"
        )
    section_html = parsed.get("text")
    if not isinstance(section_html, str):
        raise ValueError(f"{section['heading']}: missing rendered section HTML")

    root = lxml_html.fromstring(section_html)
    dom_tables = root.xpath(".//table")
    frames = pd.read_html(io.StringIO(section_html), extract_links="all")
    if len(dom_tables) != len(frames):
        raise ValueError(
            f"{section['heading']}: lxml found {len(dom_tables)} tables but "
            f"pandas found {len(frames)}"
        )

    qualifying: list[tuple[pd.DataFrame, dict]] = []
    for table, frame in zip(dom_tables, frames, strict=True):
        indexes = qualify_second_round_table(table, frame, section)
        if indexes is not None:
            qualifying.append((frame, indexes))
    if len(qualifying) != 1:
        raise ValueError(
            f"{section['heading']}: expected exactly one qualifying polling "
            f"table, found {len(qualifying)}"
        )

    frame, indexes = qualifying[0]
    events: list[dict] = []
    excluded_comparisons = 0
    for row_number, (_, row) in enumerate(frame.iterrows(), start=1):
        pollster = cell_text(row.iloc[indexes["pollster"]])
        if normalize(pollster) in {"2022 election", "election"}:
            excluded_comparisons += 1
            continue
        if not pollster:
            raise ValueError(
                f"{section['heading']} row {row_number}: blank pollster"
            )

        source_link = cell_link(row.iloc[indexes["pollster"]])
        source_url = urljoin(SOURCE_URL, source_link) if source_link else ""
        if not valid_http_url(source_url):
            raise ValueError(
                f"{section['heading']} row {row_number}: pollster "
                f"{pollster!r} lacks a direct supporting source URL"
            )

        fieldwork_raw = cell_text(row.iloc[indexes["fieldwork"]])
        try:
            fieldwork_start, fieldwork_end = parse_fieldwork(fieldwork_raw)
        except ValueError as exc:
            raise ValueError(
                f"{section['heading']} row {row_number}: ambiguous fieldwork "
                f"date {fieldwork_raw!r}"
            ) from exc

        candidates: list[dict] = []
        for column_index, name in indexes["candidates"]:
            raw_score = cell_text(row.iloc[column_index])
            try:
                score = parse_score(raw_score)
            except ValueError as exc:
                raise ValueError(
                    f"{section['heading']} row {row_number}: {name} {exc}"
                ) from exc
            if score is None:
                raise ValueError(
                    f"{section['heading']} row {row_number}: missing score "
                    f"for {name}"
                )
            candidates.append({"name": name, "score": compact_number(score)})

        commissioner = (
            cell_text(row.iloc[indexes["commissioner"]])
            if "commissioner" in indexes
            else None
        ) or None
        publication_date = None
        if "publication_date" in indexes:
            publication_raw = cell_text(row.iloc[indexes["publication_date"]])
            publication_date = parse_publication_date(publication_raw)

        sample_size = parse_sample_size(
            cell_text(row.iloc[indexes["sample_size"]])
        )
        quality_flags = [] if sample_size is not None else ["missing_sample_size"]
        names = [candidate["name"] for candidate in candidates]
        hypothesis = "Second round — " + " vs ".join(names)
        matchup_key = make_scenario_key(names, round_name=SECOND_ROUND)
        margin = compact_number(
            abs(float(candidates[0]["score"]) - float(candidates[1]["score"]))
        )
        event = {
            "event_id": make_event_id(
                pollster,
                fieldwork_start,
                fieldwork_end,
                hypothesis,
                source_url,
                round_name=SECOND_ROUND,
            ),
            "round": SECOND_ROUND,
            "pollster": pollster,
            "commissioner": commissioner,
            "publication_date": publication_date,
            "fieldwork_start": fieldwork_start,
            "fieldwork_end": fieldwork_end,
            "sample_size": sample_size,
            "matchup_key": matchup_key,
            "hypothesis": hypothesis,
            "candidates": candidates,
            "margin": margin,
            "source_url": source_url,
            "source_page_url": SOURCE_URL,
            "source_section": section["heading"],
            "source_section_path": section["path"],
            "source_scope": section["scope"],
            "quality_flags": quality_flags,
        }
        validate_second_round_event(event)
        events.append(event)
    return events, excluded_comparisons


def fetch_second_round_events() -> tuple[list[dict], dict]:
    revision_id, sections = discover_second_round_sections()
    events: list[dict] = []
    excluded_comparisons = 0
    for section in sections:
        section_events, section_excluded = parse_second_round_section(
            section, revision_id
        )
        events.extend(section_events)
        excluded_comparisons += section_excluded

    events.sort(
        key=lambda event: (
            -int(event["fieldwork_end"].replace("-", "")),
            -int(event["fieldwork_start"].replace("-", "")),
            normalize(event["pollster"]),
            event["matchup_key"],
            event["event_id"],
        )
    )
    event_ids = [event["event_id"] for event in events]
    if len(event_ids) != len(set(event_ids)):
        raise ValueError("second-round events contain duplicate event_id values")
    for event in events:
        validate_second_round_event(event)

    audit = {
        "revision_id": revision_id,
        "table_count": len(sections),
        "excluded_comparison_rows": excluded_comparisons,
        "source_scope_counts": {
            scope: sum(event["source_scope"] == scope for event in events)
            for scope in (
                "current_tested",
                "source_declined_candidate_section",
            )
        },
    }
    return events, audit


def derive_closest_tested_runoff(events: list[dict]) -> dict:
    """Derive agreement from exact common matchups in the newest valid window."""
    current_events = [
        event for event in events if event["source_scope"] == "current_tested"
    ]
    windows: dict[tuple[str, str], list[dict]] = {}
    for event in current_events:
        window = (event["fieldwork_start"], event["fieldwork_end"])
        windows.setdefault(window, []).append(event)

    selected_window: tuple[str, str] | None = None
    selected_by_pollster: dict[str, dict[str, dict]] = {}
    common_keys: set[str] = set()
    for window in sorted(windows, key=lambda item: (item[1], item[0]), reverse=True):
        by_pollster: dict[str, dict[str, dict]] = {}
        duplicate = False
        for event in windows[window]:
            pollster_events = by_pollster.setdefault(event["pollster"], {})
            if event["matchup_key"] in pollster_events:
                duplicate = True
                break
            pollster_events[event["matchup_key"]] = event
        if duplicate:
            raise ValueError(
                f"duplicate pollster/matchup record in fieldwork window {window}"
            )
        if len(by_pollster) < 2:
            continue
        if any(len(pollster_events) < 2 for pollster_events in by_pollster.values()):
            continue
        intersection = set.intersection(
            *(set(pollster_events) for pollster_events in by_pollster.values())
        )
        if len(intersection) < 2:
            continue
        selected_window = window
        selected_by_pollster = by_pollster
        common_keys = intersection
        break

    if selected_window is None:
        return {
            "status": "insufficient",
            "message": (
                "No recent common testing window has enough pollsters and "
                "matchups."
            ),
            "secondary_message": None,
            "fieldwork_window": None,
            "pollster_count": 0,
            "common_matchup_count": 0,
            "selected_matchup": None,
            "pollsters": [],
            "common_matchups": [],
        }

    pollster_names = sorted(selected_by_pollster, key=normalize)
    closest_keys: dict[str, list[str]] = {}
    for pollster in pollster_names:
        common_events = selected_by_pollster[pollster]
        minimum = min(common_events[key]["margin"] for key in common_keys)
        closest_keys[pollster] = sorted(
            key
            for key in common_keys
            if common_events[key]["margin"] == minimum
        )

    if any(len(keys) > 1 for keys in closest_keys.values()):
        status = "ambiguous"
    elif len({keys[0] for keys in closest_keys.values()}) == 1:
        status = "agree"
    else:
        status = "split"

    selected_key = closest_keys[pollster_names[0]][0] if status == "agree" else None
    if status == "agree" and len(pollster_names) == 2:
        message = "Both pollsters agree this is the closest tested runoff"
    elif status == "agree":
        message = (
            f"All {len(pollster_names)} pollsters agree this is the closest "
            "tested runoff"
        )
    elif status == "split":
        message = "Pollsters identify different closest tested runoffs"
    else:
        message = "At least one pollster has a tie for the closest tested runoff"

    secondary_message = None
    if status == "agree" and selected_key is not None:
        selected_margins = {
            selected_by_pollster[pollster][selected_key]["margin"]
            for pollster in pollster_names
        }
        if len(selected_margins) > 1:
            secondary_message = "Same closest matchup, different distance."

    def result_record(event: dict) -> dict:
        return {
            "event_id": event["event_id"],
            "pollster": event["pollster"],
            "candidates": event["candidates"],
            "margin": event["margin"],
            "source_url": event["source_url"],
        }

    common_matchups: list[dict] = []
    for matchup_key in sorted(common_keys):
        representative = selected_by_pollster[pollster_names[0]][matchup_key]
        common_matchups.append(
            {
                "matchup_key": matchup_key,
                "candidates": [
                    candidate["name"] for candidate in representative["candidates"]
                ],
                "results": [
                    result_record(selected_by_pollster[pollster][matchup_key])
                    for pollster in pollster_names
                ],
            }
        )

    pollsters = []
    for pollster in pollster_names:
        pollsters.append(
            {
                "pollster": pollster,
                "closest_matchups": [
                    {
                        "matchup_key": key,
                        "candidates": [
                            candidate["name"]
                            for candidate in selected_by_pollster[pollster][key][
                                "candidates"
                            ]
                        ],
                        "result": result_record(
                            selected_by_pollster[pollster][key]
                        ),
                    }
                    for key in closest_keys[pollster]
                ],
            }
        )

    selected_matchup = None
    if selected_key is not None:
        representative = selected_by_pollster[pollster_names[0]][selected_key]
        selected_matchup = {
            "matchup_key": selected_key,
            "candidates": [
                candidate["name"] for candidate in representative["candidates"]
            ],
            "results": [
                result_record(selected_by_pollster[pollster][selected_key])
                for pollster in pollster_names
            ],
        }

    return {
        "status": status,
        "message": message,
        "secondary_message": secondary_message,
        "fieldwork_window": {
            "start": selected_window[0],
            "end": selected_window[1],
        },
        "pollster_count": len(pollster_names),
        "common_matchup_count": len(common_keys),
        "selected_matchup": selected_matchup,
        "pollsters": pollsters,
        "common_matchups": common_matchups,
    }


def fetch_pdf(notice: dict) -> PdfReader:
    """Fetch a registry notice and retain its resolved URL and digest."""
    document = fetch_official_url(notice["listed_url"], "GET")
    data = document.content
    if not data.startswith(b"%PDF"):
        raise ValueError(
            "configured notice did not return a PDF: "
            f"{notice['notice_id']} ({document.final_url})"
        )
    notice["resolved_url"] = document.final_url
    notice["content_sha256"] = hashlib.sha256(data).hexdigest()
    return PdfReader(io.BytesIO(data))


def page_text(reader: PdfReader, page_index: int, institute: str) -> str:
    if page_index >= len(reader.pages):
        raise ValueError(
            f"{institute} notice has no PDF page {page_index + 1}"
        )
    text = reader.pages[page_index].extract_text()
    if not text:
        raise ValueError(
            f"{institute} PDF page {page_index + 1} has no extractable text"
        )
    return text


def parse_decimal(value: str) -> float:
    if not re.fullmatch(r"\d+(?:[,.]\d+)?", value.strip()):
        raise ValueError(f"invalid official score: {value!r}")
    return float(value.replace(",", "."))


def make_official_event(notice: dict, candidates: list[dict]) -> dict:
    institute = notice["pollster"]
    names = [candidate["name"] for candidate in candidates]
    hypothesis = "First round — " + ", ".join(names)
    source_url = notice["event_source_url"]
    return apply_completeness_contract({
        "event_id": make_event_id(
            institute,
            notice["fieldwork_start"],
            notice["fieldwork_end"],
            hypothesis,
            source_url,
        ),
        "pollster": institute,
        "commissioner": notice.get("poll_commissioner"),
        "publication_date": notice["publication_date"],
        "fieldwork_start": notice["fieldwork_start"],
        "fieldwork_end": notice["fieldwork_end"],
        "sample_size": notice["sample_size"],
        "round": ROUND,
        "hypothesis": hypothesis,
        "scenario_key": make_scenario_key(names),
        "source_url": source_url,
        "official_notice_id": notice["notice_id"],
        "official_notice_url": notice["resolved_url"],
        "candidates": candidates,
    })


def parse_elabe(reader: PdfReader, notice: dict) -> list[dict]:
    lines = [line.strip() for line in page_text(reader, 6, "Elabe").splitlines()]
    blocks: list[list[dict]] = []
    current: list[dict] | None = None
    result_line = re.compile(r"^(.+?)\s+(\d+(?:[,.]\d+)?)$")

    for line in lines:
        normalized = normalize(line)
        if normalized in {"1er tour publie", "1er tour"}:
            if current is not None:
                blocks.append(current)
            current = []
            continue
        if current is None:
            continue
        if re.search(r"\b(?:2e|2eme|second) tour\b", normalized):
            break

        match = result_line.fullmatch(line)
        if not match:
            continue
        raw_name, raw_score = match.groups()
        if normalize(raw_name).startswith("vote blanc ou nul abstention"):
            continue
        current.append(
            {
                "name": canonical_candidate_name(raw_name, strict=True),
                "score": parse_decimal(raw_score),
            }
        )

    if current is not None:
        blocks.append(current)
    return [make_official_event(notice, candidates) for candidates in blocks]


def parse_ipsos(reader: PdfReader, notice: dict) -> list[dict]:
    events: list[dict] = []
    percentage_line = re.compile(r"^(\d+(?:[,.]\d+)?)%$")

    for page_index in range(9, 17):
        lines = [
            line.strip()
            for line in page_text(reader, page_index, "Ipsos").splitlines()
        ]
        scores = [
            parse_decimal(match.group(1))
            for line in lines
            if (match := percentage_line.fullmatch(line))
        ]
        names = [
            CANDIDATE_NORMALIZATION_ALIASES[normalize(line)]
            for line in lines
            if normalize(line) in CANDIDATE_NORMALIZATION_ALIASES
        ]
        if len(names) != len(scores):
            raise ValueError(
                f"Ipsos PDF page {page_index + 1}: "
                f"{len(names)} candidate names for {len(scores)} scores"
            )
        candidates = [
            {"name": name, "score": score}
            for name, score in zip(names, scores, strict=True)
        ]
        events.append(make_official_event(notice, candidates))
    return events


def ifop_result_area(text: str, page_number: int) -> list[str]:
    lines = [line.strip() for line in text.splitlines()]
    start: int | None = None
    for index, line in enumerate(lines):
        if normalize(line) == "resultats publies":
            start = index + 1
            break
        if normalize(line) == "resultats":
            next_index = index + 1
            while next_index < len(lines) and not lines[next_index]:
                next_index += 1
            if (
                next_index < len(lines)
                and normalize(lines[next_index]) == "publies"
            ):
                start = next_index + 1
                break
    if start is None:
        raise ValueError(
            f"Ifop PDF page {page_number}: missing 'resultats publies' marker"
        )

    area: list[str] = []
    for line in lines[start:]:
        if normalize(line).startswith("total 100"):
            return area
        if line:
            area.append(line)
    raise ValueError(f"Ifop PDF page {page_number}: missing 'TOTAL 100' marker")


def parse_ifop(reader: PdfReader, notice: dict) -> list[dict]:
    events: list[dict] = []
    result_line = re.compile(r"^(.+?)\s+(\d+(?:[,.]\d+)?)$")

    for page_index in range(8, 16):
        area = ifop_result_area(
            page_text(reader, page_index, "Ifop"), page_index + 1
        )
        candidates: list[dict] = []
        pending = ""
        for line in area:
            match = result_line.fullmatch(line)
            if not match:
                pending = f"{pending} {line}".strip()
                continue
            raw_name, raw_score = match.groups()
            if pending:
                separator = "" if pending.endswith("-") else " "
                raw_name = f"{pending}{separator}{raw_name}"
                pending = ""
            candidates.append(
                {
                    "name": canonical_candidate_name(raw_name, strict=True),
                    "score": parse_decimal(raw_score),
                }
            )
        if pending:
            raise ValueError(
                f"Ifop PDF page {page_index + 1}: "
                f"unmatched result text {pending!r}"
            )
        events.append(make_official_event(notice, candidates))
    return events


def validate_official_events(notice: dict, events: list[dict]) -> None:
    institute = notice["pollster"]
    expected = notice["expected_first_round_events"]
    if len(events) != expected:
        raise ValueError(
            f"{institute}: expected {expected} events, parsed {len(events)}"
        )
    for index, event in enumerate(events, start=1):
        candidates = event["candidates"]
        if len(candidates) < 2:
            raise ValueError(f"{institute} event {index} has fewer than 2 candidates")
        names = [normalize(candidate["name"]) for candidate in candidates]
        if len(names) != len(set(names)):
            raise ValueError(f"{institute} event {index} has duplicate candidates")
        total = sum(candidate["score"] for candidate in candidates)
        if not 99.0 <= total <= 101.0:
            raise ValueError(
                f"{institute} event {index} candidate total is {total:g}"
            )


def fetch_official_events(
    registry: dict,
) -> tuple[list[dict], dict[str, int], list[dict]]:
    parsers = {
        "elabe": parse_elabe,
        "ipsos": parse_ipsos,
        "ifop": parse_ifop,
    }
    all_events: list[dict] = []
    counts: dict[str, int] = {}
    parsed_notices: list[dict] = []

    for notice in registry["notices"]:
        if notice["classification"] != "eligible" or notice.get("parser"):
            continue
        notice["classification"] = "unsupported"
        notice["classification_reason"] = (
            "document confirms 2027 presidential voting intentions, but no "
            "existing notice parser supports this listing"
        )

    for notice in registry_event_notices(registry):
        parser_name = notice["parser"]
        parser = parsers.get(parser_name)
        if parser is None:
            raise ValueError(
                f"{notice['notice_id']}: unknown official parser {parser_name!r}"
            )
        events = parser(fetch_pdf(notice), notice)
        validate_official_events(notice, events)
        counts[notice["notice_id"]] = len(events)
        all_events.extend(events)
        parsed_notices.append(notice)

    keys = [logical_key(event) for event in all_events]
    if len(keys) != len(set(keys)):
        raise ValueError("official notices contain duplicate logical poll identities")
    return all_events, counts, parsed_notices


def merge_events(
    wikipedia_events: list[dict], official_events: list[dict]
) -> tuple[list[dict], int, int, int]:
    wikipedia_by_logical_key: dict[tuple[str, str, str, str], dict] = {}
    for event in wikipedia_events:
        key = logical_key(event)
        if key in wikipedia_by_logical_key:
            raise ValueError(f"duplicate Wikipedia logical poll identity: {key}")
        wikipedia_by_logical_key[key] = event

    official_logical_keys = [logical_key(event) for event in official_events]
    if len(official_logical_keys) != len(set(official_logical_keys)):
        raise ValueError("official notices contain duplicate logical poll identities")

    official_wave_keys = {poll_wave_key(event) for event in official_events}
    exact_overlaps = sum(
        key in wikipedia_by_logical_key for key in official_logical_keys
    )
    suppressed_wikipedia_events = sum(
        poll_wave_key(event) in official_wave_keys for event in wikipedia_events
    )

    events = [
        event
        for event in wikipedia_events
        if poll_wave_key(event) not in official_wave_keys
    ]
    events.extend(official_events)

    events.sort(
        key=lambda event: (
            -int(event["fieldwork_end"].replace("-", "")),
            -int(event["fieldwork_start"].replace("-", "")),
            normalize(event["pollster"]),
            event["scenario_key"],
        ),
    )
    event_ids = [event["event_id"] for event in events]
    if len(event_ids) != len(set(event_ids)):
        raise ValueError("merged events contain duplicate event_id values")
    return (
        events,
        exact_overlaps,
        suppressed_wikipedia_events,
        len(official_events) - suppressed_wikipedia_events,
    )


def _reviewed_correction_target_wave(
    event: dict,
    overrides: PollWaveOverrides | None = None,
) -> PollWaveKey | None:
    reviewed = _reviewed_overrides(overrides).get(poll_wave_key(event))
    if reviewed is None or "corrections" not in reviewed:
        return None
    reporting_url = reviewed.get("reporting_source_url")
    if reporting_url is not None and reporting_url != str(
        event.get("source_url", "")
    ).strip():
        return None
    corrected_dates = reviewed["corrections"]
    return (
        normalize(str(event.get("pollster", ""))),
        corrected_dates["fieldwork_start"],
        corrected_dates["fieldwork_end"],
        event.get("sample_size"),
    )


def merge_previous_first_round_events(
    fresh_events: list[dict],
    previous_events: list[dict],
    overrides: PollWaveOverrides | None = None,
) -> tuple[list[dict], int, int]:
    """Retain validated missing waves without reviving reviewed bad metadata."""
    if previous_events:
        validate_poll_events(previous_events)

    fresh_events, _fresh_rejected_events, _fresh_rejected_waves = (
        filter_rejected_poll_waves(fresh_events, overrides)
    )
    previous_events, _previous_rejected_events, _previous_rejected_waves = (
        filter_rejected_poll_waves(previous_events, overrides)
    )

    fresh_wave_keys = {poll_wave_key(event) for event in fresh_events}
    previous_wave_keys = {
        poll_wave_key(event) for event in previous_events
    }

    retained: list[dict] = []
    retained_wave_keys: set[PollWaveKey] = set()

    for event in previous_events:
        correction_target = _reviewed_correction_target_wave(event, overrides)
        if correction_target is not None:
            if (
                correction_target not in fresh_wave_keys
                and correction_target not in previous_wave_keys
            ):
                raise ValueError(
                    "reviewed corrected poll wave missing: "
                    f"{correction_target}"
                )
            continue

        wave_key = poll_wave_key(event)
        if wave_key in fresh_wave_keys:
            continue

        retained.append(event)
        retained_wave_keys.add(wave_key)

    events = list(fresh_events)
    events.extend(retained)
    events.sort(
        key=lambda event: (
            -int(event["fieldwork_end"].replace("-", "")),
            -int(event["fieldwork_start"].replace("-", "")),
            normalize(event["pollster"]),
            event["scenario_key"],
        ),
    )

    if events:
        validate_poll_events(events)

    logical_keys = [logical_key(event) for event in events]
    if len(logical_keys) != len(set(logical_keys)):
        raise ValueError(
            "historical persistence produced duplicate logical poll identities"
        )

    return events, len(retained), len(retained_wave_keys)


def validate_merged_official_waves(
    events: list[dict],
    notices: list[dict],
) -> None:
    for notice in notices:
        institute = notice["pollster"]
        expected_wave = (
            normalize(institute),
            notice["fieldwork_start"],
            notice["fieldwork_end"],
            notice["sample_size"],
        )
        wave_events = [
            event for event in events if poll_wave_key(event) == expected_wave
        ]
        expected_count = notice["expected_first_round_events"]
        if len(wave_events) != expected_count:
            raise ValueError(
                f"{institute} official wave: expected {expected_count} merged "
                f"events, found {len(wave_events)}"
            )
        unexpected_sources = [
            event["source_url"]
            for event in wave_events
            if event["source_url"] != notice["event_source_url"]
        ]
        if unexpected_sources:
            raise ValueError(
                f"{institute} official wave contains non-notice sources: "
                f"{sorted(set(unexpected_sources))}"
            )


def atomic_write_json(path: Path | str, payload: Any) -> None:
    """Write one validated JSON artifact with atomic replacement."""
    destination = Path(path)
    destination.parent.mkdir(parents=True, exist_ok=True)
    handle = tempfile.NamedTemporaryFile(
        mode="w",
        encoding="utf-8",
        newline="\n",
        dir=destination.parent,
        prefix=f".{destination.name}.",
        suffix=".tmp",
        delete=False,
    )
    temporary = Path(handle.name)
    try:
        with handle:
            json.dump(payload, handle, ensure_ascii=False, indent=2)
            handle.write("\n")
            handle.flush()
            os.fsync(handle.fileno())
        os.replace(temporary, destination)
    except BaseException:
        try:
            temporary.unlink()
        except FileNotFoundError:
            pass
        raise


def load_previous_second_round_events(path: Path | str) -> list[dict]:
    """Load and strictly validate the last-good runoff archive."""

    source = Path(path)
    try:
        payload = json.loads(source.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as error:
        raise ValueError(f"cannot load previous second-round corpus: {error}") from error
    events = payload.get("events") if isinstance(payload, dict) else None
    if not isinstance(events, list) or not events:
        raise ValueError("previous second-round corpus must contain events")
    event_ids: set[str] = set()
    for event in events:
        validate_second_round_event(event)
        if event["event_id"] in event_ids:
            raise ValueError("previous second-round corpus has duplicate event IDs")
        event_ids.add(event["event_id"])
    return events


def integrate_french_migration_source(
    parsed: dict,
    previous_first: list[dict],
    previous_second: list[dict],
    official_events: list[dict],
    overrides: PollWaveOverrides | None = None,
) -> tuple[list[dict], list[dict], dict, tuple[int, int, int]]:
    """Feed migration-aware French discovery into the existing merge path."""

    from rehearse_fr_poll_migration import reconcile_french_production_source

    migration = reconcile_french_production_source(
        parsed,
        previous_first,
        previous_second,
    )
    previous_first_ids = {event["event_id"] for event in previous_first}
    french_additions = [
        event
        for event in migration.first_round_events
        if event["event_id"] not in previous_first_ids
    ]
    fresh_events, exact_overlaps, suppressed, net_new = merge_events(
        french_additions,
        official_events,
    )
    from poll_migration import load_migration_registry

    migration_registry = load_migration_registry()
    audited_addition_locators = {
        record["source_locator"]
        for record in migration_registry["french_additions"][FIRST_ROUND]
    }
    audited_additions = [
        event
        for event in french_additions
        if event.get("migration_source_locator") in audited_addition_locators
    ]
    previous_wave_keys = {poll_wave_key(event) for event in previous_first}
    for event in official_events:
        if (
            poll_wave_key(event) in previous_wave_keys
            and event["event_id"] not in previous_first_ids
        ):
            raise ValueError(
                "official wave changed a retained event identity during French migration"
            )
    events_by_id = {
        event["event_id"]: copy.deepcopy(event) for event in previous_first
    }
    for event in fresh_events:
        events_by_id[event["event_id"]] = copy.deepcopy(event)
    # The official merge remains authoritative for ordinary source rows.  The
    # one-time registry, however, explicitly reviewed all 29 migration
    # additions, including a single Elabe scenario not emitted by the current
    # official parser.  Restore only that finite audited set after the merge.
    for event in audited_additions:
        events_by_id[event["event_id"]] = copy.deepcopy(event)
    for event in events_by_id.values():
        event.pop("rehearsal_only", None)
    events = sorted(
        events_by_id.values(),
        key=lambda event: (
            -int(event["fieldwork_end"].replace("-", "")),
            -int(event["fieldwork_start"].replace("-", "")),
            normalize(event["pollster"]),
            event["scenario_key"],
            event["event_id"],
        ),
    )
    events, rejected_events, _rejected_waves = filter_rejected_poll_waves(
        events, overrides
    )
    if rejected_events:
        raise ValueError(
            "French migration output contains an explicitly rejected poll wave"
        )
    validate_poll_events(events)
    for event in migration.second_round_events:
        validate_second_round_event(event)

    previous_second_ids = {event["event_id"] for event in previous_second}
    final_first_ids = {event["event_id"] for event in events}
    final_second_ids = {
        event["event_id"] for event in migration.second_round_events
    }
    missing_first = previous_first_ids - final_first_ids
    missing_second = previous_second_ids - final_second_ids
    if missing_first:
        raise ValueError(
            f"French migration lost {len(missing_first)} first-round event IDs"
        )
    if missing_second:
        raise ValueError(
            f"French migration lost {len(missing_second)} second-round event IDs"
        )
    if len(final_second_ids) != len(migration.second_round_events):
        raise ValueError("French migration produced duplicate runoff event IDs")
    return (
        events,
        migration.second_round_events,
        migration.report,
        (exact_overlaps, suppressed, net_new),
    )


def validate_french_phase4a_output_paths(args: argparse.Namespace) -> None:
    """Prevent opt-in French rehearsal mode from replacing tracked artifacts."""

    protected = {
        (Path(__file__).parent / name).resolve()
        for name in (
            "polls.json",
            "second_round_polls.json",
            "closest_tested_runoff.json",
            "commission_notice_registry.json",
        )
    }
    destinations = {
        "--output": Path(args.output).resolve(),
        "--second-round-output": Path(args.second_round_output).resolve(),
        "--closest-runoff-output": Path(args.closest_runoff_output).resolve(),
        "--commission-registry-output": Path(
            args.commission_registry_output or args.commission_registry
        ).resolve(),
    }
    collisions = [option for option, path in destinations.items() if path in protected]
    if collisions:
        raise ValueError(
            "French Phase 4A mode requires non-production temporary outputs: "
            + ", ".join(collisions)
        )


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument(
        "--wikipedia-source",
        choices=WIKIPEDIA_SOURCES,
        default="english",
        help="structured Wikipedia source; French requires explicit selection",
    )
    parser.add_argument(
        "--french-fixture",
        help="offline MediaWiki fixture for explicit French-mode validation",
    )
    parser.add_argument("--output", default="polls.json")
    parser.add_argument(
        "--second-round-output", default="second_round_polls.json"
    )
    parser.add_argument(
        "--closest-runoff-output", default="closest_tested_runoff.json"
    )
    parser.add_argument(
        "--previous-first-round",
        help=(
            "previous validated first-round corpus used only to retain "
            "temporarily missing historical waves"
        ),
    )
    parser.add_argument(
        "--previous-second-round",
        help=(
            "previous validated second-round archive required to preserve "
            "runoff history in French mode"
        ),
    )
    parser.add_argument(
        "--poll-wave-overrides",
        default=str(DEFAULT_POLL_WAVE_OVERRIDES),
        help="reviewed exceptional first-round wave controls",
    )
    parser.add_argument(
        "--commission-registry",
        default="commission_notice_registry.json",
        help="last-good tracked Commission notice registry",
    )
    parser.add_argument(
        "--commission-registry-output",
        help="registry destination after a successful collection",
    )
    parser.add_argument(
        "--discover-commission-notices",
        action="store_true",
        help="run only official notice discovery and registry validation",
    )
    parser.add_argument(
        "--check",
        action="store_true",
        help="validate discovery without writing any files",
    )
    args = parser.parse_args()

    if args.wikipedia_source == "french":
        missing_inputs = [
            option
            for option, value in (
                ("--previous-first-round", args.previous_first_round),
                ("--previous-second-round", args.previous_second_round),
            )
            if not value
        ]
        if missing_inputs:
            parser.error(
                "French source mode requires " + " and ".join(missing_inputs)
            )
        try:
            validate_french_phase4a_output_paths(args)
        except ValueError as error:
            parser.error(str(error))
    elif args.french_fixture:
        parser.error("--french-fixture requires --wikipedia-source french")
    elif args.previous_second_round:
        parser.error("--previous-second-round is used only in French source mode")

    try:
        overrides = load_poll_wave_overrides(Path(args.poll_wave_overrides))
    except ValueError as error:
        parser.error(f"poll wave overrides are invalid: {error}")

    registry_path = Path(args.commission_registry)
    registry_output = Path(
        args.commission_registry_output or args.commission_registry
    )
    try:
        discovery = discover_registry(load_registry(registry_path))
    except (OSError, CommissionNoticeError) as error:
        parser.error(f"Commission notice discovery failed: {error}")

    if args.discover_commission_notices:
        notices = discovery.registry["notices"]
        counts = {
            classification: sum(
                notice["classification"] == classification
                for notice in notices
            )
            for classification in (
                "eligible",
                "excluded_non_voting",
                "ambiguous",
                "unsupported",
            )
        }
        action = "Validated" if args.check else "Discovered"
        print(
            f"{action} {len(notices)} retained Commission notices "
            f"({counts['eligible']} eligible, "
            f"{counts['excluded_non_voting']} excluded, "
            f"{counts['ambiguous']} ambiguous, "
            f"{counts['unsupported']} unsupported)"
        )
        for diagnostic in discovery.diagnostics:
            print(f"  - {diagnostic}")
        if not args.check:
            changed = atomic_write_registry(
                registry_output,
                discovery.registry,
            )
            print(
                f"{'Wrote' if changed else 'Registry unchanged at'} "
                f"{registry_output}"
            )
        return

    if args.check:
        parser.error("--check requires --discover-commission-notices")

    retained_events = 0
    retained_waves = 0
    rejected_previous_events = 0
    french_report: dict | None = None
    if args.wikipedia_source == "french":
        try:
            previous_events = json.loads(
                Path(args.previous_first_round).read_text(encoding="utf-8")
            )
            validate_poll_events(previous_events)
            previous_second_events = load_previous_second_round_events(
                args.previous_second_round
            )
            from poll_migration import load_mediawiki_fixture
            from rehearse_fr_poll_migration import (
                FRENCH_REVISION,
                fetch_live_french_parse,
            )

            parsed_french = (
                load_mediawiki_fixture(Path(args.french_fixture), FRENCH_REVISION)
                if args.french_fixture
                else fetch_live_french_parse()
            )
            official_events, official_counts, parsed_notices = (
                fetch_official_events(discovery.registry)
            )
            (
                events,
                second_round_events,
                french_report,
                official_merge_counts,
            ) = integrate_french_migration_source(
                parsed_french,
                previous_events,
                previous_second_events,
                official_events,
                overrides,
            )
        except (
            OSError,
            json.JSONDecodeError,
            PollContractError,
            ValueError,
        ) as error:
            parser.error(f"French polling migration failed: {error}")
        exact_overlaps, suppressed_wikipedia_events, new_events = (
            official_merge_counts
        )
        wikipedia_events = events
        skipped = [
            f"{french_report['skips']['fail_closed_rows']} fail-closed rows",
            f"{french_report['skips']['ambiguous_identity_rows']} ambiguous identity rows",
        ]
        retained_events = len(previous_events)
        retained_waves = len({poll_wave_key(event) for event in previous_events})
        if (len(previous_events), len(previous_second_events)) == (203, 38):
            expected_baseline = {
                "first_round": 29,
                "second_round": 12,
            }
            if french_report["audited_additions_introduced"] != expected_baseline:
                parser.error(
                    "French migration must introduce every audited 29/12 addition"
                )
            if (
                french_report["source_revision"] == FRENCH_REVISION
                and (len(events), len(second_round_events)) != (232, 50)
            ):
                parser.error(
                    "French audited revision must reconcile to 232 first-round "
                    "and 50 second-round events"
                )
            if len(events) < 232 or len(second_round_events) < 50:
                parser.error("French migration fell below the audited 232/50 baseline")
        second_round_audit = {
            "revision_id": french_report["source_revision"],
            "table_count": 11,
            "excluded_comparison_rows": 0,
            "source_scope_counts": {
                scope: sum(
                    event["source_scope"] == scope
                    for event in second_round_events
                )
                for scope in (
                    "current_tested",
                    "source_declined_candidate_section",
                )
            },
        }
        discovered_waves = len({poll_wave_key(event) for event in events})
    else:
        wikipedia_events, skipped = fetch_wikipedia_events(overrides)
        official_events, official_counts, parsed_notices = fetch_official_events(
            discovery.registry
        )
        (
            events,
            exact_overlaps,
            suppressed_wikipedia_events,
            new_events,
        ) = merge_events(wikipedia_events, official_events)
        rejected_keys = rejected_poll_wave_keys(events, overrides)
        events, rejected_fresh_events, _rejected_fresh_waves = (
            filter_rejected_poll_waves(events, overrides)
        )
        discovered_waves = len({poll_wave_key(event) for event in events})
        if args.previous_first_round:
            previous_path = Path(args.previous_first_round)
            try:
                previous_events = json.loads(
                    previous_path.read_text(encoding="utf-8")
                )
                rejected_keys.update(
                    rejected_poll_wave_keys(previous_events, overrides)
                )
                previous_events, rejected_previous_events, _ = (
                    filter_rejected_poll_waves(previous_events, overrides)
                )
                events, retained_events, retained_waves = (
                    merge_previous_first_round_events(
                        events,
                        previous_events,
                        overrides,
                    )
                )
            except (
                OSError,
                json.JSONDecodeError,
                PollContractError,
                ValueError,
            ) as error:
                parser.error(
                    f"previous first-round corpus is invalid: {error}"
                )
        second_round_events, second_round_audit = fetch_second_round_events()

    if args.wikipedia_source == "french":
        rejected_keys = rejected_poll_wave_keys(events, overrides)
        rejected_fresh_events = 0

    official_source_enriched_waves = apply_official_poll_sources(
        events,
        overrides,
    )
    anomaly_count = validate_reporting_source_wave_anomalies(events)
    official_validation_events = events
    commission_validation_events = events
    if args.wikipedia_source == "french":
        from poll_migration import load_migration_registry

        audited_first_locators = {
            record["source_locator"]
            for record in load_migration_registry()["french_additions"][FIRST_ROUND]
        }
        official_validation_events = [
            event
            for event in events
            if event.get("migration_source_locator") not in audited_first_locators
        ]
        # Commission coverage is wave-level evidence.  The retained corpus and
        # ordinary French rows remain in this view; only the finite one-time
        # addition scenarios are excluded so that their reviewed evidence URLs
        # cannot masquerade as competing published waves.  The reconciliation
        # implementation and every event in the generated output remain
        # unchanged.
        commission_validation_events = official_validation_events
    validate_merged_official_waves(official_validation_events, parsed_notices)
    validate_poll_events(events)
    coverage_counts = reconcile_commission_notices(
        discovery.registry,
        commission_validation_events,
    )
    closest_derivation = derive_closest_tested_runoff(second_round_events)

    generated_at = datetime.now(timezone.utc).isoformat().replace("+00:00", "Z")
    source_metadata = {
        "page_url": (
            FRENCH_SOURCE_URL
            if args.wikipedia_source == "french"
            else SOURCE_URL
        ),
        "revision_id": str(second_round_audit["revision_id"]),
        "license": WIKIPEDIA_LICENSE,
        "modified": True,
        "attribution": "Derived from Wikipedia contributors",
    }
    second_round_output_data = {
        "schema_version": "1.0",
        "generated_at": generated_at,
        "source": source_metadata,
        "events": second_round_events,
    }
    closest_output_data = {
        "schema_version": "1.0",
        "generated_at": generated_at,
        **closest_derivation,
        "source": source_metadata,
        "disclosure": (
            "Uses exact reported scores and margins for common matchups in one "
            "shared fieldwork window. No averages, combined scores, synthetic "
            "margins, win probabilities, or forecasts are calculated."
        ),
    }

    # All network parsing and validation completes before any output is written.
    output = Path(args.output)
    second_round_output = Path(args.second_round_output)
    closest_runoff_output = Path(args.closest_runoff_output)
    atomic_write_json(output, events)
    atomic_write_json(second_round_output, second_round_output_data)
    atomic_write_json(closest_runoff_output, closest_output_data)
    atomic_write_registry(registry_output, discovery.registry)

    print(f"Wikipedia events: {len(wikipedia_events)}")
    for notice in parsed_notices:
        print(
            f"Official {notice['pollster']} {notice['notice_id']} events: "
            f"{official_counts[notice['notice_id']]}"
        )
    for diagnostic in discovery.diagnostics:
        print(f"Commission discovery: {diagnostic}")
    print(f"Exact official logical overlaps with Wikipedia: {exact_overlaps}")
    print(
        "Wikipedia events suppressed in official waves: "
        f"{suppressed_wikipedia_events}"
    )
    print(f"Net new official events: {new_events}")
    print(
        "Historical first-round retention: "
        f"{retained_events} events across {retained_waves} waves"
    )
    rejected_event_count = rejected_fresh_events + (
        rejected_previous_events if args.previous_first_round else 0
    )
    print(
        "Poll update summary: "
        f"{discovered_waves} fresh/discovered waves; "
        f"{retained_waves} retained historical waves; "
        f"{len(rejected_keys)} rejected reviewed waves "
        f"({rejected_event_count} observations); "
        f"{official_source_enriched_waves} official-source-enriched waves; "
        f"anomaly/review status clear ({anomaly_count} conflicts)"
    )
    print(f"Final merged events: {len(events)}")
    print(
        "Commission coverage: "
        f"{coverage_counts['relevant']} relevant "
        f"({coverage_counts['parsed']} parsed, "
        f"{coverage_counts['reconciled']} reconciled, "
        f"{coverage_counts['unresolved']} unresolved)"
    )
    print(f"Wrote merged first-round events to {output}")

    if events:
        latest = events[0]
        print(
            f"Latest poll event: {latest['pollster']} | "
            f"{latest['fieldwork_start']} to {latest['fieldwork_end']} | "
            f"n={latest['sample_size']}"
        )
        print(
            "Candidates: "
            + ", ".join(
                f"{candidate['name']} {candidate['score']:g}%"
                for candidate in latest["candidates"]
            )
        )

    print(f"Skipped/ambiguous rows: {len(skipped)}")
    for reason in skipped:
        print(f"  - {reason}")

    scope_counts = second_round_audit["source_scope_counts"]
    print(f"Second-round revision: {second_round_audit['revision_id']}")
    print(f"Second-round matchup tables: {second_round_audit['table_count']}")
    print(f"Second-round genuine rows: {len(second_round_events)}")
    print(
        "Second-round current_tested rows: "
        f"{scope_counts['current_tested']}"
    )
    print(
        "Second-round source_declined_candidate_section rows: "
        f"{scope_counts['source_declined_candidate_section']}"
    )
    print(
        "Second-round comparison rows excluded: "
        f"{second_round_audit['excluded_comparison_rows']}"
    )
    print(f"Wrote second-round events to {second_round_output}")
    print(f"Closest tested runoff status: {closest_derivation['status']}")
    print(f"Wrote closest tested runoff to {closest_runoff_output}")


if __name__ == "__main__":
    main()
