"""Deterministic newsroom products for FR27 X publishing.

This module composes ranked social products from canonical MetricSnapshot
objects. It never derives alternative percentages from raw source artifacts.
"""

from __future__ import annotations

import argparse
import json
import re
import sys
from dataclasses import asdict, dataclass
from datetime import date, timedelta
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[1]

if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

import coverage_metric_contract as contract


# FR27 editorial safety ceiling for Premium long-form X newsroom products.
# This is deliberately stricter than the account/platform capability.
MAX_X_WEIGHTED_LENGTH = 1000
X_URL_WEIGHT = 23
URL_RE = re.compile(r"https?://\S+", re.IGNORECASE)

ISSUES_FR_URL = "https://france2027.app/enjeux/"
ISSUES_EN_URL = "https://france2027.app/en/issues/"
AGENDA_FR_URL = "https://france2027.app/agenda/"
AGENDA_EN_URL = "https://france2027.app/en/agenda/"

AGENDA_EXCLUDED_SOCIAL_IDS = frozenset({
    "polls_race",
})

FR_SHORT_LABELS = {
    "economy_public_finances": "Économie & finances",
    "work_purchasing_power_pensions": "Travail & pouvoir d’achat",
    "immigration_identity_secularism": "Immigration & identité",
    "security_justice": "Sécurité & justice",
    "health_education_public_services": "Santé & services publics",
    "climate_energy_agriculture": "Climat & énergie",
    "europe_defence_foreign_affairs": "Europe & défense",
    "institutions_democracy_territories": "Institutions & démocratie",

    "legal_eligibility": "Justice & éligibilité",
    "selection_strategy": "Primaires & stratégies",
    "candidacies_endorsements": "Candidatures & soutiens",
    "rules_calendar": "Règles & calendrier",
    "positioning_integrity": "Positionnement",
    "polls_race": "Sondages & rapports de force",
}

EN_SHORT_LABELS = {
    "economy_public_finances": "Economy & public finances",
    "work_purchasing_power_pensions": "Work & purchasing power",
    "immigration_identity_secularism": "Immigration & identity",
    "security_justice": "Security & justice",
    "health_education_public_services": "Health & public services",
    "climate_energy_agriculture": "Climate & energy",
    "europe_defence_foreign_affairs": "Europe & defence",
    "institutions_democracy_territories": "Institutions & democracy",

    "legal_eligibility": "Legal cases & eligibility",
    "selection_strategy": "Primaries & party strategy",
    "candidacies_endorsements": "Candidacies & endorsements",
    "rules_calendar": "Rules & calendar",
    "positioning_integrity": "Positioning",
    "polls_race": "Polling & race narratives",
}

FR_MONTHS = (
    "janv.",
    "févr.",
    "mars",
    "avr.",
    "mai",
    "juin",
    "juil.",
    "août",
    "sept.",
    "oct.",
    "nov.",
    "déc.",
)

EN_MONTHS = (
    "Jan",
    "Feb",
    "Mar",
    "Apr",
    "May",
    "Jun",
    "Jul",
    "Aug",
    "Sep",
    "Oct",
    "Nov",
    "Dec",
)


@dataclass(frozen=True)
class NewsroomRow:
    entity_id: str
    label: str
    previous_display: float
    current_display: float
    display_delta: float
    previous_evidence: int
    current_evidence: int
    previous_denominator: int
    current_denominator: int


@dataclass(frozen=True)
class NewsroomProduct:
    product_id: str
    post_type: str

    locale: str
    family: str
    rank_kind: str

    metric_id: str
    aggregation_unit: str
    denominator_id: str
    window_mode: str

    source_artifact: str
    as_of: str

    previous_start: str
    previous_end: str
    current_start: str
    current_end: str

    destination_url: str
    interpretation_boundary: str

    rows: tuple[NewsroomRow, ...]

    score: float
    text: str
    weighted_length: int


def weighted_x_length(text: str) -> int:
    total = 0
    cursor = 0

    for match in URL_RE.finditer(text):
        total += len(text[cursor:match.start()])
        total += X_URL_WEIGHT
        cursor = match.end()

    total += len(text[cursor:])

    return total


def _fr_number(value: float) -> str:
    return f"{value:.1f}".replace(".", ",")


def _fr_delta(value: float) -> str:
    if value > 0:
        prefix = "+"
    elif value < 0:
        prefix = "−"
    else:
        prefix = ""

    rendered = _fr_number(abs(value))

    unit = "pt" if abs(value) < 2 else "pts"

    return f"{prefix}{rendered} {unit}"


def _en_delta(value: float) -> str:
    if value > 0:
        prefix = "+"
    elif value < 0:
        prefix = "−"
    else:
        prefix = ""

    return f"{prefix}{abs(value):.1f} pp"


def _fr_percent(value: float) -> str:
    return f"{_fr_number(value)} %"


def _en_percent(value: float) -> str:
    return f"{value:.1f}%"


def _arrow(value: float) -> str:
    if value > 0:
        return "↑"

    if value < 0:
        return "↓"

    return "•"


def _short_label(
    entity_id: str,
    fallback: str,
    locale: str,
) -> str:
    labels = (
        FR_SHORT_LABELS
        if locale == "fr"
        else EN_SHORT_LABELS
    )

    return labels.get(
        entity_id,
        fallback,
    )


def _date_piece(
    value: str,
    locale: str,
) -> str:
    parsed = date.fromisoformat(value)

    months = (
        FR_MONTHS
        if locale == "fr"
        else EN_MONTHS
    )

    return (
        f"{parsed.day} "
        f"{months[parsed.month - 1]}"
    )


def _range_piece(
    start: str,
    end: str,
    locale: str,
) -> str:
    first = date.fromisoformat(start)
    last = date.fromisoformat(end)

    months = (
        FR_MONTHS
        if locale == "fr"
        else EN_MONTHS
    )

    if first == last:
        return _date_piece(
            start,
            locale,
        )

    if (
        first.month == last.month
        and first.year == last.year
    ):
        return (
            f"{first.day}–{last.day} "
            f"{months[last.month - 1]}"
        )

    return (
        f"{first.day} "
        f"{months[first.month - 1]}"
        f"–"
        f"{last.day} "
        f"{months[last.month - 1]}"
    )


def _period_line(
    snapshot: contract.MetricSnapshot,
    locale: str,
    *,
    compare: bool,
) -> str:
    current = _range_piece(
        snapshot.current_start,
        snapshot.current_end,
        locale,
    )

    if not compare:
        return current

    previous = _range_piece(
        snapshot.previous_start,
        snapshot.previous_end,
        locale,
    )

    years = {
        date.fromisoformat(
            snapshot.current_start
        ).year,
        date.fromisoformat(
            snapshot.current_end
        ).year,
        date.fromisoformat(
            snapshot.previous_start
        ).year,
        date.fromisoformat(
            snapshot.previous_end
        ).year,
    }

    if len(years) == 1:
        return f"{current} vs {previous}"

    return (
        f"{snapshot.current_start}"
        f"→{snapshot.current_end}"
        f" vs "
        f"{snapshot.previous_start}"
        f"→{snapshot.previous_end}"
    )


def _headline(
    *,
    family: str,
    rank_kind: str,
    window_mode: str,
    locale: str,
) -> str:
    weekly = (
        window_mode
        == contract.WINDOW_COMPLETE_WEEK
    )

    if locale == "fr":
        name = "ENJEUX DE CAMPAGNE" if family == "issues" else "AGENDA DE CAMPAGNE"
        horizon = "7 JOURS" if weekly else "24 H"
        if rank_kind == "movers":
            comparison = "7 JOURS PRÉCÉDENTS" if weekly else "24 H PRÉCÉDENTES"
            return f"{name} · {horizon} · VS {comparison}"
        return f"{name} · LE PLUS PRÉSENT · {horizon}"

    if locale == "en":
        if family == "issues":
            if rank_kind == "movers":
                return (
                    "ISSUES IN MOTION 📊"
                    if weekly
                    else "WHAT MOVED IN THE ISSUES 📡"
                )

            return "MOST PRESENT ISSUES 👀"

        if family == "agenda":
            if rank_kind == "movers":
                return (
                    "2027 AGENDA IN MOTION 📊"
                    if weekly
                    else "WHAT MOVED IN THE 2027 AGENDA 📡"
                )

            return "WHAT DOMINATES THE 2027 AGENDA 👀"

    raise ValueError(
        f"unsupported newsroom product: "
        f"{locale}/{family}/{rank_kind}"
    )


def _boundary(
    family: str,
    locale: str,
) -> str:
    if locale == "fr":
        if family == "issues":
            return (
                "Un même article peut relever de plusieurs enjeux."
            )

        if family == "agenda":
            return (
                "Couverture de campagne, pas priorités déclarées des candidats."
            )

    if locale == "en":
        if family == "issues":
            return (
                "Coverage · multilabel · ≠ opinion."
            )

        if family == "agenda":
            return (
                "Coverage · ≠ stated priorities."
            )

    raise ValueError(
        f"unsupported boundary: {locale}/{family}"
    )


def _destination(
    family: str,
    locale: str,
) -> str:
    if family == "issues":
        return (
            ISSUES_FR_URL
            if locale == "fr"
            else ISSUES_EN_URL
        )

    if family == "agenda":
        return (
            AGENDA_FR_URL
            if locale == "fr"
            else AGENDA_EN_URL
        )

    raise ValueError(
        f"unsupported family: {family}"
    )


def _newsroom_rows(
    values: tuple[contract.MetricRow, ...],
    *,
    locale: str,
) -> tuple[NewsroomRow, ...]:
    output = []

    for row in values:
        fallback = (
            row.label_fr
            if locale == "fr"
            else row.label_en
        )

        output.append(
            NewsroomRow(
                entity_id=row.entity_id,
                label=fallback.replace(" & ", " et ") if locale == "fr" else _short_label(
                    row.entity_id,
                    fallback,
                    locale,
                ),
                previous_display=(
                    row.previous_display
                ),
                current_display=(
                    row.current_display
                ),
                display_delta=(
                    row.display_delta
                ),
                previous_evidence=(
                    row.previous_evidence
                ),
                current_evidence=(
                    row.current_evidence
                ),
                previous_denominator=row.previous_denominator,
                current_denominator=row.current_denominator,
            )
        )

    return tuple(output)


def _render_product_text(
    *,
    snapshot: contract.MetricSnapshot,
    family: str,
    rank_kind: str,
    locale: str,
    rows: tuple[NewsroomRow, ...],
    destination_url: str,
) -> str:
    if locale == "fr":
        headline = _headline(family=family, rank_kind=rank_kind,
                            window_mode=snapshot.window_mode, locale=locale)
        # A daily contract with a gap must not be described as adjacent 24 H.
        if snapshot.window_mode == contract.WINDOW_COMPLETE_DAY and (
            snapshot.current_start != snapshot.current_end
            or snapshot.previous_start != snapshot.previous_end
            or date.fromisoformat(snapshot.current_end) - date.fromisoformat(snapshot.previous_end)
            != timedelta(days=1)
        ):
            headline = headline.split(" · ")[0] + " · " + _period_line(
                snapshot, locale, compare=rank_kind == "movers")
        row = rows[0]
        current = _fr_percent(row.current_display)
        if family == "agenda":
            observation = (f"{row.label} : {row.current_evidence}/{row.current_denominator} "
                           f"jours-sources affectés aux thèmes de l’agenda ({current})")
        else:
            observation = (f"{row.label} : présence dans {row.current_evidence} des "
                           f"{row.current_denominator} jours-sources de couverture "
                           f"présidentielle suivis ({current})")
        if rank_kind == "movers":
            observation += (f", contre {row.previous_evidence}/{row.previous_denominator} "
                            f"({_fr_percent(row.previous_display)}). "
                            f"Écart : {_fr_delta(row.display_delta)}.")
        else:
            observation += ", soit le thème le plus présent sur la période."
        parts = [headline, observation]
        parts.append(_boundary(family, locale))
        parts.append(destination_url)
        text = "\n\n".join(parts)
        if weighted_x_length(text) > MAX_X_WEIGHTED_LENGTH:
            raise ValueError("French newsroom observation exceeds X weighted limit")
        return text

    lines = [
        _headline(
            family=family,
            rank_kind=rank_kind,
            window_mode=snapshot.window_mode,
            locale=locale,
        ),
        _period_line(
            snapshot,
            locale,
            compare=(
                rank_kind == "movers"
            ),
        ),
    ]

    if rank_kind == "movers":
        for row in rows:
            if row.display_delta == 0:
                lines.append(
                    f"• {row.label} — stable"
                )
                continue

            if locale == "fr":
                value = _fr_delta(
                    row.display_delta
                )
            else:
                value = _en_delta(
                    row.display_delta
                )

            lines.append(
                f"{_arrow(row.display_delta)} "
                f"{row.label} "
                f"{value}"
            )

    elif rank_kind == "dominance":
        for index, row in enumerate(
            rows,
            start=1,
        ):
            if locale == "fr":
                value = _fr_percent(
                    row.current_display
                )
            else:
                value = _en_percent(
                    row.current_display
                )

            lines.append(
                f"{index}. "
                f"{row.label} — "
                f"{value}"
            )

    else:
        raise ValueError(
            f"unsupported rank kind: {rank_kind}"
        )

    lines.extend([
        "",
        _boundary(
            family,
            locale,
        ),
        destination_url,
    ])

    text = "\n".join(lines)

    length = weighted_x_length(text)

    if length > MAX_X_WEIGHTED_LENGTH and family == "issues":
        # Source-day incidence can yield longer displayed values than the old
        # article metric. Compact row punctuation, preserving every ranked row,
        # value, semantic boundary and complete destination URL.
        for index in range(2, 2 + len(rows)):
            lines[index] = lines[index].replace(" & ", "&")
        text = "\n".join(lines)
        length = weighted_x_length(text)

    if length > MAX_X_WEIGHTED_LENGTH:
        raise ValueError(
            f"{family}/{rank_kind}/"
            f"{snapshot.window_mode}/{locale} "
            f"is too long for X: "
            f"{length}"
        )

    return text


def _make_product(
    *,
    snapshot: contract.MetricSnapshot,
    family: str,
    rank_kind: str,
    locale: str,
) -> NewsroomProduct | None:
    excluded = (
        AGENDA_EXCLUDED_SOCIAL_IDS
        if family == "agenda"
        else ()
    )

    if rank_kind == "movers":
        values = contract.rank_movers(
            snapshot,
            limit=1 if locale == "fr" else 5,
            excluded_entity_ids=excluded,
            require_full=True,
        )

        if len(values) != (1 if locale == "fr" else 5):
            return None

        meaningful = sum(
            1
            for row in values
            if abs(row.display_delta) >= 0.1
        )

        # Keep the existing displayed-movement gate for the selected observation(s).
        if meaningful < (1 if locale == "fr" else 3):
            return None

        score = max(
            abs(row.display_delta)
            for row in values
        )

    elif rank_kind == "dominance":
        limit = 1 if locale == "fr" else (3 if family == "agenda" else 5)

        values = contract.rank_current_share(
            snapshot,
            limit=limit,
            excluded_entity_ids=excluded,
            require_full=True,
        )

        if len(values) != limit:
            return None

        positive = sum(
            1
            for row in values
            if row.current_display > 0
        )

        if positive < min(
            3,
            limit,
        ):
            return None

        score = values[0].current_display

    else:
        raise ValueError(
            f"unsupported rank kind: {rank_kind}"
        )

    rows = _newsroom_rows(
        values,
        locale=locale,
    )

    destination_url = _destination(
        family,
        locale,
    )

    text = _render_product_text(
        snapshot=snapshot,
        family=family,
        rank_kind=rank_kind,
        locale=locale,
        rows=rows,
        destination_url=destination_url,
    )

    post_type = (
        f"{family}_"
        f"{rank_kind}_"
        f"{snapshot.window_mode}"
    )

    product_id = (
        f"{post_type}:"
        f"{snapshot.metric_id}:"
        f"{snapshot.current_end}:"
        f"{locale}"
    )

    boundary = (
        snapshot.interpretation_boundary_fr
        if locale == "fr"
        else snapshot.interpretation_boundary_en
    )

    return NewsroomProduct(
        product_id=product_id,
        post_type=post_type,
        locale=locale,
        family=family,
        rank_kind=rank_kind,
        metric_id=snapshot.metric_id,
        aggregation_unit=(
            snapshot.aggregation_unit
        ),
        denominator_id=(
            snapshot.denominator_id
        ),
        window_mode=(
            snapshot.window_mode
        ),
        source_artifact=(
            snapshot.source_artifact
        ),
        as_of=snapshot.as_of,
        previous_start=(
            snapshot.previous_start
        ),
        previous_end=(
            snapshot.previous_end
        ),
        current_start=(
            snapshot.current_start
        ),
        current_end=(
            snapshot.current_end
        ),
        destination_url=(
            destination_url
        ),
        interpretation_boundary=(
            boundary
        ),
        rows=rows,
        score=float(score),
        text=text,
        weighted_length=(
            weighted_x_length(text)
        ),
    )


def build_newsroom_products(
    *,
    issue_payload: dict[str, Any],
    agenda_payload: dict[str, Any],
    locale: str,
) -> list[NewsroomProduct]:
    if locale not in {
        "fr",
        "en",
    }:
        raise ValueError(
            "locale must be fr or en"
        )

    snapshots = [
        contract.build_issue_metric_snapshot(
            issue_payload,
            window_mode=(
                contract.WINDOW_COMPLETE_DAY
            ),
        ),
        contract.build_agenda_metric_snapshot(
            agenda_payload,
            window_mode=(
                contract.WINDOW_COMPLETE_DAY
            ),
        ),
        contract.build_issue_metric_snapshot(
            issue_payload,
            window_mode=(
                contract.WINDOW_COMPLETE_WEEK
            ),
        ),
        contract.build_agenda_metric_snapshot(
            agenda_payload,
            window_mode=(
                contract.WINDOW_COMPLETE_WEEK
            ),
        ),
    ]

    output = []

    for snapshot in snapshots:
        for rank_kind in (
            "movers",
            "dominance",
        ):
            product = _make_product(
                snapshot=snapshot,
                family=snapshot.family,
                rank_kind=rank_kind,
                locale=locale,
            )

            if product is not None:
                output.append(product)

    return output


def _load_json(
    path: Path,
) -> dict[str, Any]:
    value = json.loads(
        path.read_text(
            encoding="utf-8"
        )
    )

    if not isinstance(
        value,
        dict,
    ):
        raise ValueError(
            f"{path} must contain an object"
        )

    return value


def run_preview(
    args: argparse.Namespace,
) -> int:
    products = build_newsroom_products(
        issue_payload=_load_json(
            ROOT
            / "issue_coverage_history.json"
        ),
        agenda_payload=_load_json(
            ROOT
            / "agenda_coverage_history.json"
        ),
        locale=args.locale,
    )

    print(
        "=== FR27 NEWSROOM PRODUCT PREVIEW ==="
    )
    print(
        f"locale={args.locale}"
    )
    print(
        f"product_count={len(products)}"
    )
    print()

    for index, product in enumerate(
        products,
        start=1,
    ):
        print(
            f"{index}. "
            f"{product.post_type}"
        )
        print(
            f"metric_id={product.metric_id}"
        )
        print(
            f"window={product.window_mode}"
        )
        print(
            f"weighted_length="
            f"{product.weighted_length}"
        )
        print(
            f"score={product.score:.1f}"
        )
        print()
        print(product.text)
        print()
        print("---")
        print()

    if args.json_output:
        target = Path(
            args.json_output
        )

        target.write_text(
            json.dumps(
                [
                    asdict(product)
                    for product in products
                ],
                ensure_ascii=False,
                indent=2,
            )
            + "\n",
            encoding="utf-8",
        )

        print(
            f"json_output={target}"
        )

    return 0


def _parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description=(
            "Preview deterministic FR27 "
            "newsroom X products"
        )
    )

    subparsers = parser.add_subparsers(
        dest="command",
        required=True,
    )

    preview = subparsers.add_parser(
        "preview",
    )

    preview.add_argument(
        "--locale",
        choices=(
            "fr",
            "en",
        ),
        required=True,
    )

    preview.add_argument(
        "--json-output",
    )

    preview.set_defaults(
        func=run_preview
    )

    return parser


def main() -> int:
    args = _parser().parse_args()

    return int(
        args.func(args)
    )


if __name__ == "__main__":
    raise SystemExit(main())
