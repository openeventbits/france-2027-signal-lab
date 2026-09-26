"""Data-backed bilingual Candidates hub rendering."""

from __future__ import annotations

import html
import json
from typing import Any

from candidate_page_contract import (
    ARCHIVED_CANDIDACY_STATUSES,
    PUBLIC_ORIGIN,
    is_archived_candidacy_status,
    project_candidate_page_index,
)


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
        "home": "ACCUEIL",
        "breadcrumb": "CANDIDATS",
        "eyebrow": "CANDIDATS",
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
        "filter_label": "CATÉGORIE",
        "all": "Toutes les catégories",
        "results": "profils affichés",
        "archived": "Archivés",
        "archive_cta": "ARCHIVES · {count}",
        "archive_collapse": "RÉDUIRE LES ARCHIVES",
        "show_potential": "AFFICHER PLUS",
        "collapse_directory": "RÉDUIRE",
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
        "language_label": "Langue de l’interface",
        "metric_monitored": "PROFILS SUIVIS",
        "metric_declared": "DÉCLARÉS",
        "metric_selected": "SÉLECTIONNÉS",
        "metric_selection": "EN SÉLECTION",
        "metric_potential": "POTENTIELS",
        "info_label": "Informations sur l’annuaire des candidats",
        "countdown_aria": "Compte à rebours avant le premier tour",
        "countdown_unit": "jours",
        "countdown_label": "avant le premier tour",
        "countdown_date": "18 avr. 2027",
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
        "home": "HOME",
        "breadcrumb": "CANDIDATES",
        "eyebrow": "CANDIDATES",
        "heading": "CANDIDATES",
        "count_suffix": "monitored profiles",
        "intro": (
            "Source-linked candidate dossiers covering polling, media visibility, "
            "agenda, scrutiny, public attention, events and candidacy evidence "
            "where available."
        ),
        "search_label": "Search candidates",
        "search_placeholder": "Candidate name",
        "filter_label": "CATEGORY",
        "all": "All categories",
        "results": "profiles shown",
        "archived": "Archived",
        "archive_cta": "ARCHIVED · {count}",
        "archive_collapse": "COLLAPSE ARCHIVE",
        "show_potential": "SHOW MORE",
        "collapse_directory": "SHOW LESS",
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
        "language_label": "Interface language",
        "metric_monitored": "PROFILES MONITORED",
        "metric_declared": "DECLARED",
        "metric_selected": "SELECTED",
        "metric_selection": "IN SELECTION",
        "metric_potential": "POTENTIAL",
        "info_label": "Information about the candidate directory",
        "countdown_aria": "First-round election countdown",
        "countdown_unit": "days",
        "countdown_label": "before the first round",
        "countdown_date": "18 Apr 2027",
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



def _numeric_poll_order_score(primary: Any, fallback: Any) -> float | None:
    for value in (primary, fallback):
        if value is None or value == "":
            continue
        try:
            score = float(value)
        except (TypeError, ValueError):
            continue
        return score
    return None


def _latest_historical_poll_observation(
    candidate: dict[str, Any],
) -> dict[str, Any] | None:
    observations = candidate.get("poll_history", {}).get("observations")

    if not isinstance(observations, list) or not observations:
        return None

    latest = None

    for observation in observations:
        fieldwork_end = observation.get("fieldwork_end")
        if not fieldwork_end:
            continue

        if (
            latest is None
            or str(fieldwork_end) > str(latest["fieldwork_end"])
        ):
            latest = observation

    return latest


def _featured_poll_order_score(candidate: dict[str, Any]) -> float | None:
    polling = candidate.get("polling", {})

    if polling.get("evidence_state") != "reported":
        return None

    return _numeric_poll_order_score(
        polling.get("selected_hypothesis_score"),
        polling.get("range_max"),
    )


def _historical_poll_order_score(
    candidate: dict[str, Any],
) -> float | None:
    observation = _latest_historical_poll_observation(candidate)

    if observation is None:
        return None

    return _numeric_poll_order_score(
        observation.get("selected_score"),
        observation.get("range_max"),
    )


def _poll_order_group(candidate: dict[str, Any]) -> int:
    if candidate.get("polling", {}).get("evidence_state") == "reported":
        return 0

    if _latest_historical_poll_observation(candidate) is not None:
        return (
            2
            if candidate.get("candidacy", {}).get("display_tier")
            == "secondary"
            else 1
        )

    return 3


def _poll_order_score(
    candidate: dict[str, Any],
    group: int,
) -> float | None:
    if group == 0:
        return _featured_poll_order_score(candidate)

    if group in (1, 2):
        return _historical_poll_order_score(candidate)

    return None


def _order_workspace_candidates(
    candidates: list[dict[str, Any]],
) -> list[dict[str, Any]]:
    """Exact generator-side mirror of Candidate Monitor display ordering."""

    ordered: list[dict[str, Any]] = []

    for candidate in candidates:
        group = _poll_order_group(candidate)
        score = _poll_order_score(candidate, group)
        insertion = None

        for index, existing in enumerate(ordered):
            existing_group = _poll_order_group(existing)

            if group != existing_group:
                if group < existing_group:
                    insertion = index
                    break
                continue

            if group == 3:
                continue

            existing_score = _poll_order_score(
                existing,
                existing_group,
            )

            if score is None:
                continue

            if existing_score is None or score > existing_score:
                insertion = index
                break

        if insertion is None:
            ordered.append(candidate)
        else:
            ordered.insert(insertion, candidate)

    return ordered


def _workspace_order_candidate_ids(
    candidate_signals_payload: dict[str, Any],
) -> list[str]:
    candidates = candidate_signals_payload.get("candidates")

    if not isinstance(candidates, list):
        raise ValueError("Candidate Signals candidates are unavailable")

    field = (
        candidate_signals_payload.get("active_monitoring_field")
        or candidate_signals_payload.get("presidential_field")
    )

    if not isinstance(field, dict):
        raise ValueError("Candidate Signals active field is unavailable")

    main = field.get("main")
    secondary = field.get("secondary")

    if not isinstance(main, list) or not isinstance(secondary, list):
        raise ValueError("Candidate Signals active field is invalid")

    active_ids = [*main, *secondary]
    active_set = set(active_ids)

    visible = [
        candidate
        for candidate in candidates
        if candidate.get("candidate_id") in active_set
    ]

    ordered = _order_workspace_candidates(visible)

    return [
        candidate["candidate_id"]
        for candidate in ordered
    ]


def build_hub_model(
    candidacy_payload: dict[str, Any],
    projections: list[dict[str, Any]],
    candidate_signals_payload: dict[str, Any] | None = None,
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

    page_candidates = list(page_index["candidates"])

    if candidate_signals_payload is not None:
        ordered_ids = _workspace_order_candidate_ids(
            candidate_signals_payload
        )

        if set(ordered_ids) != expected_ids:
            raise ValueError(
                "Candidate Monitor order does not match canonical active roster"
            )

        order_index = {
            candidate_id: index
            for index, candidate_id in enumerate(ordered_ids)
        }

        page_candidates.sort(
            key=lambda candidate: order_index[candidate["candidate_id"]]
        )

    candidates = []
    for candidate in page_candidates:
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
        "status_counts": {
            status: sum(candidate["status"] == status for candidate in candidates)
            for status in STATUS_LABELS["fr"]
        },
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


def _breadcrumb_json_ld(lang: str, copy: dict[str, str], canonical: str) -> str:
    home_url = f"{PUBLIC_ORIGIN}{'/en/' if lang == 'en' else '/'}"
    payload = {
        "@context": "https://schema.org",
        "@type": "BreadcrumbList",
        "itemListElement": [
            {
                "@type": "ListItem",
                "position": 1,
                "name": copy["home"],
                "item": home_url,
            },
            {
                "@type": "ListItem",
                "position": 2,
                "name": copy["breadcrumb"],
                "item": canonical,
            },
        ],
    }
    return json.dumps(payload, ensure_ascii=False, separators=(",", ":"))


def _masthead(lang: str, copy: dict[str, str]) -> str:
    home_path = "/en/" if lang == "en" else "/"
    home_word = "home" if lang == "en" else "accueil"
    return f'''<header class="candidate-masthead" aria-label="France 2027 Signal Lab">
      <a class="candidate-brand" href="{home_path}" aria-label="France 2027 Signal Lab — {home_word}">
        <span class="candidate-mark" aria-hidden="true"><svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 32 32" focusable="false"><rect x="1" y="1" width="30" height="30" rx="8" fill="#071522"/><path d="M6 16A10 10 0 0 1 16 6M26 16A10 10 0 0 1 16 26" fill="none" stroke="#268cff" stroke-width="2" stroke-linecap="round"/><path d="M10 16A6 6 0 0 1 16 10M22 16A6 6 0 0 1 16 22" fill="none" stroke="#35d5ff" stroke-width="2" stroke-linecap="round"/><circle cx="16" cy="16" r="2.5" fill="#35d5ff"/></svg></span>
        <span class="candidate-brand-copy"><strong>FRANCE 2027 <em>SIGNAL LAB</em></strong><small>{_h(copy["brand_note"])}</small></span>
      </a>
      <div class="candidate-masthead-tools">
        <nav class="candidate-language" aria-label="{_h(copy["language_label"])}"><a href="/candidates/" lang="fr" hreflang="fr" aria-label="Français"{' aria-current="page"' if lang == 'fr' else ''}>FR</a><span aria-hidden="true">|</span><a href="/en/candidates/" lang="en" hreflang="en" aria-label="English"{' aria-current="page"' if lang == 'en' else ''}>EN</a></nav>
        <div class="candidate-countdown" data-countdown aria-label="{_h(copy["countdown_aria"])}">
          <span class="candidate-countdown-icon" aria-hidden="true"><svg viewBox="0 0 24 24" focusable="false"><rect x="4" y="6" width="16" height="14" rx="2"></rect><path d="M8 3v5M16 3v5M4 10h16"></path><path d="M8 14h2M12 14h2M16 14h1M8 17h2M12 17h2"></path></svg></span>
          <div class="candidate-countdown-copy"><strong class="candidate-countdown-value">—</strong><div class="candidate-countdown-text"><div class="candidate-countdown-line"><span class="candidate-countdown-unit">{_h(copy["countdown_unit"])}</span><span class="candidate-countdown-label">{_h(copy["countdown_label"])}</span></div><div class="candidate-countdown-date"><span>{_h(copy["countdown_date"])}</span><span class="candidate-tooltip-mark" aria-hidden="true">i</span></div></div></div>
        </div>
      </div>
    </header>'''


def render_candidate_hud(lang: str, domains: int) -> str:
    """Render the current-main Polling Lab HUD contract for candidate pages."""

    if lang == "fr":
        return f'''<footer id="candidate-app-hud" class="fr27-app-hud" data-expanded="true" aria-label="Dock système France 2027 Signal Lab">
      <button class="fr27-app-hud-toggle" id="fr27-app-hud-toggle" type="button" aria-expanded="true" aria-controls="fr27-app-hud-surface" aria-label="Réduire le dock système" data-fr27-tooltip="Réduire le dock système"><svg viewBox="0 0 24 24" aria-hidden="true" focusable="false"><path d="M6.5 8.5 12 14l5.5-5.5"></path></svg></button>
      <div class="fr27-app-hud-surface" id="fr27-app-hud-surface">
        <div class="fr27-app-hud-content fr27-linear-console" aria-hidden="false">
          <section class="fr27-linear-zone fr27-zone-live" aria-label="Heure de Paris"><div class="fr27-zone-meta"><span>PARIS</span><span>/ <span id="fr27-hud-paris-zone">UTC+2</span></span></div><div class="fr27-zone-main fr27-live-main"><time id="fr27-hud-paris-time" datetime="">--:--:--</time><span id="fr27-hud-paris-date">—</span></div></section>
          <section class="fr27-linear-zone fr27-zone-countdown" aria-label="Compte à rebours électoral"><div class="fr27-zone-title">COMPTE À REBOURS</div><div class="fr27-zone-main fr27-countdown-main"><div class="fr27-countdown-value-row"><strong id="fr27-hud-countdown-days">—</strong><span class="fr27-countdown-unit">JOURS</span></div><time class="fr27-countdown-date" datetime="2027-04-18">18 AVR 2027</time></div></section>
          <section class="fr27-linear-zone fr27-zone-infra" aria-label="Univers de sources et sondages"><div class="fr27-zone-infra-body"><div class="fr27-source-main">
            <div class="fr27-source-stat"><strong id="fr27-hud-domains-value">{domains}</strong><span class="fr27-source-icon" aria-hidden="true"><svg viewBox="0 0 24 24" focusable="false"><circle cx="12" cy="12" r="8"></circle><path d="M4 12h16"></path><path d="M12 4c2.2 2.2 3.3 4.9 3.3 8s-1.1 5.8-3.3 8"></path><path d="M12 4c-2.2 2.2-3.3 4.9-3.3 8s1.1 5.8 3.3 8"></path></svg></span><span class="fr27-hud-label-with-info" id="fr27-hud-domains-info" data-fr27-tooltip="Domaines éditeurs approuvés configurés dans l’univers de sources FR27. Il s’agit du registre surveillé, pas du nombre d’éditeurs représentés dans les actualités électorales retenues." data-fr27-tooltip-affordance="term" tabindex="0">DOMAINES</span></div>
            <div class="fr27-source-stat"><strong id="fr27-hud-polls-value">—</strong><span class="fr27-source-icon" aria-hidden="true"><svg viewBox="0 0 24 24" focusable="false"><circle cx="9" cy="8.5" r="3"></circle><path d="M3.5 19c.6-3.3 2.4-5 5.5-5s4.9 1.7 5.5 5"></path><path d="M16 6.5a2.7 2.7 0 0 1 0 5.4"></path><path d="M15.5 14c2.7.3 4.2 1.8 4.8 4.5"></path></svg></span><span class="fr27-hud-label-with-info" id="fr27-hud-polls-info" data-fr27-tooltip="Paquets de sondages de premier tour distincts dans le corpus chargé, et non instituts. Les hypothèses partageant institut, dates de terrain et taille d’échantillon comptent pour un paquet." data-fr27-tooltip-affordance="term" tabindex="0">SONDAGES</span></div>
          </div></div></section>
          <section class="fr27-linear-zone fr27-zone-dashboard" aria-label="Tableau de bord principal"><a class="fr27-dashboard-cta" href="https://france2027.app/"><span>TABLEAU DE BORD</span><strong>OUVRIR LE MONITEUR ↗</strong></a></section>
          <section class="fr27-linear-zone fr27-zone-utility" aria-label="Liens utilitaires"><div class="fr27-linear-actions">
            <a class="fr27-hud-command github" href="https://github.com/openeventbits/france-2027-signal-lab" target="_blank" rel="noreferrer" data-fr27-tooltip="Voir le dépôt" aria-label="Ouvrir le dépôt GitHub"><svg viewBox="0 0 24 24" aria-hidden="true" focusable="false"><path fill="currentColor" d="M12 .5a12 12 0 0 0-3.79 23.39c.6.11.82-.26.82-.58v-2.04c-3.34.73-4.04-1.42-4.04-1.42-.55-1.37-1.33-1.73-1.33-1.73-1.09-.74.08-.73.08-.73 1.2.08 1.83 1.21 1.83 1.21 1.08 1.82 2.82 1.29 3.5.99.11-.76.42-1.29.76-1.59-2.67-.3-5.48-1.31-5.48-5.84 0-1.29.47-2.34 1.23-3.16-.12-.3-.53-1.53.12-3.18 0 0 1.01-.32 3.3 1.21a11.6 11.6 0 0 1 6 0c2.29-1.53 3.3-1.21 3.3-1.21.65 1.65.24 2.88.12 3.18.77.82 1.23 1.87 1.23 3.16 0 4.54-2.81 5.54-5.49 5.84.43.37.81 1.09.81 2.19v3.25c0 .32.22.7.83.58A12 12 0 0 0 12 .5Z"></path></svg></a>
            <button type="button" id="fr27-hud-email-toggle" class="fr27-hud-command email" data-fr27-tooltip="Contact" aria-label="Contacter France 2027 Signal Lab" aria-haspopup="dialog" aria-controls="fr27-hud-contact-popover" aria-expanded="false"><svg viewBox="0 0 24 24" aria-hidden="true" focusable="false"><rect x="3.25" y="5.5" width="17.5" height="13" rx="1.7"></rect><path d="m4.6 7.1 7.4 5.55 7.4-5.55"></path></svg></button>
            <a id="fr27-hud-share" class="fr27-hud-command share" href="https://x.com/fr27signal" target="_blank" rel="noopener noreferrer" data-fr27-tooltip="FR27 sur X · @fr27signal" aria-label="FR27 sur X · @fr27signal"><svg viewBox="0 0 24 24" aria-hidden="true" focusable="false"><path fill="currentColor" stroke="none" d="M18.244 2.25h3.308l-7.227 8.26 8.502 11.24H16.17l-5.214-6.817L4.99 21.75H1.68l7.73-8.835L1.264 2.25H8.09l4.713 6.231zm-1.161 17.52h1.833L7.095 4.126H5.127z"></path></svg></a>
            <button type="button" id="fr27-hud-info-toggle" class="fr27-hud-command" aria-haspopup="dialog" aria-controls="fr27-hud-info-popover" aria-expanded="false" data-fr27-tooltip="À propos de France 2027 Signal Lab" aria-label="Informations sur le projet"><svg class="fr27-info-icon" viewBox="0 0 24 24" aria-hidden="true" focusable="false"><circle cx="12" cy="12" r="8.25"></circle><path d="M12 10.8v5"></path><path d="M12 7.7h.01"></path></svg></button>
          </div></section>
        </div>
        <div class="fr27-app-hud-rail" aria-hidden="true"><i></i></div>
      </div>
      <aside class="fr27-hud-contact-popover" id="fr27-hud-contact-popover" aria-hidden="true" aria-label="Contacter France 2027 Signal Lab"><div class="fr27-hud-contact-head"><strong>CONTACT</strong><span>EMAIL</span></div><div class="fr27-hud-contact-address">contact@france2027.app</div><button type="button" class="fr27-hud-contact-copy" id="fr27-hud-contact-copy" aria-live="polite">COPIER L’ADRESSE</button></aside>
      <aside class="fr27-hud-info-popover" id="fr27-hud-info-popover" aria-hidden="true" aria-label="Informations sur le projet"><div class="fr27-hud-info-head"><strong>FRANCE 2027 SIGNAL LAB</strong><span>INTERFACE PUBLIQUE DE SUIVI</span></div><p>Suivi sourcé de la présidentielle française de 2027 à partir de sondages, d’éléments de campagne, de médias et de données d’attention publique.</p><div class="fr27-hud-info-rules"><div class="fr27-hud-info-rule-line primary"><span>DONNÉES PUBLIQUES</span><span>LIÉES AUX SOURCES</span><span>DESCRIPTIF</span></div><div class="fr27-hud-info-rule-line boundary"><span>AUCUNE MOYENNE DE SONDAGES</span><span>AUCUNE PRÉVISION</span><span>AUCUN CONSEIL DE VOTE</span></div></div><small class="fr27-hud-info-independence">Projet indépendant · aucune affiliation avec les candidats, partis, instituts de sondage, éditeurs ou autorités publiques suivis.</small><small class="fr27-hud-info-note">Les portraits des candidates et candidats sont des illustrations générées par IA à des fins d’identification visuelle.</small><div class="fr27-hud-info-rights"><strong>DROITS &amp; LICENCES</strong><span>POLYFORM NC · CC BY-NC 4.0</span><a href="https://github.com/openeventbits/france-2027-signal-lab/blob/main/NOTICE" target="_blank" rel="noopener noreferrer" aria-label="Ouvrir les détails des droits et licences dans un nouvel onglet">DÉTAILS ↗</a></div></aside>
      <div class="visually-hidden">Données descriptives issues de sources publiques. Aucune moyenne. Aucune prévision. Aucun conseil de vote.</div>
    </footer>'''

    if lang == "en":
        return f'''<footer id="candidate-app-hud" class="fr27-app-hud" data-expanded="true" aria-label="France 2027 Signal Lab system dock">
      <button class="fr27-app-hud-toggle" id="fr27-app-hud-toggle" type="button" aria-expanded="true" aria-controls="fr27-app-hud-surface" aria-label="Collapse system dock" data-fr27-tooltip="Collapse system dock"><svg viewBox="0 0 24 24" aria-hidden="true" focusable="false"><path d="M6.5 8.5 12 14l5.5-5.5"></path></svg></button>
      <div class="fr27-app-hud-surface" id="fr27-app-hud-surface">
        <div class="fr27-app-hud-content fr27-linear-console" aria-hidden="false">
          <section class="fr27-linear-zone fr27-zone-live" aria-label="Paris time"><div class="fr27-zone-meta"><span>PARIS</span><span>/ <span id="fr27-hud-paris-zone">UTC+2</span></span></div><div class="fr27-zone-main fr27-live-main"><time id="fr27-hud-paris-time" datetime="">--:--:--</time><span id="fr27-hud-paris-date">—</span></div></section>
          <section class="fr27-linear-zone fr27-zone-countdown" aria-label="Election countdown"><div class="fr27-zone-title">COUNTDOWN</div><div class="fr27-zone-main fr27-countdown-main"><div class="fr27-countdown-value-row"><strong id="fr27-hud-countdown-days">—</strong><span class="fr27-countdown-unit">DAYS</span></div><time class="fr27-countdown-date" datetime="2027-04-18">18 APR 2027</time></div></section>
          <section class="fr27-linear-zone fr27-zone-infra" aria-label="Source and polling universe"><div class="fr27-zone-infra-body"><div class="fr27-source-main">
            <div class="fr27-source-stat"><strong id="fr27-hud-domains-value">{domains}</strong><span class="fr27-source-icon" aria-hidden="true"><svg viewBox="0 0 24 24" focusable="false"><circle cx="12" cy="12" r="8"></circle><path d="M4 12h16"></path><path d="M12 4c2.2 2.2 3.3 4.9 3.3 8s-1.1 5.8-3.3 8"></path><path d="M12 4c-2.2 2.2-3.3 4.9-3.3 8s1.1 5.8 3.3 8"></path></svg></span><span class="fr27-hud-label-with-info" id="fr27-hud-domains-info" data-fr27-tooltip="Approved publisher domains configured in the FR27 source universe. This is the monitored source registry, not the number of publishers represented in accepted election news." data-fr27-tooltip-affordance="term" tabindex="0">DOMAINS</span></div>
            <div class="fr27-source-stat"><strong id="fr27-hud-polls-value">—</strong><span class="fr27-source-icon" aria-hidden="true"><svg viewBox="0 0 24 24" focusable="false"><circle cx="9" cy="8.5" r="3"></circle><path d="M3.5 19c.6-3.3 2.4-5 5.5-5s4.9 1.7 5.5 5"></path><path d="M16 6.5a2.7 2.7 0 0 1 0 5.4"></path><path d="M15.5 14c2.7.3 4.2 1.8 4.8 4.5"></path></svg></span><span class="fr27-hud-label-with-info" id="fr27-hud-polls-info" data-fr27-tooltip="Distinct first-round poll packages in the loaded poll corpus, not pollsters. Reported hypotheses sharing the same pollster, fieldwork dates and sample size count as one poll package." data-fr27-tooltip-affordance="term" tabindex="0">POLLS</span></div>
          </div></div></section>
          <section class="fr27-linear-zone fr27-zone-dashboard" aria-label="Main dashboard"><a class="fr27-dashboard-cta" href="https://france2027.app/en/"><span>DASHBOARD</span><strong>OPEN THE MONITOR ↗</strong></a></section>
          <section class="fr27-linear-zone fr27-zone-utility" aria-label="Utility links"><div class="fr27-linear-actions">
            <a class="fr27-hud-command github" href="https://github.com/openeventbits/france-2027-signal-lab" target="_blank" rel="noreferrer" data-fr27-tooltip="View repository" aria-label="Open GitHub repository"><svg viewBox="0 0 24 24" aria-hidden="true" focusable="false"><path fill="currentColor" d="M12 .5a12 12 0 0 0-3.79 23.39c.6.11.82-.26.82-.58v-2.04c-3.34.73-4.04-1.42-4.04-1.42-.55-1.37-1.33-1.73-1.33-1.73-1.09-.74.08-.73.08-.73 1.2.08 1.83 1.21 1.83 1.21 1.08 1.82 2.82 1.29 3.5.99.11-.76.42-1.29.76-1.59-2.67-.3-5.48-1.31-5.48-5.84 0-1.29.47-2.34 1.23-3.16-.12-.3-.53-1.53.12-3.18 0 0 1.01-.32 3.3 1.21a11.6 11.6 0 0 1 6 0c2.29-1.53 3.3-1.21 3.3-1.21.65 1.65.24 2.88.12 3.18.77.82 1.23 1.87 1.23 3.16 0 4.54-2.81 5.54-5.49 5.84.43.37.81 1.09.81 2.19v3.25c0 .32.22.7.83.58A12 12 0 0 0 12 .5Z"></path></svg></a>
            <button type="button" id="fr27-hud-email-toggle" class="fr27-hud-command email" data-fr27-tooltip="Contact" aria-label="Contact France 2027 Signal Lab" aria-haspopup="dialog" aria-controls="fr27-hud-contact-popover" aria-expanded="false"><svg viewBox="0 0 24 24" aria-hidden="true" focusable="false"><rect x="3.25" y="5.5" width="17.5" height="13" rx="1.7"></rect><path d="m4.6 7.1 7.4 5.55 7.4-5.55"></path></svg></button>
            <a id="fr27-hud-share" class="fr27-hud-command share" href="https://x.com/fr27signal" target="_blank" rel="noopener noreferrer" data-fr27-tooltip="FR27 sur X · @fr27signal" aria-label="FR27 sur X · @fr27signal"><svg viewBox="0 0 24 24" aria-hidden="true" focusable="false"><path fill="currentColor" stroke="none" d="M18.244 2.25h3.308l-7.227 8.26 8.502 11.24H16.17l-5.214-6.817L4.99 21.75H1.68l7.73-8.835L1.264 2.25H8.09l4.713 6.231zm-1.161 17.52h1.833L7.095 4.126H5.127z"></path></svg></a>
            <button type="button" id="fr27-hud-info-toggle" class="fr27-hud-command" aria-haspopup="dialog" aria-controls="fr27-hud-info-popover" aria-expanded="false" data-fr27-tooltip="About France 2027 Signal Lab" aria-label="Project information"><svg class="fr27-info-icon" viewBox="0 0 24 24" aria-hidden="true" focusable="false"><circle cx="12" cy="12" r="8.25"></circle><path d="M12 10.8v5"></path><path d="M12 7.7h.01"></path></svg></button>
          </div></section>
        </div>
        <div class="fr27-app-hud-rail" aria-hidden="true"><i></i></div>
      </div>
      <aside class="fr27-hud-contact-popover" id="fr27-hud-contact-popover" aria-hidden="true" aria-label="Contact France 2027 Signal Lab"><div class="fr27-hud-contact-head"><strong>CONTACT</strong><span>EMAIL</span></div><div class="fr27-hud-contact-address">contact@france2027.app</div><button type="button" class="fr27-hud-contact-copy" id="fr27-hud-contact-copy" aria-live="polite">COPY ADDRESS</button></aside>
      <aside class="fr27-hud-info-popover" id="fr27-hud-info-popover" aria-hidden="true" aria-label="Project information"><div class="fr27-hud-info-head"><strong>FRANCE 2027 SIGNAL LAB</strong><span>PUBLIC MONITORING INTERFACE</span></div><p>Source-linked monitoring of the French 2027 presidential race using published polling, campaign, media and public evidence.</p><div class="fr27-hud-info-rules"><div class="fr27-hud-info-rule-line primary"><span>PUBLIC EVIDENCE</span><span>SOURCE-LINKED</span><span>DESCRIPTIVE</span></div><div class="fr27-hud-info-rule-line boundary"><span>NO POLLING AVERAGES</span><span>NO FORECAST</span><span>NO VOTING ADVICE</span></div></div><small class="fr27-hud-info-independence">Independent project · no affiliation with the candidates, parties, pollsters, publishers or public authorities monitored.</small><small class="fr27-hud-info-note">Candidate portraits are AI-generated illustrations for visual identification.</small><div class="fr27-hud-info-rights"><strong>RIGHTS &amp; LICENSES</strong><span>POLYFORM NC · CC BY-NC 4.0</span><a href="https://github.com/openeventbits/france-2027-signal-lab/blob/main/NOTICE" target="_blank" rel="noopener noreferrer" aria-label="Open rights and license details in a new tab">DETAILS ↗</a></div></aside>
      <div class="visually-hidden">Descriptive data from public sources. No polling averages. No forecast. No voting advice.</div>
    </footer>'''

    raise ValueError(f"unsupported HUD locale: {lang}")
def render_hub(
    model: dict[str, Any],
    *,
    lang: str,
    favicon_markup: str,
    og_image: str,
    hud_metrics: dict[str, int],
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
    main_candidates = [
        candidate
        for candidate in model["candidates"]
        if candidate["status"] != "active_potential"
    ]
    potential_candidates = [
        candidate
        for candidate in model["candidates"]
        if candidate["status"] == "active_potential"
    ]

    directory_candidates = [
        *main_candidates,
        *potential_candidates,
    ]

    potential_count = len(potential_candidates)
    potential_label = copy["show_potential"]

    cards = "\n".join(
        _card(candidate, lang)
        for candidate in directory_candidates
    )

    options = "".join(
        f'<option value="{_h(status)}">{_h(STATUS_LABELS[lang][status])}</option>'
        for status in model["statuses"]
    )
    options += (
        f'<option value="archived">{_h(copy["archived"])}</option>'
    )
    status_counts = model["status_counts"]
    breadcrumb_json_ld = _breadcrumb_json_ld(lang, copy, canonical)

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
  <script type="application/ld+json">{breadcrumb_json_ld}</script>
  <title>{_h(copy["title"])}</title>
  <link rel="stylesheet" href="/assets/fr27-ui.css">
  <link rel="stylesheet" href="/assets/candidate-page-shell.css">
  <link rel="stylesheet" href="/assets/candidate-page.css">
  <link rel="stylesheet" href="/assets/candidate-hub.css">
  <script src="/assets/fr27-ui.js" defer></script>
  <script src="/assets/candidate-hub.js" defer></script>
  <script src="/assets/candidate-hub-directory.js" defer></script>
  <script src="/assets/candidate-family-hud.js" defer></script>
</head>
<body class="candidate-page candidate-hub-page">
  <main class="candidate-shell">
    {_masthead(lang, copy)}

    <nav class="candidate-hub-breadcrumb" aria-label="Breadcrumb"><a href="{'/en/' if lang == 'en' else '/'}">{_h(copy["home"])}</a><span aria-hidden="true">/</span><span aria-current="page">{_h(copy["breadcrumb"])}</span></nav>

    <section class="candidate-hub-intro" aria-labelledby="candidate-hub-title">
      <div class="candidate-hub-eyebrow">{_h(copy["eyebrow"])}</div>
      <div class="candidate-hub-title-row"><h1 id="candidate-hub-title">{_h(copy["heading"])}</h1><span class="candidate-hub-title-info-wrap"><button class="candidate-hub-title-info" type="button" aria-label="{_h(copy["info_label"])}" aria-describedby="candidate-hub-title-note">i</button><span class="candidate-hub-title-tooltip" id="candidate-hub-title-note" role="tooltip">{_h(copy["intro"])}</span></span></div>
    </section>

    <section class="candidate-hub-metrics" aria-label="{_h(copy["count_suffix"])}">
      <div class="candidate-hub-metric"><span>{_h(copy["metric_monitored"])}</span><strong data-candidate-total>{model["count"]}</strong></div>
      <div class="candidate-hub-metric"><span>{_h(copy["metric_declared"])}</span><strong>{status_counts["declared"]}</strong></div>
      <div class="candidate-hub-metric"><span>{_h(copy["metric_selected"])}</span><strong>{status_counts["party_selected"]}</strong></div>
      <div class="candidate-hub-metric"><span>{_h(copy["metric_selection"])}</span><strong>{status_counts["primary_contender"]}</strong></div>
      <div class="candidate-hub-metric"><span>{_h(copy["metric_potential"])}</span><strong>{status_counts["active_potential"]}</strong></div>
    </section>

    <section class="candidate-hub-controls" aria-label="Candidate search and filters">
      <label><span>{_h(copy["search_label"])}</span><input type="search" data-candidate-search placeholder="{_h(copy["search_placeholder"])}" autocomplete="off"></label>
      <label><span>{_h(copy["filter_label"])}</span><select data-candidate-status><option value="">{_h(copy["all"])}</option>{options}</select></label>
      <p class="visually-hidden" aria-live="polite"><strong data-candidate-visible-count>{model["count"]}</strong> {_h(copy["results"])}</p>
      <noscript><p>{_h(copy["no_js"])}</p></noscript>
    </section>

    <section
      class="candidate-hub-grid"
      id="candidate-hub-directory-grid"
      data-candidate-grid
      data-candidate-directory-grid
      aria-label="{_h(copy["heading"])}">
{cards}
    </section>

    <div
      class="candidate-hub-disclosure"
      data-candidate-disclosure
      hidden>
      <button
        type="button"
        class="candidate-hub-more"
        data-candidate-potential-toggle
        data-collapsed-label="{_h(potential_label)}"
        data-expanded-label="{_h(copy["collapse_directory"])}"
        aria-expanded="false">{_h(potential_label)}</button>
    </div>

{render_candidate_hud(lang, hud_metrics["domains"])}
  </main>
</body>
</html>
'''
    return document.encode("utf-8")
