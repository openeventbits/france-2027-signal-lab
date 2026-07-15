"""Fetch and normalize first-round France 2027 presidential polls."""

from __future__ import annotations

import argparse
import hashlib
import io
import json
import math
import re
import unicodedata
from datetime import datetime, timezone
from pathlib import Path
from urllib.parse import urlencode, urljoin, urlparse
from urllib.request import Request, urlopen

import pandas as pd
from lxml import html as lxml_html
from pypdf import PdfReader


SOURCE_URL = (
    "https://en.wikipedia.org/wiki/"
    "Opinion_polling_for_the_2027_French_presidential_election"
)
USER_AGENT = "France2027SignalLab/1.0 (contact: malatazen@gmail.com)"
MEDIAWIKI_API_URL = "https://en.wikipedia.org/w/api.php"
SOURCE_PAGE = "Opinion_polling_for_the_2027_French_presidential_election"
WIKIPEDIA_LICENSE = "CC BY-SA 4.0"
FIRST_ROUND_TABLES = range(4, 8)
ROUND = "first_round"
SECOND_ROUND = "second_round"
DASHES = {"", "-", "–", "—", "−", "nan", "none"}
OFFICIAL_NOTICES = {
    "Elabe": {
        "url": "https://www.commission-des-sondages.fr/notices/medias/fichiers/add/2166",
        "commissioner": "BFMTV; La Tribune Dimanche",
        "publication_date": "2026-03-28",
        "fieldwork_start": "2026-03-25",
        "fieldwork_end": "2026-03-27",
        "sample_size": 1504,
        "expected_events": 6,
    },
    "Ipsos": {
        "url": "https://www.commission-des-sondages.fr/notices/medias/fichiers/add/2197",
        "commissioner": "Le Parisien",
        "publication_date": "2026-06-01",
        "fieldwork_start": "2026-05-27",
        "fieldwork_end": "2026-05-28",
        "sample_size": 1500,
        "expected_events": 8,
    },
    "Ifop": {
        "url": "https://www.commission-des-sondages.fr/notices/medias/fichiers/add/2216",
        "commissioner": "LCI; Le Figaro; Sud Radio",
        "publication_date": "2026-06-25",
        "fieldwork_start": "2026-06-22",
        "fieldwork_end": "2026-06-24",
        "sample_size": 1415,
        "expected_events": 8,
    },
}

CANONICAL_CANDIDATES = (
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


def normalize(value: str) -> str:
    """Normalize text for deterministic hashes."""
    value = unicodedata.normalize("NFKD", value)
    value = "".join(ch for ch in value if not unicodedata.combining(ch))
    value = value.casefold()
    return " ".join(re.sub(r"[^a-z0-9]+", " ", value).split())


CANDIDATE_ALIASES = {
    normalize(name): name for name in CANONICAL_CANDIDATES
}
CANDIDATE_ALIASES.update(
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


def canonical_candidate_name(value: str, *, strict: bool = False) -> str:
    """Return a known display name, failing on unknown official candidates."""
    name = re.sub(r"\s+", " ", value).strip()
    canonical = CANDIDATE_ALIASES.get(normalize(name))
    if canonical:
        return canonical
    if strict:
        raise ValueError(f"unknown official candidate name: {value!r}")
    return name


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


def make_scenario_key(
    names: list[str], *, round_name: str = ROUND
) -> str:
    normalized_names = sorted(normalize(name) for name in names)
    material = round_name + "|" + "|".join(normalized_names)
    return hashlib.sha256(material.encode("utf-8")).hexdigest()


def make_event_id(
    pollster: str,
    fieldwork_start: str,
    fieldwork_end: str,
    hypothesis: str,
    source_url: str,
    *,
    round_name: str = ROUND,
) -> str:
    material = (
        normalize(pollster)
        + fieldwork_start
        + fieldwork_end
        + round_name
        + normalize(hypothesis)
        + source_url
    )
    return hashlib.sha256(material.encode("utf-8")).hexdigest()


def logical_key(event: dict) -> tuple[str, str, str, str]:
    return (
        normalize(event["pollster"]),
        event["fieldwork_start"],
        event["fieldwork_end"],
        event["scenario_key"],
    )


def poll_wave_key(event: dict) -> tuple[str, str, str]:
    return (
        normalize(event["pollster"]),
        event["fieldwork_start"],
        event["fieldwork_end"],
    )


def fetch_wikipedia_events() -> tuple[list[dict], list[str]]:
    tables = pd.read_html(
        SOURCE_URL,
        storage_options={"User-Agent": USER_AGENT},
        extract_links="body",
    )

    events: list[dict] = []
    skipped: list[str] = []

    for table_index in FIRST_ROUND_TABLES:
        frame = tables[table_index]

        if isinstance(frame.columns, pd.MultiIndex):
            headers = list(frame.columns.get_level_values(0))
        else:
            headers = list(frame.columns)

        candidate_columns: list[tuple[int, str]] = []
        for column_index, header in enumerate(headers[3:], start=3):
            name = canonical_candidate_name(candidate_name(header))
            if not name or name.startswith("Unnamed:"):
                continue
            candidate_columns.append((column_index, name))

        for row_index, row in frame.iterrows():
            pollster = cell_text(row.iloc[0])
            fieldwork_raw = cell_text(row.iloc[1])

            if not pollster or normalize(pollster) in {"2022 election", "election"}:
                continue

            try:
                fieldwork_start, fieldwork_end = parse_fieldwork(fieldwork_raw)
            except ValueError:
                skipped.append(
                    f"table {table_index} row {row_index}: "
                    f"unparsed fieldwork date {fieldwork_raw!r}"
                )
                continue

            candidates: list[dict] = []
            ambiguous_reason: str | None = None

            for column_index, name in candidate_columns:
                raw_score = cell_text(row.iloc[column_index])

                try:
                    score = parse_score(raw_score)
                except ValueError as exc:
                    ambiguous_reason = f"{name}: {exc}"
                    break

                if score is not None:
                    candidates.append({"name": name, "score": score})

            if ambiguous_reason:
                skipped.append(
                    f"{pollster} {fieldwork_raw} row {row_index}: "
                    f"{ambiguous_reason}; event skipped"
                )
                continue

            if len(candidates) < 2:
                continue

            source_url = cell_link(row.iloc[0]) or SOURCE_URL
            names = [candidate["name"] for candidate in candidates]
            hypothesis = "First round — " + ", ".join(names)

            event = {
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
                "sample_size": parse_sample_size(cell_text(row.iloc[2])),
                "round": ROUND,
                "hypothesis": hypothesis,
                "scenario_key": make_scenario_key(names),
                "source_url": source_url,
                "candidates": candidates,
            }

            events.append(event)

    # Wikipedia tables are already ordered newest first.
    return events, skipped


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
    """Resolve a full name or unique surname-style label to a candidate."""
    raw_name = candidate_name(value)
    direct = CANDIDATE_ALIASES.get(normalize(raw_name))
    if direct:
        return direct

    short = normalize(raw_name)
    matches = [
        name
        for name in CANONICAL_CANDIDATES
        if normalize(name) == short or normalize(name).endswith(f" {short}")
    ]
    if len(matches) != 1:
        raise ValueError(
            f"matchup candidate is not uniquely canonical: {value!r}"
        )
    return matches[0]


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


def fetch_pdf(url: str) -> PdfReader:
    request = Request(url, headers={"User-Agent": USER_AGENT})
    with urlopen(request, timeout=60) as response:
        data = response.read()
    if not data.startswith(b"%PDF"):
        raise ValueError(f"configured notice did not return a PDF: {url}")
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


def make_official_event(institute: str, candidates: list[dict]) -> dict:
    notice = OFFICIAL_NOTICES[institute]
    names = [candidate["name"] for candidate in candidates]
    hypothesis = "First round — " + ", ".join(names)
    source_url = notice["url"]
    return {
        "event_id": make_event_id(
            institute,
            notice["fieldwork_start"],
            notice["fieldwork_end"],
            hypothesis,
            source_url,
        ),
        "pollster": institute,
        "commissioner": notice["commissioner"],
        "publication_date": notice["publication_date"],
        "fieldwork_start": notice["fieldwork_start"],
        "fieldwork_end": notice["fieldwork_end"],
        "sample_size": notice["sample_size"],
        "round": ROUND,
        "hypothesis": hypothesis,
        "scenario_key": make_scenario_key(names),
        "source_url": source_url,
        "candidates": candidates,
    }


def parse_elabe(reader: PdfReader) -> list[dict]:
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
    return [make_official_event("Elabe", candidates) for candidates in blocks]


def parse_ipsos(reader: PdfReader) -> list[dict]:
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
            CANDIDATE_ALIASES[normalize(line)]
            for line in lines
            if normalize(line) in CANDIDATE_ALIASES
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
        events.append(make_official_event("Ipsos", candidates))
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


def parse_ifop(reader: PdfReader) -> list[dict]:
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
        events.append(make_official_event("Ifop", candidates))
    return events


def validate_official_events(institute: str, events: list[dict]) -> None:
    expected = OFFICIAL_NOTICES[institute]["expected_events"]
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


def fetch_official_events() -> tuple[list[dict], dict[str, int]]:
    parsers = {
        "Elabe": parse_elabe,
        "Ipsos": parse_ipsos,
        "Ifop": parse_ifop,
    }
    all_events: list[dict] = []
    counts: dict[str, int] = {}
    for institute, parser in parsers.items():
        events = parser(fetch_pdf(OFFICIAL_NOTICES[institute]["url"]))
        validate_official_events(institute, events)
        counts[institute] = len(events)
        all_events.extend(events)

    keys = [logical_key(event) for event in all_events]
    if len(keys) != len(set(keys)):
        raise ValueError("official notices contain duplicate logical poll identities")
    return all_events, counts


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


def validate_merged_official_waves(events: list[dict]) -> None:
    for institute, notice in OFFICIAL_NOTICES.items():
        expected_wave = (
            normalize(institute),
            notice["fieldwork_start"],
            notice["fieldwork_end"],
        )
        wave_events = [
            event for event in events if poll_wave_key(event) == expected_wave
        ]
        expected_count = notice["expected_events"]
        if len(wave_events) != expected_count:
            raise ValueError(
                f"{institute} official wave: expected {expected_count} merged "
                f"events, found {len(wave_events)}"
            )
        unexpected_sources = [
            event["source_url"]
            for event in wave_events
            if event["source_url"] != notice["url"]
        ]
        if unexpected_sources:
            raise ValueError(
                f"{institute} official wave contains non-notice sources: "
                f"{sorted(set(unexpected_sources))}"
            )


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--output", default="polls.json")
    parser.add_argument(
        "--second-round-output", default="second_round_polls.json"
    )
    parser.add_argument(
        "--closest-runoff-output", default="closest_tested_runoff.json"
    )
    args = parser.parse_args()

    wikipedia_events, skipped = fetch_wikipedia_events()
    official_events, official_counts = fetch_official_events()
    events, exact_overlaps, suppressed_wikipedia_events, new_events = merge_events(
        wikipedia_events, official_events
    )
    validate_merged_official_waves(events)
    second_round_events, second_round_audit = fetch_second_round_events()
    closest_derivation = derive_closest_tested_runoff(second_round_events)

    generated_at = datetime.now(timezone.utc).isoformat().replace("+00:00", "Z")
    source_metadata = {
        "page_url": SOURCE_URL,
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
    output.write_text(
        json.dumps(events, ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8",
    )
    second_round_output.write_text(
        json.dumps(second_round_output_data, ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8",
    )
    closest_runoff_output.write_text(
        json.dumps(closest_output_data, ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8",
    )

    print(f"Wikipedia events: {len(wikipedia_events)}")
    for institute in OFFICIAL_NOTICES:
        print(f"Official {institute} events: {official_counts[institute]}")
    print(f"Exact official logical overlaps with Wikipedia: {exact_overlaps}")
    print(
        "Wikipedia events suppressed in official waves: "
        f"{suppressed_wikipedia_events}"
    )
    print(f"Net new official events: {new_events}")
    print(f"Final merged events: {len(events)}")
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
