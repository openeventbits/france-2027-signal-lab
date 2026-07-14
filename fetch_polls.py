"""Fetch and normalize first-round France 2027 presidential polls."""

from __future__ import annotations

import argparse
import hashlib
import io
import json
import re
import unicodedata
from datetime import datetime
from pathlib import Path
from urllib.request import Request, urlopen

import pandas as pd
from pypdf import PdfReader


SOURCE_URL = (
    "https://en.wikipedia.org/wiki/"
    "Opinion_polling_for_the_2027_French_presidential_election"
)
USER_AGENT = "France2027SignalLab/1.0 (contact: malatazen@gmail.com)"
FIRST_ROUND_TABLES = range(4, 8)
ROUND = "first_round"
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


def make_scenario_key(names: list[str]) -> str:
    normalized_names = sorted(normalize(name) for name in names)
    material = ROUND + "|" + "|".join(normalized_names)
    return hashlib.sha256(material.encode("utf-8")).hexdigest()


def make_event_id(
    pollster: str,
    fieldwork_start: str,
    fieldwork_end: str,
    hypothesis: str,
    source_url: str,
) -> str:
    material = (
        normalize(pollster)
        + fieldwork_start
        + fieldwork_end
        + ROUND
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
    args = parser.parse_args()

    wikipedia_events, skipped = fetch_wikipedia_events()
    official_events, official_counts = fetch_official_events()
    events, exact_overlaps, suppressed_wikipedia_events, new_events = merge_events(
        wikipedia_events, official_events
    )
    validate_merged_official_waves(events)
    output = Path(args.output)
    output.write_text(
        json.dumps(events, ensure_ascii=False, indent=2) + "\n",
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


if __name__ == "__main__":
    main()
