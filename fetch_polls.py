"""Fetch and normalize first-round France 2027 presidential polls."""

from __future__ import annotations

import argparse
import hashlib
import json
import re
import unicodedata
from datetime import datetime
from pathlib import Path

import pandas as pd


SOURCE_URL = (
    "https://en.wikipedia.org/wiki/"
    "Opinion_polling_for_the_2027_French_presidential_election"
)
USER_AGENT = "France2027SignalLab/1.0 (contact: malatazen@gmail.com)"
FIRST_ROUND_TABLES = range(4, 8)
ROUND = "first_round"
DASHES = {"", "-", "–", "—", "−", "nan", "none"}


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
    material = ROUND + "|" + "|".join(normalize(name) for name in names)
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


def fetch_events() -> tuple[list[dict], list[str]]:
    tables = pd.read_html(
        SOURCE_URL,
        storage_options={"User-Agent": USER_AGENT},
        extract_links="body",
    )

    events_by_id: dict[str, dict] = {}
    skipped: list[str] = []

    for table_index in FIRST_ROUND_TABLES:
        frame = tables[table_index]

        if isinstance(frame.columns, pd.MultiIndex):
            headers = list(frame.columns.get_level_values(0))
        else:
            headers = list(frame.columns)

        candidate_columns: list[tuple[int, str]] = []
        for column_index, header in enumerate(headers[3:], start=3):
            name = candidate_name(header)
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

            events_by_id[event["event_id"]] = event

    # Wikipedia tables are already ordered newest first.
    events = list(events_by_id.values())
    return events, skipped


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--output", default="polls.json")
    args = parser.parse_args()

    events, skipped = fetch_events()
    output = Path(args.output)
    output.write_text(
        json.dumps(events, ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8",
    )

    print(f"Wrote {len(events)} complete first-round events to {output}")

    if events:
        latest = events[0]
        print(
            f"Latest: {latest['pollster']} | "
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
