#!/usr/bin/env python3
from __future__ import annotations

import argparse
import json
import math
from dataclasses import asdict, dataclass
from datetime import date
from pathlib import Path
from typing import Any


ROOT = Path(__file__).resolve().parents[1]

DEFAULT_CANDIDATE_HISTORY = ROOT / "candidate_visibility_history.json"
DEFAULT_ISSUE_HISTORY = ROOT / "issue_coverage_history.json"
DEFAULT_AGENDA_HISTORY = ROOT / "agenda_coverage_history.json"

HORIZONS = {
    "daily": {
        "current_days": 1,
        "prior_days": 1,
        "fr": "DERNIER JOUR COMPLET · VS VEILLE",
        "en": "LATEST COMPLETE DAY · VS PRIOR DAY",
        "weight": 0.55,
    },
    "weekly": {
        "current_days": 7,
        "prior_days": 7,
        "fr": "7 JOURS · VS 7 JOURS PRÉCÉDENTS",
        "en": "7 DAYS · VS PREVIOUS 7 DAYS",
        "weight": 1.20,
    },
    "four_week": {
        "current_days": 14,
        "prior_days": 14,
        "fr": "14 JOURS · VS 14 JOURS PRÉCÉDENTS",
        "en": "14 DAYS · VS PREVIOUS 14 DAYS",
        "weight": 1.10,
    },
}

DELTA_THRESHOLDS = {
    "candidate_visibility": {
        "daily": 1.50,
        "weekly": 0.80,
        "four_week": 0.60,
    },
    "issues": {
        "daily": 2.00,
        "weekly": 1.00,
        "four_week": 0.80,
    },
    "agenda": {
        "daily": 2.00,
        "weekly": 1.00,
        "four_week": 0.80,
    },
}

DENOMINATOR_MINIMUMS = {
    "candidate_visibility": {
        "daily": 25,
        "weekly": 150,
        "four_week": 300,
    },
    "issues": {
        "daily": 20,
        "weekly": 120,
        "four_week": 250,
    },
    "agenda": {
        "daily": 5,
        "weekly": 30,
        "four_week": 60,
    },
}

EVIDENCE_MINIMUMS = {
    "candidate_visibility": {
        "daily": 2,
        "weekly": 5,
        "four_week": 8,
    },
    "issues": {
        "daily": 2,
        "weekly": 5,
        "four_week": 8,
    },
    "agenda": {
        "daily": 2,
        "weekly": 5,
        "four_week": 8,
    },
}


SOCIAL_EXCLUDED_AGENDA_IDS = frozenset({
    "polls_race",
})

DAILY_CURRENT_NUMERATOR_MINIMUMS = {
    "candidate_visibility": 5,
    "issues": 5,
    "agenda": 3,
}


@dataclass(frozen=True)
class Signal:
    family: str
    horizon: str
    entity_id: str
    label_fr: str
    label_en: str
    current_percent: float
    prior_percent: float
    delta_pp: float
    current_numerator: int
    prior_numerator: int
    current_denominator: int
    prior_denominator: int
    current_start: str
    current_end: str
    prior_start: str
    prior_end: str
    score: float


def _load_json(path: Path) -> dict[str, Any]:
    value = json.loads(path.read_text(encoding="utf-8"))

    if not isinstance(value, dict):
        raise ValueError(f"{path} must contain a JSON object")

    return value


def _sorted_dates(values: list[str]) -> list[str]:
    clean = sorted({str(value) for value in values if value})

    for value in clean:
        date.fromisoformat(value)

    return clean


def _window_dates(
    all_dates: list[str],
    horizon: str,
) -> tuple[list[str], list[str]] | None:
    spec = HORIZONS[horizon]

    current_days = int(spec["current_days"])
    prior_days = int(spec["prior_days"])
    required = current_days + prior_days

    if len(all_dates) < required:
        return None

    current = all_dates[-current_days:]
    prior = all_dates[-required:-current_days]

    if len(current) != current_days or len(prior) != prior_days:
        return None

    return current, prior


def _ratio_percent(
    numerator: int,
    denominator: int,
) -> float:
    if denominator <= 0:
        return 0.0

    return (numerator / denominator) * 100.0


def _score_signal(
    *,
    family: str,
    horizon: str,
    delta_pp: float,
    current_numerator: int,
    prior_numerator: int,
) -> float:
    magnitude = abs(delta_pp)
    horizon_weight = float(HORIZONS[horizon]["weight"])

    evidence = max(
        0,
        current_numerator + prior_numerator,
    )

    evidence_bonus = min(
        1.5,
        math.log10(evidence + 1) / 2.0,
    )

    return round(
        magnitude * horizon_weight + evidence_bonus,
        4,
    )


def _eligible(
    *,
    family: str,
    horizon: str,
    delta_pp: float,
    current_numerator: int,
    prior_numerator: int,
    current_denominator: int,
    prior_denominator: int,
) -> bool:
    if abs(delta_pp) < DELTA_THRESHOLDS[family][horizon]:
        return False

    denominator_min = DENOMINATOR_MINIMUMS[family][horizon]

    if current_denominator < denominator_min:
        return False

    if prior_denominator < denominator_min:
        return False

    evidence_min = EVIDENCE_MINIMUMS[family][horizon]

    if current_numerator + prior_numerator < evidence_min:
        return False

    if horizon == "daily":
        current_minimum = (
            DAILY_CURRENT_NUMERATOR_MINIMUMS[family]
        )

        if current_numerator < current_minimum:
            return False

    return True


def _build_signal(
    *,
    family: str,
    horizon: str,
    entity_id: str,
    label_fr: str,
    label_en: str,
    current_numerator: int,
    prior_numerator: int,
    current_denominator: int,
    prior_denominator: int,
    current_dates: list[str],
    prior_dates: list[str],
) -> Signal | None:
    current_percent = _ratio_percent(
        current_numerator,
        current_denominator,
    )

    prior_percent = _ratio_percent(
        prior_numerator,
        prior_denominator,
    )

    delta_pp = current_percent - prior_percent

    if not _eligible(
        family=family,
        horizon=horizon,
        delta_pp=delta_pp,
        current_numerator=current_numerator,
        prior_numerator=prior_numerator,
        current_denominator=current_denominator,
        prior_denominator=prior_denominator,
    ):
        return None

    return Signal(
        family=family,
        horizon=horizon,
        entity_id=entity_id,
        label_fr=label_fr,
        label_en=label_en,
        current_percent=round(current_percent, 4),
        prior_percent=round(prior_percent, 4),
        delta_pp=round(delta_pp, 4),
        current_numerator=current_numerator,
        prior_numerator=prior_numerator,
        current_denominator=current_denominator,
        prior_denominator=prior_denominator,
        current_start=current_dates[0],
        current_end=current_dates[-1],
        prior_start=prior_dates[0],
        prior_end=prior_dates[-1],
        score=_score_signal(
            family=family,
            horizon=horizon,
            delta_pp=delta_pp,
            current_numerator=current_numerator,
            prior_numerator=prior_numerator,
        ),
    )


def candidate_signals(
    payload: dict[str, Any],
) -> list[Signal]:
    lanes = payload.get("lanes") or {}
    lane = lanes.get("campaign_attention") or {}

    denominators = lane.get("daily_denominators") or []

    denominator_by_date = {
        str(row.get("date")): int(row.get("record_count") or 0)
        for row in denominators
        if isinstance(row, dict) and row.get("date")
    }

    all_dates = _sorted_dates(list(denominator_by_date))
    output: list[Signal] = []

    for candidate in payload.get("candidates") or []:
        if not isinstance(candidate, dict):
            continue

        candidate_id = str(candidate.get("candidate_id") or "")
        candidate_name = str(candidate.get("candidate_name") or "")

        if not candidate_id or not candidate_name:
            continue

        series = (
            (candidate.get("campaign_attention") or {})
            .get("daily_series")
            or []
        )

        row_by_date = {
            str(row.get("date")): row
            for row in series
            if isinstance(row, dict) and row.get("date")
        }

        for horizon in HORIZONS:
            windows = _window_dates(all_dates, horizon)

            if windows is None:
                continue

            current_dates, prior_dates = windows

            current_num = sum(
                int((row_by_date.get(day) or {}).get("record_count") or 0)
                for day in current_dates
            )

            prior_num = sum(
                int((row_by_date.get(day) or {}).get("record_count") or 0)
                for day in prior_dates
            )

            current_den = sum(
                denominator_by_date.get(day, 0)
                for day in current_dates
            )

            prior_den = sum(
                denominator_by_date.get(day, 0)
                for day in prior_dates
            )

            signal = _build_signal(
                family="candidate_visibility",
                horizon=horizon,
                entity_id=candidate_id,
                label_fr=candidate_name,
                label_en=candidate_name,
                current_numerator=current_num,
                prior_numerator=prior_num,
                current_denominator=current_den,
                prior_denominator=prior_den,
                current_dates=current_dates,
                prior_dates=prior_dates,
            )

            if signal is not None:
                output.append(signal)

    return output


def issue_signals(
    payload: dict[str, Any],
) -> list[Signal]:
    corpus = payload.get("corpus") or {}

    corpus_daily = corpus.get("daily") or []

    denominator_by_date = {
        str(row.get("date")): int(row.get("item_count") or 0)
        for row in corpus_daily
        if isinstance(row, dict) and row.get("date")
    }

    all_dates = _sorted_dates(list(denominator_by_date))
    output: list[Signal] = []

    for issue in payload.get("issues") or []:
        if not isinstance(issue, dict):
            continue

        entity_id = str(issue.get("id") or "")
        labels = issue.get("labels") or {}

        label_fr = str(labels.get("fr") or entity_id)
        label_en = str(labels.get("en") or label_fr)

        row_by_date = {
            str(row.get("date")): row
            for row in issue.get("daily") or []
            if isinstance(row, dict) and row.get("date")
        }

        for horizon in HORIZONS:
            windows = _window_dates(all_dates, horizon)

            if windows is None:
                continue

            current_dates, prior_dates = windows

            current_num = sum(
                int((row_by_date.get(day) or {}).get("item_count") or 0)
                for day in current_dates
            )

            prior_num = sum(
                int((row_by_date.get(day) or {}).get("item_count") or 0)
                for day in prior_dates
            )

            current_den = sum(
                denominator_by_date.get(day, 0)
                for day in current_dates
            )

            prior_den = sum(
                denominator_by_date.get(day, 0)
                for day in prior_dates
            )

            signal = _build_signal(
                family="issues",
                horizon=horizon,
                entity_id=entity_id,
                label_fr=label_fr,
                label_en=label_en,
                current_numerator=current_num,
                prior_numerator=prior_num,
                current_denominator=current_den,
                prior_denominator=prior_den,
                current_dates=current_dates,
                prior_dates=prior_dates,
            )

            if signal is not None:
                output.append(signal)

    return output


def agenda_signals(
    payload: dict[str, Any],
) -> list[Signal]:
    activity = payload.get("daily") or []

    denominator_by_date = {
        str(row.get("date")): int(
            row.get("total_classified_agenda_items") or 0
        )
        for row in activity
        if isinstance(row, dict) and row.get("date")
    }

    all_dates = _sorted_dates(list(denominator_by_date))
    output: list[Signal] = []

    for topic in payload.get("topics") or []:
        if not isinstance(topic, dict):
            continue

        entity_id = str(topic.get("id") or "")

        if entity_id in SOCIAL_EXCLUDED_AGENDA_IDS:
            continue

        labels = topic.get("labels") or {}

        label_fr = str(labels.get("fr") or entity_id)
        label_en = str(labels.get("en") or label_fr)

        row_by_date = {
            str(row.get("date")): row
            for row in topic.get("daily") or []
            if isinstance(row, dict) and row.get("date")
        }

        for horizon in HORIZONS:
            windows = _window_dates(all_dates, horizon)

            if windows is None:
                continue

            current_dates, prior_dates = windows

            current_num = sum(
                int((row_by_date.get(day) or {}).get("item_count") or 0)
                for day in current_dates
            )

            prior_num = sum(
                int((row_by_date.get(day) or {}).get("item_count") or 0)
                for day in prior_dates
            )

            current_den = sum(
                denominator_by_date.get(day, 0)
                for day in current_dates
            )

            prior_den = sum(
                denominator_by_date.get(day, 0)
                for day in prior_dates
            )

            signal = _build_signal(
                family="agenda",
                horizon=horizon,
                entity_id=entity_id,
                label_fr=label_fr,
                label_en=label_en,
                current_numerator=current_num,
                prior_numerator=prior_num,
                current_denominator=current_den,
                prior_denominator=prior_den,
                current_dates=current_dates,
                prior_dates=prior_dates,
            )

            if signal is not None:
                output.append(signal)

    return output


def build_all_signals(
    *,
    candidate_payload: dict[str, Any],
    issue_payload: dict[str, Any],
    agenda_payload: dict[str, Any],
) -> list[Signal]:
    values = [
        *candidate_signals(candidate_payload),
        *issue_signals(issue_payload),
        *agenda_signals(agenda_payload),
    ]

    return sorted(
        values,
        key=lambda item: (
            -item.score,
            item.family,
            item.horizon,
            item.entity_id,
        ),
    )


def lane_winners(
    signals: list[Signal],
) -> list[Signal]:
    winners: dict[tuple[str, str], Signal] = {}

    for signal in signals:
        key = (signal.family, signal.horizon)

        previous = winners.get(key)

        if previous is None or signal.score > previous.score:
            winners[key] = signal

    return sorted(
        winners.values(),
        key=lambda item: (
            -item.score,
            item.family,
            item.horizon,
        ),
    )


def select_signals(
    signals: list[Signal],
    *,
    limit: int,
    distinct_families: bool = False,
) -> list[Signal]:
    winners = lane_winners(signals)

    selected: list[Signal] = []
    family_counts: dict[str, int] = {}
    used_entities: set[tuple[str, str]] = set()
    used_families: set[str] = set()

    for signal in winners:
        entity_key = (
            signal.family,
            signal.entity_id,
        )

        if entity_key in used_entities:
            continue

        if (
            distinct_families
            and signal.family in used_families
        ):
            continue

        count = family_counts.get(
            signal.family,
            0,
        )

        if count >= 3:
            continue

        selected.append(signal)

        used_entities.add(entity_key)
        used_families.add(signal.family)

        family_counts[signal.family] = (
            count + 1
        )

        if len(selected) >= limit:
            break

    return selected


def _fr_number(value: float) -> str:
    return f"{value:.1f}".replace(".", ",")


def _signed_fr(value: float) -> str:
    if value > 0:
        return "+" + _fr_number(value)

    return _fr_number(value).replace("-", "−")


def _signed_en(value: float) -> str:
    if value > 0:
        return f"+{value:.1f}"

    return f"{value:.1f}".replace("-", "−")


def _period_fr(signal: Signal) -> str:
    if signal.current_start == signal.current_end:
        return signal.current_end

    return f"{signal.current_start} → {signal.current_end}"


def _period_en(signal: Signal) -> str:
    return _period_fr(signal)


def render_fr(signal: Signal) -> str:
    horizon = str(HORIZONS[signal.horizon]["fr"])

    if signal.family == "candidate_visibility":
        body = (
            f"VISIBILITÉ CANDIDATS · {horizon}\n\n"
            f"{signal.label_fr} : "
            f"{signal.current_numerator}/{signal.current_denominator} "
            f"articles de campagne liés à un candidat "
            f"({_fr_number(signal.current_percent)} %), contre "
            f"{signal.prior_numerator}/{signal.prior_denominator} "
            f"({_fr_number(signal.prior_percent)} %). "
            f"Écart : {_signed_fr(signal.delta_pp)} pts.\n\n"
            f"FR27 · {_period_fr(signal)}"
        )
        return body

    if signal.family == "issues":
        body = (
            f"ENJEUX · {horizon}\n\n"
            f"{signal.label_fr} : "
            f"{signal.current_numerator}/{signal.current_denominator} "
            f"articles du corpus électoral FR27 "
            f"({_fr_number(signal.current_percent)} %), contre "
            f"{signal.prior_numerator}/{signal.prior_denominator} "
            f"({_fr_number(signal.prior_percent)} %). "
            f"Écart : {_signed_fr(signal.delta_pp)} pts.\n\n"
            f"FR27 · {_period_fr(signal)}"
        )
        return body

    if signal.family == "agenda":
        body = (
            f"AGENDA DE CAMPAGNE · {horizon}\n\n"
            f"{signal.label_fr} : "
            f"{signal.current_numerator}/{signal.current_denominator} "
            f"articles classés dans l’agenda "
            f"({_fr_number(signal.current_percent)} %), contre "
            f"{signal.prior_numerator}/{signal.prior_denominator} "
            f"({_fr_number(signal.prior_percent)} %). "
            f"Écart : {_signed_fr(signal.delta_pp)} pts.\n\n"
            f"FR27 · {_period_fr(signal)}"
        )
        return body

    raise ValueError(f"unsupported family: {signal.family}")


def render_en(signal: Signal) -> str:
    horizon = str(HORIZONS[signal.horizon]["en"])

    if signal.family == "candidate_visibility":
        return (
            f"CANDIDATE VISIBILITY · {horizon}\n\n"
            f"{signal.label_en}: "
            f"{signal.current_numerator}/{signal.current_denominator} "
            f"candidate-linked campaign articles "
            f"({signal.current_percent:.1f}%), versus "
            f"{signal.prior_numerator}/{signal.prior_denominator} "
            f"({signal.prior_percent:.1f}%). "
            f"Change: {_signed_en(signal.delta_pp)} pp.\n\n"
            f"FR27 · {_period_en(signal)}"
        )

    if signal.family == "issues":
        return (
            f"ISSUES · {horizon}\n\n"
            f"{signal.label_en}: "
            f"{signal.current_numerator}/{signal.current_denominator} "
            f"articles in FR27’s election-news corpus "
            f"({signal.current_percent:.1f}%), versus "
            f"{signal.prior_numerator}/{signal.prior_denominator} "
            f"({signal.prior_percent:.1f}%). "
            f"Change: {_signed_en(signal.delta_pp)} pp.\n\n"
            f"FR27 · {_period_en(signal)}"
        )

    if signal.family == "agenda":
        return (
            f"CAMPAIGN AGENDA · {horizon}\n\n"
            f"{signal.label_en}: "
            f"{signal.current_numerator}/{signal.current_denominator} "
            f"classified campaign-agenda articles "
            f"({signal.current_percent:.1f}%), versus "
            f"{signal.prior_numerator}/{signal.prior_denominator} "
            f"({signal.prior_percent:.1f}%). "
            f"Change: {_signed_en(signal.delta_pp)} pp.\n\n"
            f"FR27 · {_period_en(signal)}"
        )

    raise ValueError(f"unsupported family: {signal.family}")


def _print_signal(
    signal: Signal,
    *,
    locale: str,
    index: int,
) -> None:
    renderer = render_fr if locale == "fr" else render_en

    print(
        f"{index}. "
        f"family={signal.family} "
        f"horizon={signal.horizon} "
        f"score={signal.score:.3f} "
        f"delta={signal.delta_pp:+.3f}pp "
        f"evidence={signal.current_numerator}/{signal.current_denominator}"
    )

    print(renderer(signal))
    print("---")


def run_preview(args: argparse.Namespace) -> int:
    candidate_payload = _load_json(Path(args.candidate_history))
    issue_payload = _load_json(Path(args.issue_history))
    agenda_payload = _load_json(Path(args.agenda_history))

    signals = build_all_signals(
        candidate_payload=candidate_payload,
        issue_payload=issue_payload,
        agenda_payload=agenda_payload,
    )

    winners = lane_winners(signals)

    fr_selected = select_signals(
        signals,
        limit=args.fr,
    )

    en_selected = select_signals(
        signals,
        limit=args.en,
        distinct_families=True,
    )

    print("=== SIGNAL ENGINE SUMMARY ===")
    print(f"eligible_signals={len(signals)}")
    print(f"lane_winners={len(winners)}")
    print(f"fr_selected={len(fr_selected)}")
    print(f"en_selected={len(en_selected)}")
    print()

    print("=== FR PREVIEW ===")

    for index, signal in enumerate(fr_selected, start=1):
        _print_signal(
            signal,
            locale="fr",
            index=index,
        )

    print()
    print("=== EN PREVIEW ===")

    for index, signal in enumerate(en_selected, start=1):
        _print_signal(
            signal,
            locale="en",
            index=index,
        )

    print()
    print("=== LANE WINNERS ===")

    for signal in winners:
        print(
            f"{signal.family:22} "
            f"{signal.horizon:10} "
            f"{signal.entity_id:36} "
            f"score={signal.score:7.3f} "
            f"delta={signal.delta_pp:+8.3f}pp"
        )

    if args.json_output:
        output = {
            "eligible_signals": [
                asdict(signal)
                for signal in signals
            ],
            "lane_winners": [
                asdict(signal)
                for signal in winners
            ],
            "fr_selected": [
                asdict(signal)
                for signal in fr_selected
            ],
            "en_selected": [
                asdict(signal)
                for signal in en_selected
            ],
        }

        path = Path(args.json_output)

        path.parent.mkdir(
            parents=True,
            exist_ok=True,
        )

        path.write_text(
            json.dumps(
                output,
                ensure_ascii=False,
                indent=2,
            )
            + "\n",
            encoding="utf-8",
        )

        print()
        print(f"json_output={path}")

    return 0


def _parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description="FR27 deterministic X signal engine prototype"
    )

    subparsers = parser.add_subparsers(
        dest="command",
        required=True,
    )

    preview = subparsers.add_parser(
        "preview",
        help="rank and render FR/EN signal candidates",
    )

    preview.add_argument(
        "--candidate-history",
        default=str(DEFAULT_CANDIDATE_HISTORY),
    )

    preview.add_argument(
        "--issue-history",
        default=str(DEFAULT_ISSUE_HISTORY),
    )

    preview.add_argument(
        "--agenda-history",
        default=str(DEFAULT_AGENDA_HISTORY),
    )

    preview.add_argument(
        "--fr",
        type=int,
        default=8,
    )

    preview.add_argument(
        "--en",
        type=int,
        default=2,
    )

    preview.add_argument(
        "--json-output",
    )

    preview.set_defaults(func=run_preview)

    return parser


def main() -> int:
    parser = _parser()
    args = parser.parse_args()
    return int(args.func(args))


if __name__ == "__main__":
    raise SystemExit(main())
