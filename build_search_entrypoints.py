"""Build deterministic localized search entrypoints for FR27."""

from __future__ import annotations

import argparse
import html
import json
import os
import tempfile
from datetime import date
from pathlib import Path
from typing import Any

from build_candidate_signals import (
    CandidateSignalsError,
    validate_candidate_signals,
)
from generate_recent_changes import LedgerError, validate_recent_changes


ROOT = Path(__file__).resolve().parent
SOURCE = ROOT / "index.html"
ENGLISH_OUTPUT = ROOT / "en" / "index.html"
CANDIDATE_SIGNALS = ROOT / "candidate_signals.json"
RECENT_CHANGES = ROOT / "recent_changes.json"

ENGLISH_TITLE = (
    "France 2027 Signal Lab — Source-Linked Election Signals"
)
ENGLISH_DESCRIPTION = (
    "Source-linked polling, election news, candidate coverage and fact checks "
    "for France's 2027 presidential race. No averages, no forecast, no voting advice."
)

WHAT_CHANGED_START = "<!-- FR27 SEMANTIC SNAPSHOT: WHAT CHANGED START -->"
WHAT_CHANGED_END = "<!-- FR27 SEMANTIC SNAPSHOT: WHAT CHANGED END -->"
RACE_START = "<!-- FR27 SEMANTIC SNAPSHOT: RACE AT A GLANCE START -->"
RACE_END = "<!-- FR27 SEMANTIC SNAPSHOT: RACE AT A GLANCE END -->"
MAX_RECENT_CHANGES = 3

COPY = {
    "fr": {
        "what_changed": "CE QUI A CHANGÉ",
        "changes": "CHANGEMENTS",
        "change": "CHANGEMENT",
        "window": "14 DERNIERS JOURS",
        "empty": "Aucun changement qualifié dans les 14 derniers jours.",
        "chronological": "Changements sourcés par ordre chronologique",
        "open_source": "Ouvrir la source ↗",
        "supporting_one": "+1 source concordante",
        "supporting_many": "+{count} sources concordantes",
        "race": "RAPPORT DE FORCE",
        "methodology": (
            "Éléments reliés à leurs sources · aucune moyenne de sondages · "
            "aucune prévision · aucun conseil de vote"
        ),
        "fieldwork": "Terrain",
        "sample": "Échantillon",
        "not_stated": "non indiqué",
        "hypothesis_one": "1 hypothèse publiée",
        "hypothesis_many": "{count} hypothèses publiées",
        "scenario": "HYPOTHÈSE",
        "selected_hypothesis": "Hypothèse sélectionnée",
        "candidate": "CANDIDAT",
        "reported_score": "SCORE PUBLIÉ",
        "result": "RÉSULTAT",
        "poll_source": "Voir la source du sondage ↗",
        "poll_source_number": "Voir la source {number} du sondage ↗",
        "reported_scores": "Scores publiés pour l’hypothèse sélectionnée",
    },
    "en": {
        "what_changed": "WHAT CHANGED",
        "changes": "CHANGES",
        "change": "CHANGE",
        "window": "LAST 14 DAYS",
        "empty": "No qualifying change in the last 14 days.",
        "chronological": "Chronological source-linked changes",
        "open_source": "Open source ↗",
        "supporting_one": "+1 supporting source",
        "supporting_many": "+{count} supporting sources",
        "race": "RACE AT A GLANCE",
        "methodology": (
            "Source-linked evidence · no polling average · no forecast · "
            "no voting advice"
        ),
        "fieldwork": "Fieldwork",
        "sample": "Sample",
        "not_stated": "not stated",
        "hypothesis_one": "1 published hypothesis",
        "hypothesis_many": "{count} published hypotheses",
        "scenario": "SCENARIO",
        "selected_hypothesis": "Selected hypothesis",
        "candidate": "CANDIDATE",
        "reported_score": "REPORTED SCORE",
        "result": "RESULT",
        "poll_source": "View poll source ↗",
        "poll_source_number": "View poll source {number} ↗",
        "reported_scores": "Reported scores for the selected hypothesis",
    },
}

CATEGORY_LABELS = {
    "fr": {
        "campaign": "CAMPAGNE",
        "polling": "SONDAGE",
        "runoff": "SECOND TOUR",
        "fact_check": "VÉRIFICATION",
        "legal": "JURIDIQUE",
    },
    "en": {
        "campaign": "CAMPAIGN",
        "polling": "POLLING",
        "runoff": "RUNOFF",
        "fact_check": "FACT CHECK",
        "legal": "LEGAL",
    },
}

DATE_KIND_LABELS = {
    "fr": {
        "source_published": "Publié",
        "official_event": "Événement officiel",
        "first_seen": "Première observation",
        "fieldwork_ended": "Fin du terrain",
        "review_published": "Vérification publiée",
        "ruling_or_decision": "Décision",
    },
    "en": {
        "source_published": "Published",
        "official_event": "Official event",
        "first_seen": "First seen",
        "fieldwork_ended": "Fieldwork ended",
        "review_published": "Review published",
        "ruling_or_decision": "Ruling / decision",
    },
}

MONTHS = {
    "fr": (
        "janv.", "févr.", "mars", "avr.", "mai", "juin",
        "juil.", "août", "sept.", "oct.", "nov.", "déc.",
    ),
    "en": (
        "Jan", "Feb", "Mar", "Apr", "May", "Jun",
        "Jul", "Aug", "Sep", "Oct", "Nov", "Dec",
    ),
}


class SearchEntrypointError(RuntimeError):
    """Raised when semantic entrypoints cannot be built safely."""


def replace_once(text: str, old: str, new: str, label: str) -> str:
    count = text.count(old)
    if count != 1:
        raise SearchEntrypointError(
            f"{label}: expected exactly 1 source occurrence, found {count}"
        )
    return text.replace(old, new, 1)


def _escape(value: Any) -> str:
    return html.escape(str(value), quote=True)


def _load_json(path: Path) -> Any:
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except (OSError, UnicodeDecodeError, json.JSONDecodeError) as error:
        raise SearchEntrypointError(f"could not read {path}: {error}") from error


def _format_date(value: str, language: str) -> str:
    try:
        parsed = date.fromisoformat(value[:10])
    except (TypeError, ValueError) as error:
        raise SearchEntrypointError(f"invalid semantic date: {value!r}") from error
    month = MONTHS[language][parsed.month - 1]
    return f"{parsed.day} {month} {parsed.year}"


def _format_number(value: int | float) -> str:
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        raise SearchEntrypointError("semantic numeric value must be a number")
    return format(value, "g")


def _format_sample(value: int | None, language: str) -> str:
    if value is None:
        return COPY[language]["not_stated"]
    if not isinstance(value, int) or isinstance(value, bool) or value <= 0:
        raise SearchEntrypointError("featured poll sample size is invalid")
    separator = "\u202f" if language == "fr" else ","
    return f"{value:,}".replace(",", separator)


def construct_semantic_model(
    candidate_signals: Any,
    recent_changes: Any,
) -> dict[str, Any]:
    """Validate authoritative artifacts and project only approved V1 fields."""

    try:
        validate_candidate_signals(candidate_signals)
        validate_recent_changes(recent_changes)
    except (CandidateSignalsError, LedgerError) as error:
        raise SearchEntrypointError(
            f"semantic snapshot input is invalid: {error}"
        ) from error

    board = candidate_signals["featured_poll_board"]
    changes = recent_changes["items"][:MAX_RECENT_CHANGES]
    return {
        "race": {
            "pollster": board["pollster"],
            "fieldwork_start": board["fieldwork_start"],
            "fieldwork_end": board["fieldwork_end"],
            "sample_size": board["sample_size"],
            "package_hypothesis_count": board["package_hypothesis_count"],
            "hypothesis_label": board["hypothesis_label"],
            "selected_event_id": board["selected_event_id"],
            "scenario_key": board["scenario_key"],
            "source_urls": list(board["source_urls"]),
            "displayed_candidate_count": board["displayed_candidate_count"],
            "omitted_candidate_count": board["omitted_candidate_count"],
            "candidates": [dict(candidate) for candidate in board["candidates"]],
        },
        "changes": {
            "window": dict(recent_changes["window"]),
            "count": recent_changes["counts"]["total"],
            "items": [dict(item) for item in changes],
        },
    }


def load_semantic_model(
    candidate_signals_path: Path = CANDIDATE_SIGNALS,
    recent_changes_path: Path = RECENT_CHANGES,
) -> dict[str, Any]:
    return construct_semantic_model(
        _load_json(candidate_signals_path),
        _load_json(recent_changes_path),
    )


def _render_change_item(item: dict[str, Any], language: str) -> str:
    source = item["primary_source"]
    supporting_count = item["supporting_source_count"]
    supporting = ""
    if supporting_count == 1:
        supporting = " · " + COPY[language]["supporting_one"]
    elif supporting_count > 1:
        supporting = " · " + COPY[language]["supporting_many"].format(
            count=supporting_count
        )
    trusted_at = item["trusted_change_at"]
    trusted_label = DATE_KIND_LABELS[language][
        item["trusted_change_date_kind"]
    ]
    category = CATEGORY_LABELS[language][item["category"]]
    return f'''          <li class="changes-ledger-entry" data-category="{_escape(item["category"])}" data-fr27-change-id="{_escape(item["id"])}">
            <time class="changes-ledger-time" datetime="{_escape(trusted_at)}">{_escape(_format_date(trusted_at, language))}</time>
            <span class="changes-ledger-beacon" aria-hidden="true"><svg viewBox="0 0 24 24" focusable="false"><circle class="changes-ledger-shape" cx="12" cy="12" r="8"></circle><circle class="changes-ledger-fill" cx="12" cy="12" r="2.5"></circle></svg></span>
            <div class="changes-ledger-copy">
              <div class="changes-ledger-category">{_escape(category)}</div>
              <h3 class="changes-ledger-headline">{_escape(item["headline"])}</h3>
              <div class="changes-ledger-meta">
                <span class="changes-ledger-meta-text">{_escape(trusted_label)} · {_escape(source["name"])}{_escape(supporting)}</span>
                <a class="changes-ledger-source" href="{_escape(source["url"])}" target="_blank" rel="noopener noreferrer">{_escape(COPY[language]["open_source"])}</a>
              </div>
            </div>
            <div class="changes-ledger-visual" aria-hidden="true"><span class="changes-ledger-wordmark">{_escape(source["name"])}</span></div>
          </li>'''


def render_what_changed(model: dict[str, Any], language: str) -> str:
    copy = COPY[language]
    changes = model["changes"]
    count = changes["count"]
    count_label = copy["change"] if count == 1 else copy["changes"]
    items = changes["items"]
    if items:
        content = (
            f'        <ol class="semantic-snapshot-list" aria-label="{_escape(copy["chronological"])}">\n'
            + "\n".join(_render_change_item(item, language) for item in items)
            + "\n        </ol>"
        )
    else:
        content = f'        <p class="changes-ledger-empty">{_escape(copy["empty"])}</p>'
    return f'''      <div class="panel-head">
        <h2 id="what-changed-title" data-i18n="dashboard.what_changed">{_escape(copy["what_changed"])}</h2>
        <div class="changes-ledger-summary" id="changes-ledger-summary" aria-live="polite">{count} {_escape(count_label)} · {_escape(copy["window"])}</div>
      </div>
      <div class="what-changed-list" id="what-changed-list" aria-live="polite" aria-busy="false" data-fr27-semantic-snapshot="true">
        <div class="changes-ledger-scroll" tabindex="0">
{content}
        </div>
      </div>'''


def _render_candidate(candidate: dict[str, Any]) -> str:
    score = _format_number(candidate["reported_score"])
    return f'''              <li class="bar-row" data-fr27-candidate-id="{_escape(candidate["candidate_id"])}">
                <div class="race-candidate"><div class="candidate">{_escape(candidate["candidate_name"])}</div></div>
                <div class="track" aria-hidden="true"><div class="fill" style="width:{_escape(score)}%"></div></div>
                <data class="score" value="{_escape(score)}">{_escape(score)}%</data>
              </li>'''


def render_race(model: dict[str, Any], language: str) -> str:
    copy = COPY[language]
    race = model["race"]
    hypothesis_count = race["package_hypothesis_count"]
    hypothesis_text = (
        copy["hypothesis_one"]
        if hypothesis_count == 1
        else copy["hypothesis_many"].format(count=hypothesis_count)
    )
    hypothesis_label = race["hypothesis_label"] or copy["selected_hypothesis"]
    candidates = "\n".join(
        _render_candidate(candidate) for candidate in race["candidates"]
    )
    source_links = []
    for index, url in enumerate(race["source_urls"], start=1):
        label = (
            copy["poll_source"]
            if len(race["source_urls"]) == 1
            else copy["poll_source_number"].format(number=index)
        )
        identifier = ' id="race-source"' if index == 1 else ""
        extra = (
            ""
            if index == 1
            else ' data-fr27-semantic-race-source="extra"'
        )
        source_links.append(
            f'        <a{identifier}{extra} class="media-pulse-dashboard-cta" href="{_escape(url)}" target="_blank" rel="noopener noreferrer">{_escape(label)}</a>'
        )
    return f'''      <div class="panel-head race-glance-head">
        <div class="race-heading">
          <h2 id="race-glance-title" data-i18n="dashboard.race_at_a_glance">{_escape(copy["race"])}</h2>
        </div>
        <div class="race-poll-tabs" id="race-poll-tabs" role="tablist" aria-label="{_escape(copy["reported_scores"])}" aria-busy="false"></div>
      </div>
      <div class="race-poll-panel is-no-comparison" id="race-poll-panel" role="tabpanel" tabindex="0" data-fr27-semantic-snapshot="true" data-selected-event-id="{_escape(race["selected_event_id"])}" data-scenario-key="{_escape(race["scenario_key"])}">
        <div class="race-event-controls">
          <div class="race-event" aria-live="polite">
            <div class="race-event-title" id="latest-title">{_escape(race["pollster"])} · {_escape(copy["fieldwork"])} <time datetime="{_escape(race["fieldwork_start"])}">{_escape(_format_date(race["fieldwork_start"], language))}</time>–<time datetime="{_escape(race["fieldwork_end"])}">{_escape(_format_date(race["fieldwork_end"], language))}</time></div>
            <div class="race-event-detail" id="latest-sub">{_escape(copy["sample"])} <data value="{_escape(race["sample_size"] if race["sample_size"] is not None else "")}">{_escape(_format_sample(race["sample_size"], language))}</data> · {_escape(hypothesis_text)}</div>
          </div>
          <div class="race-scenario-control">
            <label class="hypothesis-label" for="hypothesis-select">{_escape(copy["scenario"])}</label>
            <select id="hypothesis-select" hidden disabled aria-disabled="true"></select>
            <div class="race-scenario-static" id="race-scenario-static">{_escape(copy["selected_hypothesis"])} · {_escape(hypothesis_label)}</div>
          </div>
        </div>
        <div class="race-scroll-shell">
          <div class="bars" id="bars" aria-live="polite" aria-label="{_escape(copy["reported_scores"])}" tabindex="0">
            <div class="race-column-head" aria-hidden="true"><span>{_escape(copy["candidate"])}</span><span>{_escape(copy["reported_score"])}</span><span class="race-column-head-result">{_escape(copy["result"])}</span></div>
            <ol class="semantic-snapshot-list" aria-label="{_escape(copy["reported_scores"])}">
{candidates}
            </ol>
          </div>
          <div class="race-scroll-fade" id="race-scroll-fade" aria-hidden="true" hidden></div>
        </div>
        <div id="race-more" hidden></div>
        <div id="meta" hidden></div>
        <div class="race-footer">
{"\n".join(source_links)}
        </div>
      </div>'''


def _replace_owned_region(
    source: str,
    start_marker: str,
    end_marker: str,
    rendered: str,
    label: str,
) -> str:
    if source.count(start_marker) != 1 or source.count(end_marker) != 1:
        raise SearchEntrypointError(
            f"{label}: ownership markers must each occur exactly once"
        )
    start = source.index(start_marker) + len(start_marker)
    end = source.index(end_marker, start)
    newline = "\r\n" if "\r\n" in source else "\n"
    localized = rendered.replace("\n", newline)
    return source[:start] + newline + localized + newline + source[end:]


def render_semantic_regions(
    source: str,
    model: dict[str, Any],
    language: str,
) -> str:
    if language not in COPY:
        raise SearchEntrypointError(f"unsupported semantic language: {language}")
    text = _replace_owned_region(
        source,
        WHAT_CHANGED_START,
        WHAT_CHANGED_END,
        render_what_changed(model, language),
        "What Changed semantic region",
    )
    return _replace_owned_region(
        text,
        RACE_START,
        RACE_END,
        render_race(model, language),
        "Race at a Glance semantic region",
    )


def _localize_english_head(source: str) -> str:
    newline = "\r\n" if "\r\n" in source else "\n"
    text = source
    text = replace_once(
        text,
        '<html lang="fr" data-site-root="./"',
        '<html lang="en" data-site-root="/"',
        "document language/site root",
    )
    text = replace_once(
        text,
        "<head>",
        f'<head>{newline}  <base href="/">',
        "English base URL",
    )
    text = replace_once(
        text,
        (
            '<meta name="description" content="'
            "Sondages sourcés, actualité électorale, couverture des candidats "
            "et vérifications pour la présidentielle française de 2027. "
            'Aucune moyenne, aucune prévision, aucun conseil de vote.">'
        ),
        f'<meta name="description" content="{ENGLISH_DESCRIPTION}">',
        "English meta description",
    )
    text = replace_once(
        text,
        '<link rel="canonical" href="https://france2027.app/">',
        '<link rel="canonical" href="https://france2027.app/en/">',
        "English canonical",
    )
    text = replace_once(
        text,
        '<meta property="og:title" content="France 2027 Signal Lab — Signaux électoraux sourcés">',
        f'<meta property="og:title" content="{ENGLISH_TITLE}">',
        "English Open Graph title",
    )
    text = replace_once(
        text,
        (
            '<meta property="og:description" content="'
            "Sondages sourcés, actualité électorale, couverture des candidats "
            "et vérifications pour la présidentielle française de 2027. "
            'Aucune moyenne, aucune prévision, aucun conseil de vote.">'
        ),
        f'<meta property="og:description" content="{ENGLISH_DESCRIPTION}">',
        "English Open Graph description",
    )
    text = replace_once(
        text,
        '<meta property="og:url" content="https://france2027.app/">',
        '<meta property="og:url" content="https://france2027.app/en/">',
        "English Open Graph URL",
    )
    text = replace_once(
        text,
        '<meta name="twitter:title" content="France 2027 Signal Lab — Signaux électoraux sourcés">',
        f'<meta name="twitter:title" content="{ENGLISH_TITLE}">',
        "English Twitter title",
    )
    text = replace_once(
        text,
        (
            '<meta name="twitter:description" content="'
            "Sondages sourcés, actualité électorale, couverture des candidats "
            "et vérifications pour la présidentielle française de 2027. "
            'Aucune moyenne, aucune prévision, aucun conseil de vote.">'
        ),
        f'<meta name="twitter:description" content="{ENGLISH_DESCRIPTION}">',
        "English Twitter description",
    )
    return replace_once(
        text,
        "<title>France 2027 Signal Lab — Signaux électoraux sourcés</title>",
        f"<title>{ENGLISH_TITLE}</title>",
        "English document title",
    )


def build_english_entrypoint(
    source: str,
    model: dict[str, Any] | None = None,
) -> str:
    semantic_model = model if model is not None else load_semantic_model()
    return _localize_english_head(
        render_semantic_regions(source, semantic_model, "en")
    )


def _owned_region(text: str, start_marker: str, end_marker: str) -> str:
    start = text.index(start_marker) + len(start_marker)
    end = text.index(end_marker, start)
    return text[start:end]


def validate_document(text: str, language: str) -> None:
    for start_marker, end_marker, label in (
        (WHAT_CHANGED_START, WHAT_CHANGED_END, "What Changed"),
        (RACE_START, RACE_END, "Race at a Glance"),
    ):
        if text.count(start_marker) != 1 or text.count(end_marker) != 1:
            raise SearchEntrypointError(
                f"{label}: invalid generated ownership boundary"
            )
        region = _owned_region(text, start_marker, end_marker)
        if 'data-fr27-semantic-snapshot="true"' not in region:
            raise SearchEntrypointError(f"{label}: semantic state is missing")
        if "visually-hidden" in region or "<noscript" in region:
            raise SearchEntrypointError(f"{label}: snapshot must be visible")
    race = _owned_region(text, RACE_START, RACE_END)
    if "<time " not in race or "<data " not in race or "<a" not in race:
        raise SearchEntrypointError("Race at a Glance lacks semantic evidence markup")
    if f'<html lang="{language}"' not in text:
        raise SearchEntrypointError(f"document language is not {language}")
    if language == "fr":
        if '<base href="/">' in text:
            raise SearchEntrypointError("French root must not contain an English base")
        canonical = '<link rel="canonical" href="https://france2027.app/">'
    else:
        if text.count('<base href="/">') != 1:
            raise SearchEntrypointError("English document must contain one base URL")
        canonical = '<link rel="canonical" href="https://france2027.app/en/">'
    if text.count(canonical) != 1:
        raise SearchEntrypointError("document canonical contract changed")


def build_documents(
    source: str,
    candidate_signals: Any,
    recent_changes: Any,
) -> tuple[str, str]:
    model = construct_semantic_model(candidate_signals, recent_changes)
    french = render_semantic_regions(source, model, "fr")
    english = build_english_entrypoint(french, model)
    validate_document(french, "fr")
    validate_document(english, "en")
    return french, english


def _stage_bytes(path: Path, content: bytes) -> Path:
    path.parent.mkdir(parents=True, exist_ok=True)
    handle = tempfile.NamedTemporaryFile(
        mode="wb",
        dir=path.parent,
        prefix=f".{path.name}.",
        suffix=".tmp",
        delete=False,
    )
    temporary = Path(handle.name)
    try:
        with handle:
            handle.write(content)
            handle.flush()
            os.fsync(handle.fileno())
        return temporary
    except BaseException:
        temporary.unlink(missing_ok=True)
        raise


def _write_pair(
    source_path: Path,
    source_bytes: bytes,
    english_path: Path,
    english_bytes: bytes,
) -> None:
    originals = {
        source_path: source_path.read_bytes() if source_path.exists() else None,
        english_path: english_path.read_bytes() if english_path.exists() else None,
    }
    source_temporary: Path | None = None
    english_temporary: Path | None = None
    try:
        source_temporary = _stage_bytes(source_path, source_bytes)
        english_temporary = _stage_bytes(english_path, english_bytes)
    except BaseException:
        if source_temporary is not None:
            source_temporary.unlink(missing_ok=True)
        if english_temporary is not None:
            english_temporary.unlink(missing_ok=True)
        raise
    replaced: list[Path] = []
    try:
        os.replace(source_temporary, source_path)
        replaced.append(source_path)
        os.replace(english_temporary, english_path)
        replaced.append(english_path)
    except BaseException:
        source_temporary.unlink(missing_ok=True)
        english_temporary.unlink(missing_ok=True)
        for path in reversed(replaced):
            original = originals[path]
            if original is None:
                path.unlink(missing_ok=True)
            else:
                rollback = _stage_bytes(path, original)
                os.replace(rollback, path)
        raise


def generate_entrypoints(
    *,
    source_path: Path = SOURCE,
    english_output_path: Path = ENGLISH_OUTPUT,
    candidate_signals_path: Path = CANDIDATE_SIGNALS,
    recent_changes_path: Path = RECENT_CHANGES,
    check: bool = False,
) -> tuple[bool, bool]:
    source_bytes = source_path.read_bytes()
    candidate_signals = _load_json(candidate_signals_path)
    recent_changes = _load_json(recent_changes_path)
    french, english = build_documents(
        source_bytes.decode("utf-8"),
        candidate_signals,
        recent_changes,
    )
    french_bytes = french.encode("utf-8")
    english_bytes = english.encode("utf-8")
    current_english = (
        english_output_path.read_bytes()
        if english_output_path.exists()
        else None
    )
    french_changed = french_bytes != source_bytes
    english_changed = english_bytes != current_english
    if check:
        stale = []
        if french_changed:
            stale.append(str(source_path))
        if english_changed:
            stale.append(str(english_output_path))
        if stale:
            raise SearchEntrypointError(
                "stale generated search entrypoints: " + ", ".join(stale)
            )
        return False, False
    if french_changed or english_changed:
        _write_pair(
            source_path,
            french_bytes,
            english_output_path,
            english_bytes,
        )
    return french_changed, english_changed


def _parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description="Build deterministic FR27 semantic search entrypoints"
    )
    parser.add_argument("--check", action="store_true")
    parser.add_argument("--source", type=Path, default=SOURCE)
    parser.add_argument(
        "--english-output",
        type=Path,
        default=ENGLISH_OUTPUT,
    )
    parser.add_argument(
        "--candidate-signals",
        type=Path,
        default=CANDIDATE_SIGNALS,
    )
    parser.add_argument(
        "--recent-changes",
        type=Path,
        default=RECENT_CHANGES,
    )
    return parser


def main(argv: list[str] | None = None) -> int:
    arguments = _parser().parse_args(argv)
    try:
        changed = generate_entrypoints(
            source_path=arguments.source,
            english_output_path=arguments.english_output,
            candidate_signals_path=arguments.candidate_signals,
            recent_changes_path=arguments.recent_changes,
            check=arguments.check,
        )
    except (OSError, UnicodeDecodeError, SearchEntrypointError) as error:
        print(f"search entrypoint error: {error}")
        return 1
    if arguments.check:
        print("Validated deterministic semantic search entrypoints")
    else:
        updated = []
        if changed[0]:
            updated.append(str(arguments.source))
        if changed[1]:
            updated.append(str(arguments.english_output))
        print("Generated " + (", ".join(updated) if updated else "no changes"))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
