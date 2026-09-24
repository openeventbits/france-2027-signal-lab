"""Data-backed bilingual Candidates hub rendering."""

from __future__ import annotations

import html
from typing import Any

from candidate_page_contract import PUBLIC_ORIGIN, project_candidate_page_index


STATUS_LABELS = {
    "fr": {
        "declared": "Candidature déclarée",
        "party_selected": "Candidature sélectionnée par un parti",
        "primary_contender": "Candidature en sélection",
        "active_potential": "Candidature potentielle",
        "conditional": "Candidature conditionnelle",
    },
    "en": {
        "declared": "Declared candidacy",
        "party_selected": "Party-selected candidacy",
        "primary_contender": "Candidacy in selection",
        "active_potential": "Potential candidacy",
        "conditional": "Conditional candidacy",
    },
}


COPY = {
    "fr": {
        "lang_tag": "fr-FR",
        "og_locale": "fr_FR",
        "canonical_path": "/candidates/",
        "title": "Candidats suivis — France 2027 Signal Lab",
        "description": (
            "Annuaire bilingue des candidatures suivies pour la présidentielle "
            "française de 2027, avec dossiers sourcés et disponibilité des preuves."
        ),
        "brand_note": "Signaux sourcés de la présidentielle française.",
        "breadcrumb": "CANDIDATS",
        "eyebrow": "RÉPERTOIRE PUBLIC",
        "heading": "CANDIDATS",
        "count_suffix": "profils suivis",
        "intro": (
            "Dossiers de candidature reliés aux sources couvrant les sondages, "
            "la visibilité médiatique, l’agenda, les vérifications, l’attention "
            "publique, les événements et les preuves de candidature lorsqu’elles "
            "sont disponibles."
        ),
        "search_label": "Rechercher une candidature",
        "search_placeholder": "Nom de la candidate ou du candidat",
        "filter_label": "Statut factuel",
        "all": "Tous les statuts",
        "results": "profils affichés",
        "open": "Ouvrir le dossier",
        "availability": "PREUVES DISPONIBLES",
        "available": "disponible",
        "not_observed": "non observé",
        "unavailable": "indisponible",
        "method_heading": "CE QUE SIGNIFIE « SUIVI »",
        "method": (
            "Un profil suivi appartient au champ actif du registre canonique des "
            "candidatures. Sa présence ne constitue ni un classement, ni une "
            "prévision, ni une évaluation d’éligibilité. Les indicateurs signalent "
            "uniquement si des éléments sont publiés dans chaque corpus."
        ),
        "no_js": "La liste complète reste disponible ci-dessous sans JavaScript.",
        "dashboard": "OUVRIR LE MONITEUR",
        "directory": "ANNUAIRE DES CANDIDATURES",
        "locale_name": "Français",
        "portrait_alt": "Portrait illustré de {name}",
        "portrait_missing": "Portrait non disponible pour {name}",
    },
    "en": {
        "lang_tag": "en-GB",
        "og_locale": "en_GB",
        "canonical_path": "/en/candidates/",
        "title": "Monitored candidates — France 2027 Signal Lab",
        "description": (
            "Bilingual directory of monitored candidacies for France's 2027 "
            "presidential election, with source-linked dossiers and evidence availability."
        ),
        "brand_note": "Source-linked signals for France's presidential election.",
        "breadcrumb": "CANDIDATES",
        "eyebrow": "PUBLIC DIRECTORY",
        "heading": "CANDIDATES",
        "count_suffix": "monitored profiles",
        "intro": (
            "Source-linked candidate dossiers covering polling, media visibility, "
            "agenda, scrutiny, public attention, events and candidacy evidence "
            "where available."
        ),
        "search_label": "Search candidates",
        "search_placeholder": "Candidate name",
        "filter_label": "Factual status",
        "all": "All statuses",
        "results": "profiles shown",
        "open": "Open dossier",
        "availability": "EVIDENCE AVAILABILITY",
        "available": "available",
        "not_observed": "not observed",
        "unavailable": "unavailable",
        "method_heading": "WHAT “MONITORED” MEANS",
        "method": (
            "A monitored profile belongs to the active field of the canonical "
            "candidacy registry. Inclusion is not a ranking, forecast or assessment "
            "of electability. Indicators only state whether evidence is published "
            "in each corpus."
        ),
        "no_js": "The complete list remains available below without JavaScript.",
        "dashboard": "OPEN THE MONITOR",
        "directory": "CANDIDATE DIRECTORY",
        "locale_name": "English",
        "portrait_alt": "Illustrated portrait of {name}",
        "portrait_missing": "Portrait unavailable for {name}",
    },
}


SIGNAL_LABELS = {
    "fr": {
        "polling": "Sondages",
        "media": "Médias actuels",
        "agenda": "Agenda",
        "scrutiny": "Vérifications",
        "attention": "Attention",
        "events": "Événements",
    },
    "en": {
        "polling": "Polling",
        "media": "Current media",
        "agenda": "Agenda",
        "scrutiny": "Scrutiny",
        "attention": "Attention",
        "events": "Events",
    },
}


def _h(value: Any) -> str:
    return html.escape(str(value), quote=True)


def _initials(candidate_name: str) -> str:
    parts = [part for part in candidate_name.replace("-", " ").split() if part]
    return "".join(part[0] for part in parts[:2]).upper()


def build_hub_model(
    candidacy_payload: dict[str, Any],
    projections: list[dict[str, Any]],
) -> dict[str, Any]:
    """Join canonical routes to dossier evidence without a second roster."""

    page_index = project_candidate_page_index(candidacy_payload)
    projection_by_id = {
        projection["candidate_id"]: projection for projection in projections
    }
    expected_ids = {
        candidate["candidate_id"] for candidate in page_index["candidates"]
    }

    if set(projection_by_id) != expected_ids:
        raise ValueError("hub projections do not match the canonical active roster")

    candidates = []
    for candidate in page_index["candidates"]:
        projection = projection_by_id[candidate["candidate_id"]]
        polling = projection["polling"]
        agenda = projection["agenda"]
        candidates.append(
            {
                **candidate,
                "portrait_path": projection["candidate"].get("portrait_path"),
                "availability": {
                    "polling": "available" if (
                        polling["current"]["evidence_state"] == "reported"
                        or polling["first_round_history"]["observation_count"] > 0
                    ) else "not_observed",
                    "media": "available" if (
                        projection["media"]["summary"]["evidence_state"]
                        == "reported"
                    ) else "not_observed",
                    "agenda": "available" if (
                        agenda["current"]["association_count"] > 0
                        or agenda["since_tracking"]["association_count"] > 0
                    ) else "not_observed",
                    "scrutiny": "available" if (
                        projection["accountability"]["review_count"] > 0
                    ) else "not_observed",
                    "attention": "available" if (
                        projection["attention"]["evidence_state"] == "observed"
                    ) else "unavailable",
                    "events": "available" if bool(
                        projection["events"]["upcoming"]
                        or projection["events"]["recent"]
                    ) else "not_observed",
                },
            }
        )

    return {
        "schema_version": page_index["schema_version"],
        "status_as_of": page_index["status_as_of"],
        "count": len(candidates),
        "statuses": sorted({candidate["status"] for candidate in candidates}),
        "candidates": candidates,
    }


def _portrait(candidate: dict[str, Any], copy: dict[str, str]) -> str:
    name = candidate["candidate_name"]
    initials = _h(_initials(name))
    fallback = (
        '<span class="candidate-hub-portrait-fallback" aria-hidden="true">'
        f"{initials}</span>"
    )
    portrait_path = candidate.get("portrait_path")
    if not portrait_path:
        return (
            '<div class="candidate-hub-portrait is-fallback" role="img" '
            f'aria-label="{_h(copy["portrait_missing"].format(name=name))}">'
            f"{fallback}</div>"
        )
    return (
        '<div class="candidate-hub-portrait">'
        f"{fallback}"
        f'<img src="{_h(portrait_path)}" '
        f'alt="{_h(copy["portrait_alt"].format(name=name))}" '
        'width="112" height="112" loading="lazy" decoding="async" '
        'onerror="this.remove()"></div>'
    )


def _card(candidate: dict[str, Any], lang: str) -> str:
    copy = COPY[lang]
    name = candidate["candidate_name"]
    route = candidate["routes"][lang]
    status = candidate["status"]
    availability = "".join(
        '<li class="candidate-hub-signal '
        + ("is-available" if state == "available" else "is-not-observed")
        + f'" data-signal="{_h(signal)}" data-available="'
        + ("true" if state == "available" else "false")
        + f'" data-evidence-state="{_h(state)}'
        + '"><span aria-hidden="true"></span><b>'
        + _h(SIGNAL_LABELS[lang][signal])
        + "</b><small>"
        + _h(copy[state])
        + "</small></li>"
        for signal, state in candidate["availability"].items()
    )
    return f'''<article class="candidate-hub-card" data-candidate-card data-candidate-id="{_h(candidate["candidate_id"])}" data-candidate-name="{_h(name)}" data-candidate-status="{_h(status)}">
  <div class="candidate-hub-card-top">{_portrait(candidate, copy)}<div><p class="candidate-hub-card-kicker">{_h(STATUS_LABELS[lang][status])}</p><h2><a href="{_h(route)}">{_h(name)}</a></h2></div></div>
  <div class="candidate-hub-availability"><h3>{_h(copy["availability"])}</h3><ul>{availability}</ul></div>
  <a class="candidate-hub-open" href="{_h(route)}">{_h(copy["open"])} <span aria-hidden="true">↗</span></a>
</article>'''


def render_hub(
    model: dict[str, Any],
    *,
    lang: str,
    favicon_markup: str,
    og_image: str,
) -> bytes:
    """Render an indexable, useful-without-JavaScript candidate directory."""

    if lang not in COPY:
        raise ValueError(f"unsupported hub locale: {lang}")

    copy = COPY[lang]
    fr_url = f"{PUBLIC_ORIGIN}/candidates/"
    en_url = f"{PUBLIC_ORIGIN}/en/candidates/"
    canonical = f'{PUBLIC_ORIGIN}{copy["canonical_path"]}'
    alternate_locale = "en_GB" if lang == "fr" else "fr_FR"
    peer_path = "/en/candidates/" if lang == "fr" else "/candidates/"
    cards = "\n".join(_card(candidate, lang) for candidate in model["candidates"])
    options = "".join(
        f'<option value="{_h(status)}">{_h(STATUS_LABELS[lang][status])}</option>'
        for status in model["statuses"]
    )

    document = f'''<!doctype html>
<html lang="{lang}">
<head>
  <meta charset="utf-8">
  <meta name="viewport" content="width=device-width, initial-scale=1">
  <meta name="robots" content="index,follow,max-image-preview:large">
  <meta name="description" content="{_h(copy["description"])}">
  <link rel="canonical" href="{_h(canonical)}">
  <link rel="alternate" hreflang="fr" href="{_h(fr_url)}">
  <link rel="alternate" hreflang="en" href="{_h(en_url)}">
  <link rel="alternate" hreflang="x-default" href="{_h(fr_url)}">
  {favicon_markup}
  <meta name="theme-color" content="#050b14">
  <meta name="color-scheme" content="dark">
  <meta property="og:type" content="website">
  <meta property="og:site_name" content="France 2027 Signal Lab">
  <meta property="og:title" content="{_h(copy["title"])}">
  <meta property="og:description" content="{_h(copy["description"])}">
  <meta property="og:url" content="{_h(canonical)}">
  <meta property="og:locale" content="{copy["og_locale"]}">
  <meta property="og:locale:alternate" content="{alternate_locale}">
  <meta property="og:image" content="{_h(og_image)}">
  <meta property="og:image:alt" content="France 2027 Signal Lab">
  <meta name="twitter:card" content="summary_large_image">
  <meta name="twitter:title" content="{_h(copy["title"])}">
  <meta name="twitter:description" content="{_h(copy["description"])}">
  <meta name="twitter:image" content="{_h(og_image)}">
  <title>{_h(copy["title"])}</title>
  <link rel="stylesheet" href="/assets/fr27-ui.css">
  <link rel="stylesheet" href="/assets/candidate-page-shell.css">
  <link rel="stylesheet" href="/assets/candidate-hub.css">
  <script src="/assets/fr27-ui.js" defer></script>
  <script src="/assets/candidate-hub.js" defer></script>
</head>
<body class="candidate-page candidate-hub-page">
  <main class="candidate-shell">
    <header class="candidate-masthead" aria-label="France 2027 Signal Lab">
      <a class="candidate-brand" href="{'/en/' if lang == 'en' else '/'}" aria-label="France 2027 Signal Lab">
        <span class="candidate-mark" aria-hidden="true"><svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 32 32" focusable="false"><rect x="1" y="1" width="30" height="30" rx="8" fill="#071522"/><path d="M6 16A10 10 0 0 1 16 6M26 16A10 10 0 0 1 16 26" fill="none" stroke="#268cff" stroke-width="2" stroke-linecap="round"/><path d="M10 16A6 6 0 0 1 16 10M22 16A6 6 0 0 1 16 22" fill="none" stroke="#35d5ff" stroke-width="2" stroke-linecap="round"/><circle cx="16" cy="16" r="2.5" fill="#35d5ff"/></svg></span>
        <span class="candidate-brand-copy"><strong>FRANCE 2027 <em>SIGNAL LAB</em></strong><small>{_h(copy["brand_note"])}</small></span>
      </a>
      <nav class="candidate-language" aria-label="{_h(copy["locale_name"])}"><a href="/candidates/" lang="fr" hreflang="fr"{' aria-current="page"' if lang == 'fr' else ''}>FR</a><span aria-hidden="true">|</span><a href="/en/candidates/" lang="en" hreflang="en"{' aria-current="page"' if lang == 'en' else ''}>EN</a></nav>
    </header>

    <nav class="candidate-hub-breadcrumb" aria-label="Breadcrumb"><a href="{'/en/' if lang == 'en' else '/'}">FR27</a><span aria-hidden="true">/</span><span aria-current="page">{_h(copy["breadcrumb"])}</span></nav>

    <header class="candidate-hub-hero">
      <div><p class="candidate-hub-eyebrow">{_h(copy["eyebrow"])}</p><h1>{_h(copy["heading"])}</h1></div>
      <p class="candidate-hub-count"><strong data-candidate-total>{model["count"]}</strong><span>{_h(copy["count_suffix"])}</span></p>
      <p class="candidate-hub-intro">{_h(copy["intro"])}</p>
    </header>

    <section class="candidate-hub-controls" aria-label="Candidate search and filters">
      <label><span>{_h(copy["search_label"])}</span><input type="search" data-candidate-search placeholder="{_h(copy["search_placeholder"])}" autocomplete="off"></label>
      <label><span>{_h(copy["filter_label"])}</span><select data-candidate-status><option value="">{_h(copy["all"])}</option>{options}</select></label>
      <p class="candidate-hub-result-count" aria-live="polite"><strong data-candidate-visible-count>{model["count"]}</strong> {_h(copy["results"])}</p>
      <noscript><p>{_h(copy["no_js"])}</p></noscript>
    </section>

    <section class="candidate-hub-grid" data-candidate-grid aria-label="{_h(copy["heading"])}">
{cards}
    </section>

    <section class="candidate-hub-method" aria-labelledby="candidate-hub-method-title">
      <p class="candidate-hub-eyebrow">MÉTHODOLOGIE / METHODOLOGY</p>
      <h2 id="candidate-hub-method-title">{_h(copy["method_heading"])}</h2>
      <p>{_h(copy["method"])}</p>
    </section>

    <footer class="candidate-hub-hud">
      <div><span>FR27</span><strong>{_h(copy["directory"])}</strong></div>
      <div><span>ACTIVE</span><strong>{model["count"]}</strong></div>
      <div><span>STATUS AS OF</span><strong>{_h(model["status_as_of"])}</strong></div>
      <a href="{'/en/' if lang == 'en' else '/'}">{_h(copy["dashboard"])} <span aria-hidden="true">↗</span></a>
    </footer>
  </main>
</body>
</html>
'''
    return document.encode("utf-8")
