from __future__ import annotations

import argparse
import html
import json
import re
import sys
from pathlib import Path
from typing import Any


ROOT = Path(__file__).resolve().parent
EXPLORER_PATH = ROOT / "poll_explorer.json"

HUBS = {
    "fr": ROOT / "sondages" / "index.html",
    "en": ROOT / "en" / "sondages" / "index.html",
}

START = "<!-- FR27_STATIC_POLL_LINKS_START -->"
END = "<!-- FR27_STATIC_POLL_LINKS_END -->"


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
        pollster = str(wave.get("pollster") or "—")
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
            "          <tr>\n"
            f"            <td>{escape(date_text)}</td>\n"
            f"            <td><strong>{escape(pollster)}</strong></td>\n"
            f"            <td>{escape(format_number(scenario_count, language))}</td>\n"
            f"            <td>n={escape(format_number(sample_size, language))}</td>\n"
            f"            <td>{escape(candidate_text)}</td>\n"
            "            <td>"
            f'<a class="polling-wave-open-link" '
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
    latest = waves[:10]

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
            waves,
            language=language,
            complete=True,
        ),
    )

    return document


def normalized_template(document: str) -> str:
    pattern = re.compile(
        re.escape(START)
        + r".*?"
        + re.escape(END),
        flags=re.DOTALL,
    )

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

    return render_hub(
        template,
        waves=waves,
        language=language,
    )


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
