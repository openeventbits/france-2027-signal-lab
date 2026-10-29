from __future__ import annotations

import argparse
import html
import json
import re
import sys
from pathlib import Path
from typing import Any
from poll_source_tables import load_source_tables, published_source_pages
from build_poll_explorer import directory_entries


ROOT = Path(__file__).resolve().parent
EXPLORER_PATH = ROOT / "poll_explorer.json"

HUBS = {
    "fr": ROOT / "sondages" / "index.html",
    "en": ROOT / "en" / "sondages" / "index.html",
}

START = "<!-- FR27_STATIC_POLL_LINKS_START -->"
END = "<!-- FR27_STATIC_POLL_LINKS_END -->"
SOURCE_START = "<!-- FR27_SOURCE_EVIDENCE_START -->"
SOURCE_END = "<!-- FR27_SOURCE_EVIDENCE_END -->"


class StaticPollHubError(ValueError):
    pass


def escape(value: Any) -> str:
    return html.escape(str(value), quote=True)


def load_explorer() -> dict[str, Any]:
    payload = json.loads(
        EXPLORER_PATH.read_text(encoding="utf-8")
    )

    waves = payload.get("waves")

    if not isinstance(waves, list) or not waves:
        raise StaticPollHubError(
            "poll_explorer.json contains no waves"
        )

    return payload


def format_number(value: Any, language: str) -> str:
    if value is None:
        return "—"

    number = int(value)

    if language == "fr":
        return f"{number:,}".replace(",", "\u202f")

    return f"{number:,}"


MONTHS_FR = (
    "",
    "janvier",
    "février",
    "mars",
    "avril",
    "mai",
    "juin",
    "juillet",
    "août",
    "septembre",
    "octobre",
    "novembre",
    "décembre",
)

MONTHS_EN = (
    "",
    "January",
    "February",
    "March",
    "April",
    "May",
    "June",
    "July",
    "August",
    "September",
    "October",
    "November",
    "December",
)


def iso_parts(value: str) -> tuple[int, int, int]:
    match = re.fullmatch(
        r"(\d{4})-(\d{2})-(\d{2})",
        str(value),
    )

    if not match:
        raise StaticPollHubError(
            f"invalid ISO date: {value!r}"
        )

    return tuple(int(part) for part in match.groups())


def format_date(value: str, language: str) -> str:
    year, month, day = iso_parts(value)

    if language == "fr":
        return f"{day} {MONTHS_FR[month]} {year}"

    return f"{day} {MONTHS_EN[month]} {year}"


def format_date_range(
    start: str,
    end: str,
    language: str,
) -> str:
    sy, sm, sd = iso_parts(start)
    ey, em, ed = iso_parts(end)

    if start == end:
        return format_date(start, language)

    months = MONTHS_FR if language == "fr" else MONTHS_EN

    if sy == ey and sm == em:
        return f"{sd}–{ed} {months[sm]} {sy}"

    return (
        f"{sd} {months[sm]} {sy} – "
        f"{ed} {months[em]} {ey}"
    )


def wave_path(
    wave: dict[str, Any],
    language: str,
) -> str:
    key = (
        "page_path_fr"
        if language == "fr"
        else "page_path_en"
    )

    value = wave.get(key)

    if (
        not isinstance(value, str)
        or not value.startswith("/")
    ):
        raise StaticPollHubError(
            f"wave has invalid {key}: "
            f"{wave.get('wave_id')!r}"
        )

    return value


def tested_candidate_names(
    wave: dict[str, Any],
) -> list[str]:
    names: dict[str, str] = {}

    for scenario in wave.get("scenarios", []):
        if not isinstance(scenario, dict):
            continue

        for candidate in scenario.get(
            "candidates",
            [],
        ):
            if not isinstance(candidate, dict):
                continue

            if candidate.get("identity_type") != "person":
                continue

            candidate_id = candidate.get("candidate_id")
            candidate_name = candidate.get("candidate_name")

            if (
                isinstance(candidate_id, str)
                and candidate_id
                and isinstance(candidate_name, str)
                and candidate_name
            ):
                names[candidate_id] = candidate_name

    return sorted(
        names.values(),
        key=lambda value: value.casefold(),
    )


def render_table(
    waves: list[dict[str, Any]],
    *,
    language: str,
    complete: bool,
) -> str:
    if language == "fr":
        labels = {
            "fieldwork": "TERRAIN",
            "pollster": "INSTITUT",
            "scenarios": "SCÉNARIOS",
            "sample": "ÉCHANTILLON",
            "candidates": "CANDIDATS TESTÉS",
            "open": "SONDAGE",
            "open_text": "OUVRIR →",
        }
    else:
        labels = {
            "fieldwork": "FIELDWORK",
            "pollster": "POLLSTER",
            "scenarios": "SCENARIOS",
            "sample": "SAMPLE",
            "candidates": "CANDIDATES TESTED",
            "open": "POLL",
            "open_text": "OPEN →",
        }

    rows: list[str] = []

    for wave in waves:
        source = wave.get("kind") == "reviewed_source_scenario"
        pollster = str(wave.get("pollster") or "—")
        if source:
            pollster += " / " + wave["commissioner"]
        start = str(wave.get("fieldwork_start") or "")
        end = str(wave.get("fieldwork_end") or "")
        scenario_count = wave.get("scenario_count")
        sample_size = wave.get("sample_size")

        candidates = tested_candidate_names(wave)

        candidate_text = (
            ", ".join(candidates)
            if candidates
            else "—"
        )
        if source:
            candidate_text = ", ".join(c["candidate_name"] + " " + c["result"]["literal"] for c in wave["candidates"])
        scenario_text = (("SCÉNARIO SOURCE VÉRIFIÉ" if language == "fr" else "VERIFIED SOURCE SCENARIO")
                         + " · Notice " + wave["notice_id"] if source else format_number(scenario_count, language))
        historical = sum(s.get("election_scope") == "retrospective_2022_revote" for s in wave.get("scenarios", []))
        if historical:
            plural = "s" if historical > 1 else ""
            scenario_text += (f" · {historical} scénario{plural} rétrospectif{plural} 2022" if language == "fr"
                              else f" · {historical} retrospective 2022 archive scenario{plural}")
        sample_text = (format_number(wave["respondent_bases"]["adults"], language)
                       + (" adultes" if language == "fr" else " adults") if source
                       else "n=" + format_number(sample_size, language))
        row_attributes = f' data-source-scenario-id="{escape(wave["source_scenario_id"])}"' if source else ""
        link_class = "polling-source-open-link polling-wave-open-link" if source else "polling-wave-open-link"

        href = wave_path(wave, language)

        date_text = format_date_range(
            start,
            end,
            language,
        )

        if language == "fr":
            anchor_label = (
                f"Sondage présidentiel {pollster}, "
                f"{date_text}"
            )
        else:
            anchor_label = (
                f"{pollster} presidential poll, "
                f"{date_text}"
            )

        rows.append(
            f"          <tr{row_attributes}>\n"
            f'            <td data-label="{labels["fieldwork"]}">{escape(date_text)}</td>\n'
            f'            <td data-label="{labels["pollster"]}"><strong>{escape(pollster)}</strong></td>\n'
            f'            <td data-label="{labels["scenarios"]}">{escape(scenario_text)}</td>\n'
            f'            <td data-label="{labels["sample"]}">{escape(sample_text)}</td>\n'
            f'            <td data-label="{labels["candidates"]}">{escape(candidate_text)}</td>\n'
            f'            <td data-label="{labels["open"]}">'
            f'<a class="{link_class}" '
            f'href="{escape(href)}" '
            f'aria-label="{escape(anchor_label)}">'
            f'{escape(labels["open_text"])}</a>'
            "</td>\n"
            "          </tr>"
        )

    static_class = (
        "polling-static-directory "
        + (
            "polling-static-directory-complete"
            if complete
            else "polling-static-directory-latest"
        )
    )

    return (
        f'      <div class="{static_class}" '
        'data-static-poll-directory="true">\n'
        '        <table class="polling-wave-table">\n'
        "          <thead>\n"
        "            <tr>\n"
        f'              <th scope="col">{labels["fieldwork"]}</th>\n'
        f'              <th scope="col">{labels["pollster"]}</th>\n'
        f'              <th scope="col">{labels["scenarios"]}</th>\n'
        f'              <th scope="col">{labels["sample"]}</th>\n'
        f'              <th scope="col">{labels["candidates"]}</th>\n'
        f'              <th scope="col">{labels["open"]}</th>\n'
        "            </tr>\n"
        "          </thead>\n"
        "          <tbody>\n"
        + "\n".join(rows)
        + "\n"
        "          </tbody>\n"
        "        </table>\n"
        "      </div>"
    )


def container_pattern(container_id: str) -> re.Pattern[str]:
    return re.compile(
        rf'(?P<open><div\b[^>]*\bid="{re.escape(container_id)}"[^>]*>)'
        rf'(?P<body>.*?)'
        rf'(?P<close></div>)',
        flags=re.IGNORECASE | re.DOTALL,
    )


def replace_container(
    document: str,
    *,
    container_id: str,
    content: str,
) -> str:
    pattern = container_pattern(container_id)

    matches = list(pattern.finditer(document))

    if len(matches) != 1:
        raise StaticPollHubError(
            f"{container_id}: expected exactly one container, "
            f"found {len(matches)}"
        )

    match = matches[0]

    replacement = (
        match.group("open")
        + "\n"
        + START
        + "\n"
        + content
        + "\n"
        + END
        + "\n"
        + match.group("close")
    )

    return (
        document[: match.start()]
        + replacement
        + document[match.end() :]
    )


def render_hub(
    original: str,
    *,
    waves: list[dict[str, Any]],
    language: str,
) -> str:
    entries = directory_entries(waves)
    latest = entries[:10]

    document = replace_container(
        original,
        container_id="latest-wave-directory",
        content=render_table(
            latest,
            language=language,
            complete=False,
        ),
    )

    document = replace_container(
        document,
        container_id="polling-browse-panel",
        content=render_table(
            entries,
            language=language,
            complete=True,
        ),
    )

    return document


def render_source_links(language, waves=None):
    fr = language == "fr"
    record = load_source_tables()
    links = []
    for page in published_source_pages():
        table = record["tables"][page["notice_id"]]["table"]
        date_label = (format_date(table["publication_date"], language) if table.get("publication_date")
                      else ("Terrain : " if fr else "Fieldwork: ") + format_date_range(table["fieldwork_start"], table["fieldwork_end"], language))
        label = f'{table["institute"]} / {table["commissioner"]} · {date_label} · notice {page["notice_id"]}'
        links.append(f'<li><a href="{escape(page[f"page_path_{language}"])}">{escape(label)} →</a></li>')
    return (SOURCE_START + '\n<section class="polling-panel" id="source-evidence" aria-labelledby="source-evidence-title">'
            '<div class="polling-panel-head"><div><div class="polling-eyebrow">'
            + ("DOCUMENTS SOURCES" if fr else "SOURCE DOCUMENTS") + '</div><h2 id="source-evidence-title">'
            + ("TABLEAUX PUBLIÉS · PREMIER TOUR" if fr else "PUBLISHED FIRST-ROUND TABLES")
            + '</h2></div></div><div class="polling-inspector-empty"><p>'
            + ("Preuves documentaires avec valeurs littérales, dont &lt;1%. Ces tableaux ne sont pas des vagues numériques et ne participent pas aux tendances du Polling Lab."
               if fr else "Documentary evidence with literal values, including &lt;1%. These tables are not numerical waves and do not enter Polling Lab trends.")
            + '</p><ul>' + ''.join(links) + '</ul></div></section>\n'
            + render_historical_archive(language, waves) + '\n' + SOURCE_END)


def render_historical_archive(language, waves=None):
    """A crawlable, keyboard-accessible archive of exact original scenarios."""
    waves = load_explorer()["waves"] if waves is None else waves
    fr = language == "fr"
    links = []
    for wave in waves:
        for index, scenario in enumerate(wave["scenarios"], 1):
            if scenario.get("election_scope") != "retrospective_2022_revote":
                continue
            label = f'{wave["pollster"]} · {format_date_range(wave["fieldwork_start"], wave["fieldwork_end"], language)} · ' + ("scénario" if fr else "scenario") + f' {index}'
            href = wave_path(wave, language) + f'#scenario-{index}'
            links.append(f'<li data-event-id="{escape(scenario["event_id"])}"><a href="{escape(href)}">{escape(label)} →</a></li>')
    total = sum(len(w["scenarios"]) for w in waves)
    explanation = (f"{len(links)} scénarios rétrospectifs 2022 confirmés par leurs sources, exclus des comparaisons et historiques de candidats de la vue 2027. Le corpus conserve {total} scénarios ; la vue 2027 en affiche {total - len(links)}. Tous les autres scénarios ne sont pas vérifiés individuellement. Les résultats originaux et les références restent accessibles ci-dessous."
                   if fr else f"{len(links)} source-confirmed retrospective 2022 scenarios, excluded from 2027 comparisons and candidate histories. The corpus retains {total} scenarios; the 2027 view displays {total - len(links)}. The other scenarios have not all been individually verified. Original results and evidence remain accessible below.")
    title = "ARCHIVES RÉTROSPECTIVES 2022" if fr else "2022 RETROSPECTIVE ARCHIVE"
    return ('<section class="polling-panel" id="historical-archive" aria-labelledby="historical-archive-title">'
            f'<div class="polling-panel-head"><h2 id="historical-archive-title">{title}</h2></div>'
            f'<div class="polling-inspector-empty"><p>{explanation}</p><ul>{"".join(links)}</ul></div></section>')


def normalized_template(document: str) -> str:
    pattern = re.compile(
        re.escape(START)
        + r".*?"
        + re.escape(END),
        flags=re.DOTALL,
    )

    document = re.sub(re.escape(SOURCE_START) + r".*?" + re.escape(SOURCE_END) + r"\s*",
                      "", document, flags=re.DOTALL)
    return pattern.sub("", document)


def expected_document(
    path: Path,
    *,
    waves: list[dict[str, Any]],
    language: str,
) -> str:
    current = path.read_text(encoding="utf-8")

    template = normalized_template(current)

    # Remove whitespace left behind from a previous generated block,
    # while preserving the surrounding container.
    template = re.sub(
        r'(<div\b[^>]*\bid="latest-wave-directory"[^>]*>)'
        r'\s*'
        r'(</div>)',
        r"\1\2",
        template,
        flags=re.IGNORECASE | re.DOTALL,
    )

    template = re.sub(
        r'(<div\b[^>]*\bid="polling-browse-panel"[^>]*>)'
        r'\s*'
        r'(</div>)',
        r"\1\2",
        template,
        flags=re.IGNORECASE | re.DOTALL,
    )

    document = render_hub(
        template,
        waves=waves,
        language=language,
    )
    marker = '<footer id="candidate-app-hud"'
    if document.count(marker) != 1:
        raise StaticPollHubError("Expected exactly one shared hub footer")
    return document.replace(marker, render_source_links(language, waves) + '\n\n    ' + marker, 1)


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        description=(
            "Pre-render crawlable poll-wave links "
            "inside the FR27 Polling Lab hubs."
        )
    )

    parser.add_argument(
        "--check",
        action="store_true",
    )

    args = parser.parse_args(argv)

    try:
        explorer = load_explorer()
        waves = explorer["waves"]

        # Explorer is already newest-first by contract.
        if args.check:
            errors: list[str] = []

            for language, path in HUBS.items():
                actual = path.read_text(
                    encoding="utf-8"
                )

                expected = expected_document(
                    path,
                    waves=waves,
                    language=language,
                )

                if actual != expected:
                    errors.append(
                        f"out of date: "
                        f"{path.relative_to(ROOT).as_posix()}"
                    )

            if errors:
                for error in errors:
                    print(
                        f"poll hub static links check: "
                        f"{error}"
                    )

                return 1

            print(
                "poll hub static links check clean: "
                f"{len(waves)} waves, "
                "2 bilingual hubs"
            )

            return 0

        for language, path in HUBS.items():
            expected = expected_document(
                path,
                waves=waves,
                language=language,
            )

            path.write_text(
                expected,
                encoding="utf-8",
                newline="\n",
            )

        print(
            "built poll hub static links: "
            f"{len(waves)} waves, "
            "10 latest links + complete index "
            "in both languages"
        )

        return 0

    except (
        OSError,
        json.JSONDecodeError,
        StaticPollHubError,
    ) as error:
        print(
            f"poll hub static links error: {error}",
            file=sys.stderr,
        )

        return 1


if __name__ == "__main__":
    raise SystemExit(main())
