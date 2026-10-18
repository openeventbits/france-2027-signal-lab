"""Read-only, static presentation of the three provider-native histories.

History validation and delta arithmetic remain in the Task-5A provider modules.
Nothing here collects, appends, normalizes or writes provider observations.
"""
from datetime import timedelta
from html import escape
import json

from candidate_history import instant, number, require, delta
import candidate_polymarket_history as polymarket
import candidate_youtube_history as youtube
import candidate_bluesky_history as bluesky


PROVIDERS = {
    "polymarket": (polymarket, "polymarket_candidate_markets.json", "implied_probability",
                   (("market_id", "market_id"), ("yes_token_id", "outcome_id"))),
    "youtube": (youtube, "youtube_candidate_channels.json", "subscriber_count",
                (("channel_id", "channel_id"),)),
    "bluesky": (bluesky, "bluesky_candidate_accounts.json", "followers_count", (("did", "did"),)),
}


def load_histories(root):
    """Separate build inputs: validate full coverage, identities and snapshot parity.

    These are deliberately not candidate projection sources: no JSON duplication.
    Missing or invalid input fails the build, rather than hiding corrupt history.
    """
    def read(name):
        return json.loads((root / name).read_text(encoding="utf-8"))
    ids = {row["candidate_id"] for row in read("candidate_candidacy_status.json")["candidates"]}
    result = {}
    for provider, (module, mapping, _, _) in PROVIDERS.items():
        history = read(f"candidate_{provider}_history.json")
        getattr(module, f"validate_candidate_{provider}_history")(
            history, mapping=read(mapping), candidate_ids=ids,
            snapshot=read(f"candidate_{provider}.json"))
        result[provider] = {row["candidate_id"]: row for row in history["candidates"]}
    return result


def current_series(provider, candidate_id, current, histories):
    """Return the reviewed series ending at the authoritative card observation.

    Task-5A validation guarantees this terminal point already exists. Never splice
    identities, replace the headline with a CLOB quote, or synthesize a point.
    """
    if not histories or current.get("status") != "observed":
        return None
    module, _, field, identities = PROVIDERS[provider]
    value = current.get(field)
    if value is None or provider == "youtube" and current.get("hidden_subscriber_count"):
        return None
    row = histories[provider].get(candidate_id)
    require(row is not None, "missing candidate trend history")
    require(all(row[old] == current.get(new) for old, new in identities), "trend identity mismatch")
    points = row["points"]
    require(bool(points) and instant(points[-1]["observed_at"]) == instant(current["observed_at"])
            and points[-1][field] == value, "trend lacks authoritative current observation")
    change = module.derive_delta(row, 7)
    return (points, field, change) if change is not None else None


def movement_text(provider, change, lang):
    """Visible signed native units and an explicit screen-reader equivalent."""
    fr = lang == "fr"
    if provider == "polymarket":
        magnitude = f"{abs(change):.1f}"
        # A rounded zero has no directional sign.
        sign = "" if float(magnitude) == 0 else "+" if change > 0 else "−"
        magnitude = magnitude.replace(".", ",") if fr else magnitude
        unit = "pt" if sign == "" else "pts"
        visible = f'{sign}{magnitude} {unit} · {"7 j" if fr else "7d"}'
        word = ("plus " if change > 0 else "moins " if change < 0 else "") if fr else (
            "plus " if change > 0 else "minus " if change < 0 else "")
        accessible = (f"Variation sur 7 jours : {word}{magnitude} points de probabilité implicite."
                      if fr else f"Seven-day change: {word}{magnitude} percentage points in implied probability.")
    else:
        magnitude = f"{abs(change):,}"
        magnitude = magnitude.replace(",", "\u202f") if fr else magnitude
        sign = "+" if change > 0 else "−" if change < 0 else ""
        visible = f'{sign}{magnitude} · {"7 j" if fr else "7d"}'
        unit = "abonnés" if fr else "subscribers" if provider == "youtube" else "followers"
        if fr:
            direction = "supplémentaires" if change > 0 else "en moins" if change < 0 else "de variation"
            accessible = f"{magnitude} {unit} {direction} sur 7 jours."
        else:
            direction = "more" if change > 0 else "fewer" if change < 0 else "change in"
            accessible = f"{magnitude} {direction} {unit} over 7 days."
    return visible, accessible


def render_trendline(points, field, label, *, eligible, probability=False):
    """Up to 30 days, true time spacing, no interpolation across gaps >48 hours.

    Coordinates use the visible observation extent, with four-pixel margins and
    ten-percent vertical range padding. Flat series are centered. Singleton gap
    segments are dots, not invented connections. Native values stay untouched.
    """
    ordered = sorted(points, key=lambda p: instant(p["observed_at"]))
    times = [instant(p["observed_at"]) for p in ordered]
    require(len(times) == len(set(times)), "duplicate trend timestamp")
    for point in ordered:
        number(point[field], probability=probability)
    if not eligible or len(ordered) < 2 or delta(ordered, field, 7, probability=probability) is None:
        return ""
    boundary = times[-1] - timedelta(days=30)
    visible = [(t, p[field]) for t, p in zip(times, ordered) if t >= boundary]
    if len(visible) < 2:
        return ""
    start, end = visible[0][0], visible[-1][0]
    low, high = min(v for _, v in visible), max(v for _, v in visible)
    span = high - low
    coordinates = []
    for timestamp, value in visible:
        x = 4 + 232 * (timestamp - start).total_seconds() / (end - start).total_seconds()
        y = 22 if span == 0 else 4 + 36 * ((high - value) / span + .1) / 1.2
        coordinates.append((timestamp, f"{x:.2f}", f"{y:.2f}"))
    segments = [[]]
    for index, (timestamp, x, y) in enumerate(coordinates):
        if index and timestamp - coordinates[index - 1][0] > timedelta(hours=48):
            segments.append([])
        segments[-1].append((x, y))
    shapes = []
    for segment in segments:
        if len(segment) == 1:
            x, y = segment[0]
            shapes.append(f'<circle class="candidate-public-signal-trend-point" cx="{x}" cy="{y}" r="1.5"/>')
        else:
            coords = " ".join(f"{x},{y}" for x, y in segment)
            shapes.append(f'<polyline class="candidate-chart-line" points="{coords}"/>')
    return (f'<svg class="candidate-public-signal-trend" viewBox="0 0 240 44" '
            f'role="img" aria-label="{escape(label, quote=True)}" focusable="false">'
            f'<g aria-hidden="true">{"".join(shapes)}</g></svg>')


def render_movement(provider, candidate_id, current, histories, lang):
    series = current_series(provider, candidate_id, current, histories)
    if series is None:
        return ""
    points, field, change = series
    visible, accessible = movement_text(provider, change, lang)
    measure = {
        "polymarket": ("de la probabilité implicite Polymarket", "Polymarket implied probability"),
        "youtube": ("du nombre d’abonnés YouTube", "YouTube subscriber count"),
        "bluesky": ("du nombre d’abonnés Bluesky", "Bluesky follower count"),
    }[provider]
    label = (f"Évolution sur 30 jours au maximum {measure[0]}. " if lang == "fr" else
             f"Up to 30-day trend in {measure[1]}. ") + accessible
    chart = render_trendline(points, field, label, eligible=True, probability=provider == "polymarket")
    return (f'<p class="candidate-public-signal-change"><span aria-hidden="true">{escape(visible)}</span>'
            f'<span class="visually-hidden">{escape(accessible)}</span></p>{chart}')


def method_note(provider, lang):
    if lang == "fr":
        unit = "Variation en points de pourcentage." if provider == "polymarket" else (
            "Variation du nombre d’abonnés, selon les valeurs arrondies de YouTube." if provider == "youtube" else
            "Variation du nombre d’abonnés Bluesky.")
        return (" La variation compare la valeur actuelle à la dernière observation valide au plus tard sept jours auparavant. "
                "Sans référence suffisante, aucune variation ni courbe n’est affichée. " + unit +
                " Courbe sur 30 jours au maximum, observations réelles espacées dans le temps ; rupture au-delà de 48 h sans observation. "
                "Chaque courbe a sa propre échelle : leurs formes ne sont pas comparables entre plateformes.")
    unit = "Change in percentage points." if provider == "polymarket" else (
        "Subscriber-count change inherits YouTube’s rounding." if provider == "youtube" else "Change in Bluesky follower count.")
    return (" Change compares the current value with the latest valid observation at or before seven days earlier. "
            "Insufficient history produces no change or chart. " + unit +
            " Up to 30 days of actual time-spaced observations; gaps beyond 48 hours break the line. "
            "Each chart has its own scale: shapes cannot be compared across platforms.")
