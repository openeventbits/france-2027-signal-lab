"""Three frozen, reviewed PDF tables for presentation only.

No numerical observations, ingestion hooks, route registration or network I/O.
The vendored records retain the original Phase 1 review and PDF content hashes.
"""

import hashlib
from html import escape
import json
from pathlib import Path

RECORD_PATH = Path(__file__).with_name("poll_source_tables.json")
RECORD_SHA256 = "4ede22b9d7973257cedd2f76ff0edeb137ff43d8e67ca946800d7251d76eb526"


def digest(value):
    return hashlib.sha256(json.dumps(value, ensure_ascii=False, sort_keys=True,
                                     separators=(",", ":")).encode()).hexdigest()


def load_source_tables(path=RECORD_PATH):
    record = json.loads(Path(path).read_text(encoding="utf-8"))
    if digest(record) != RECORD_SHA256:
        raise ValueError("Reviewed source-table presentation evidence changed")
    for entry in record["tables"].values():
        if digest(entry["table"]) != entry["record_sha256"]:
            raise ValueError("Reviewed source table changed")
    return record


def numeric_context(wave):
    # Authenticate the existing association, never infer it from a weak anchor.
    return {k: wave[k] for k in (
        "wave_id", "page_path_fr", "page_path_en", "pollster", "fieldwork_start",
        "fieldwork_end", "sample_size", "scenario_count",
    )} | {"scenarios": [
        {"event_id": scenario["event_id"], "source_url": scenario["source_url"],
         "scores": [[c["candidate_id"], c["score"]] for c in scenario["candidates"]]}
        for scenario in wave["scenarios"]
    ]}


def source_table_for_wave(wave, record):
    for notice, pin in record["existing_pages"].items():
        if wave["wave_id"] == pin["wave_id"]:
            if digest(numeric_context(wave)) != pin["numeric_context_sha256"]:
                raise ValueError("Reviewed source-table numerical association changed")
            return record["tables"][notice]["table"]
    return None


def render_source_card(table, language, *, standalone=False):
    fr = language == "fr"
    notice = table["notice"]["notice_id"].split(":")[1]
    position = {
        "10327": ("TABLEAU 6 SUR 8 DU PDF ORIGINAL", "TABLE 6 OF 8 IN THE ORIGINAL PDF"),
        "10260": ("HYPOTHÈSE 3 DU PDF ORIGINAL", "HYPOTHESIS 3 IN THE ORIGINAL PDF"),
        "10264": ("TABLEAU PUBLIÉ · PAGE 12", "PUBLISHED TABLE · PAGE 12"),
    }[notice][not fr]
    rows = []
    for row in table["rows"]:
        result = row["result"]
        # Only the requested typographic dash is displayed; the authenticated
        # source record retains its exact '-' transcription. Neither is zero.
        literal = "–" if result["kind"] == "source_dash" else result["literal"]
        exceptional = result["kind"] != "exact"
        rows.append(f'<tr><th scope="row">{escape(row["published_name"])}</th>'
                    f'<td class="poll-detail-score{" poll-source-literal" if exceptional else ""}"'
                    f' data-published-literal="{escape(result["literal"], quote=True)}">{escape(literal)}</td></tr>')
    note = ("Document source uniquement : ce tableau n’ajoute aucune observation numérique."
            if fr else "Source evidence only: this table adds no numerical observation.")
    if notice == "10327":
        note += (' Les huit cartes numériques restent inchangées ; leur ordre n’est pas celui du PDF. '
                 '<a href="#scenario-4" onclick="document.getElementById(\'scenario-4\').open=true">Voir la carte numérique 4 conservée (0 % pour Arthaud).</a>' if fr else
                 ' The eight numerical cards are unchanged; their order differs from the PDF. '
                 '<a href="#scenario-4" onclick="document.getElementById(\'scenario-4\').open=true">View retained numerical card 4 (0% for Arthaud).</a>')
    title = table["institute"] + (" / " + table["commissioner"] if table["commissioner"] else "")
    return (
        f'<details class="poll-detail-scenario poll-detail-source-only" id="source-table-{notice}"'
        f'{" open" if standalone else ""}>'
        '<summary class="poll-detail-scenario-summary"><div class="poll-detail-scenario-summary-main">'
        '<div class="poll-detail-scenario-kicker">'
        f'<span class="poll-detail-scenario-number">{position}</span>'
        f'<span class="poll-detail-scenario-status is-source-only">{"SOURCE UNIQUEMENT" if fr else "SOURCE ONLY"}</span></div>'
        f'<h3>{escape(title)}</h3><div class="poll-detail-scenario-meta">'
        f'<span>{len(table["rows"])} {"CANDIDATS TESTÉS" if fr else "TESTED CANDIDATES"}</span>'
        f'<span>NOTICE {notice} · PDF p. {table["source"]["pdf_page"]}</span></div></div>'
        '<span class="poll-detail-scenario-toggle" aria-hidden="true">'
        f'<span class="poll-detail-scenario-toggle-text" data-open-label="{"OUVRIR" if fr else "OPEN"}" '
        f'data-close-label="{"RÉDUIRE" if fr else "COLLAPSE"}">{("RÉDUIRE" if fr else "COLLAPSE") if standalone else ("OUVRIR" if fr else "OPEN")}</span>'
        '<i class="poll-detail-scenario-toggle-icon"></i></span></summary>'
        '<div class="poll-detail-scenario-body"><div class="poll-detail-table-wrap">'
        f'<table class="poll-detail-table" aria-label="{position}"><thead><tr>'
        f'<th scope="col">{"CANDIDAT TESTÉ" if fr else "TESTED CANDIDATE"}</th>'
        f'<th scope="col">{"RÉSULTAT PUBLIÉ (%)" if fr else "PUBLISHED RESULT (%)"}</th></tr></thead>'
        f'<tbody>{"".join(rows)}</tbody></table></div>'
        f'<p class="poll-source-context">{note}</p><div class="poll-detail-scenario-foot">'
        f'<span>{escape("Valeurs littérales ; tiret ≠ zéro, <1% ≠ score exact." if fr else "Literal values; a dash is not zero, <1% is not an exact score.")}</span>'
        f'<a href="{escape(table["source"]["pdf_url"], quote=True)}#page={table["source"]["pdf_page"]}" '
        f'target="_blank" rel="noopener noreferrer">{"PDF ORIGINAL" if fr else "ORIGINAL PDF"} ↗</a>'
        '</div></div></details>'
    )
