#!/usr/bin/env python3
from __future__ import annotations

import argparse
import json
import os
import re
import sys
import unicodedata
import urllib.error
import urllib.request
from difflib import SequenceMatcher
from dataclasses import dataclass
from datetime import date, datetime, timedelta, timezone
from pathlib import Path
from typing import Any, Callable, Iterable
from urllib.parse import urlsplit
from zoneinfo import ZoneInfo

BUFFER_ENDPOINT = "https://api.buffer.com"
PARIS = ZoneInfo("Europe/Paris")
MAX_X_WEIGHTED_LENGTH = 280
X_URL_WEIGHT = 23
STATE_SCHEMA_VERSION = 1
URL_RE = re.compile(r"https?://\S+", re.IGNORECASE)
ELIGIBLE_RECENT_CHANGE_CATEGORIES = frozenset({"campaign", "fact_check", "legal"})
GOOGLE_NEWS_HOSTS = frozenset({"news.google.com"})
SOCIAL_STOPWORDS = frozenset({
    "a", "au", "aux", "avec", "ce", "ces", "dans", "de", "des", "du",
    "elle", "en", "et", "est", "il", "la", "le", "les", "leur", "lui",
    "mais", "ne", "ou", "par", "pas", "plus", "pour", "presidentielle",
    "que", "qui", "sa", "se", "ses", "son", "sur", "un", "une", "2027",
})
SOCIAL_CAMPAIGN_ACTION_GROUPS = {
    "candidacy_launch": (
        "je suis candidat",
        "je suis candidate",
        "annonce sa candidature",
        "annonce son intention d etre candidat",
        "se lance dans la course",
        "se lance dans la course a l elysee",
        "lance sa campagne",
        "entree en campagne",
        "entre en campagne",
    ),
    "withdrawal": (
        "renonce a se presenter",
        "renonce a sa candidature",
        "retire sa candidature",
        "retire sa candidature",
    ),
    "suspension": (
        "suspendu temporairement",
        "suspendue temporairement",
        "est suspendu",
        "est suspendue",
    ),
}

FRENCH_MONTHS = (
    "janv.", "févr.", "mars", "avr.", "mai", "juin",
    "juil.", "août", "sept.", "oct.", "nov.", "déc.",
)

AGENDA_SOCIAL_LABELS = {
    "Primaires et stratégies partisanes": "Primaires et stratégies partisanes",
    "Candidatures et soutiens": "Candidatures et soutiens",
    "Sondages et rapports de force": "Sondages et rapports de force",
    "Règles, calendrier et organisation de la campagne": "Règles et calendrier",
    "Affaires judiciaires et éligibilité": "Justice et éligibilité",
    "Positionnement et image politique": "Positionnement",
}


@dataclass(frozen=True)
class SocialCandidate:
    key: str
    kind: str
    observed_at: datetime
    text: str
    source_url: str


def _parse_iso(value: str | None) -> datetime | None:
    if not value:
        return None
    text = str(value).strip()
    if not text:
        return None
    if text.endswith("Z"):
        text = text[:-1] + "+00:00"
    try:
        parsed = datetime.fromisoformat(text)
    except ValueError:
        return None
    if parsed.tzinfo is None:
        parsed = parsed.replace(tzinfo=timezone.utc)
    return parsed.astimezone(timezone.utc)


def _iso_z(value: datetime) -> str:
    return value.astimezone(timezone.utc).isoformat().replace("+00:00", "Z")


def _valid_http_url(value: Any) -> str:
    text = str(value or "").strip()
    return text if text.startswith(("https://", "http://")) else ""


def _normalize_number_text(value: Any) -> str:
    text = " ".join(str(value or "").replace("\u2212", "-").split())
    return text.replace("pp", " pts")


def _signed_number(value: Any) -> float | None:
    text = _normalize_number_text(value).replace("%", "").replace("pts", "")
    text = text.replace("▲", "").replace("▼", "").replace("•", "").strip()
    text = text.replace(" ", "").replace(",", ".")
    if not text or text in {"—", "-"}:
        return None
    try:
        return float(text)
    except ValueError:
        return None


def _fr_decimal(value: float, digits: int = 1, signed: bool = False) -> str:
    prefix = "+" if signed and value > 0 else ""
    rendered = f"{value:.{digits}f}".replace(".", ",")
    if rendered in {"-0,0", "+0,0"}:
        rendered = "0,0"
        prefix = ""
    return prefix + rendered


def _fr_signed_points(value: float) -> str:
    rendered = _fr_decimal(value, signed=True).replace("-", "−", 1)
    unit = "pt" if abs(value) < 2 else "pts"
    return f"{rendered} {unit}"


def _weighted_x_length(text: str) -> int:
    total = 0
    cursor = 0
    for match in URL_RE.finditer(text):
        total += len(text[cursor:match.start()])
        total += X_URL_WEIGHT
        cursor = match.end()
    total += len(text[cursor:])
    return total


def _truncate_text_to_weight(text: str, budget: int) -> str:
    if budget <= 0:
        return ""
    if _weighted_x_length(text) <= budget:
        return text
    suffix = "…"
    target = max(0, budget - len(suffix))
    out: list[str] = []
    weight = 0
    for ch in text:
        if weight + 1 > target:
            break
        out.append(ch)
        weight += 1
    return "".join(out).rstrip() + suffix


def _normalize_body_text(value: Any) -> str:
    lines = [" ".join(line.split()) for line in str(value or "").splitlines()]
    while lines and not lines[0]:
        lines.pop(0)
    while lines and not lines[-1]:
        lines.pop()
    output: list[str] = []
    blank = False
    for line in lines:
        if not line:
            if output and not blank:
                output.append("")
            blank = True
            continue
        output.append(line)
        blank = False
    return "\n".join(output)


def _fit_with_url(body: str, url: str) -> str:
    body = _normalize_body_text(body)
    url = _valid_http_url(url)
    if not url:
        return _truncate_text_to_weight(body, MAX_X_WEIGHTED_LENGTH)
    separator = "\n\n"
    fixed_weight = _weighted_x_length(separator + url)
    fitted = _truncate_text_to_weight(
        body,
        MAX_X_WEIGHTED_LENGTH - fixed_weight,
    )
    return f"{fitted}{separator}{url}"


def _format_fr_date_from_iso(value: str | None) -> str:
    if not value:
        return ""
    try:
        parsed = date.fromisoformat(str(value)[:10])
    except ValueError:
        return ""
    return f"{parsed.day} {FRENCH_MONTHS[parsed.month - 1]} {parsed.year}"


def _url_host(value: str) -> str:
    try:
        return (urlsplit(value).hostname or "").lower().rstrip(".")
    except ValueError:
        return ""


def _is_google_news_url(value: str) -> bool:
    return _url_host(_valid_http_url(value)) in GOOGLE_NEWS_HOSTS


def _decode_google_news_urls(urls: list[str]) -> dict[str, str]:
    unique = list(dict.fromkeys(url for url in urls if _is_google_news_url(url)))
    if not unique:
        return {}
    try:
        from googlenewsdecoder import gnewsdecoder
    except ImportError as exc:
        raise RuntimeError(
            "Google News URL resolution requires googlenewsdecoder==0.2.1; "
            "run the installer again or install social/requirements.txt"
        ) from exc

    try:
        result = gnewsdecoder(unique, timeout=15.0)
    except Exception as exc:  # third-party decoder/network boundary
        print(f"WARNING: Google News batch decode failed: {exc}", file=sys.stderr)
        return {}

    rows = result if isinstance(result, list) else [result]
    resolved: dict[str, str] = {}
    for source, row in zip(unique, rows):
        if not isinstance(row, dict):
            continue
        success = row.get("success")
        if success is None:
            success = row.get("status")
        decoded = _valid_http_url(row.get("decoded_url"))
        if success and decoded and not _is_google_news_url(decoded):
            resolved[source] = decoded
    return resolved


def resolve_publisher_urls(urls: Iterable[str]) -> dict[str, str]:
    clean = list(dict.fromkeys(_valid_http_url(url) for url in urls if _valid_http_url(url)))
    resolved = {url: url for url in clean if not _is_google_news_url(url)}
    google = [url for url in clean if _is_google_news_url(url)]
    resolved.update(_decode_google_news_urls(google))
    return resolved


def _normalize_social_title(value: Any) -> str:
    text = unicodedata.normalize("NFKD", str(value or ""))
    text = "".join(ch for ch in text if not unicodedata.combining(ch)).lower()
    text = re.sub(r"[^a-z0-9]+", " ", text)
    return " ".join(text.split())


def _social_tokens(value: Any) -> set[str]:
    return {
        token
        for token in _normalize_social_title(value).split()
        if token not in SOCIAL_STOPWORDS and len(token) >= 3
    }


def _change_date(item: dict[str, Any]) -> date | None:
    parsed = _parse_iso(item.get("trusted_change_at")) or _parse_iso(item.get("published_at"))
    return parsed.date() if parsed else None


def _campaign_action_groups(value: Any) -> set[str]:
    title = _normalize_social_title(value)
    return {
        group
        for group, phrases in SOCIAL_CAMPAIGN_ACTION_GROUPS.items()
        if any(phrase in title for phrase in phrases)
    }


def _recent_changes_social_match(left: dict[str, Any], right: dict[str, Any]) -> bool:
    if str(left.get("category") or "").lower() != str(right.get("category") or "").lower():
        return False
    left_title = _normalize_social_title(left.get("headline"))
    right_title = _normalize_social_title(right.get("headline"))
    if not left_title or not right_title:
        return False
    if left_title == right_title:
        return True

    left_date = _change_date(left)
    right_date = _change_date(right)
    if left_date and right_date and abs((left_date - right_date).days) > 1:
        return False

    left_candidates = {str(v) for v in (left.get("candidate_ids") or []) if str(v)}
    right_candidates = {str(v) for v in (right.get("candidate_ids") or []) if str(v)}
    shared_candidates = left_candidates & right_candidates
    if left_candidates and right_candidates and not shared_candidates:
        return False

    # Headline wording can differ sharply across publishers even when both
    # describe the same one-off candidate-status event. For a small set of
    # unambiguous action groups, same candidate + same/adjacent day is enough
    # to collapse duplicate coverage. Endorsements are deliberately excluded:
    # two different people can separately endorse the same candidate on a day.
    if (
        str(left.get("category") or "").lower() == "campaign"
        and shared_candidates
        and (_campaign_action_groups(left_title) & _campaign_action_groups(right_title))
    ):
        return True

    left_tokens = _social_tokens(left_title)
    right_tokens = _social_tokens(right_title)
    if not left_tokens or not right_tokens:
        return False
    shared = left_tokens & right_tokens
    containment = len(shared) / max(1, min(len(left_tokens), len(right_tokens)))
    sequence = SequenceMatcher(None, left_title, right_title).ratio()

    # Conservative social deduplication: enough shared content to identify the
    # same underlying development, while avoiding collapse of separate
    # endorsements or events concerning the same candidate.
    if len(shared) >= 4 and containment >= 0.55 and sequence >= 0.50:
        return True
    return sequence >= 0.84 and len(shared) >= 3


def _cluster_recent_changes(items: list[dict[str, Any]]) -> list[list[dict[str, Any]]]:
    clusters: list[list[dict[str, Any]]] = []
    for item in sorted(
        items,
        key=lambda row: (
            _parse_iso(row.get("detected_at")) or _parse_iso(row.get("trusted_change_at")) or datetime.min.replace(tzinfo=timezone.utc),
            str(row.get("id") or ""),
        ),
    ):
        for cluster in clusters:
            if any(_recent_changes_social_match(item, other) for other in cluster):
                cluster.append(item)
                break
        else:
            clusters.append([item])
    return clusters


def _select_social_change(
    cluster: list[dict[str, Any]],
    resolved_urls: dict[str, str],
) -> dict[str, Any] | None:
    candidates: list[tuple[tuple[int, int, str, str], dict[str, Any]]] = []
    for item in cluster:
        raw_url = _valid_http_url((item.get("primary_source") or {}).get("url"))
        resolved = resolved_urls.get(raw_url, "")
        if not resolved:
            continue
        headline = str(item.get("headline") or "").strip()
        if not headline:
            continue
        direct_rank = 0 if not _is_google_news_url(raw_url) else 1
        candidates.append(((direct_rank, len(headline), headline, str(item.get("id") or "")), item))
    return min(candidates, key=lambda pair: pair[0])[1] if candidates else None


def render_recent_change(item: dict[str, Any], source_url: str | None = None) -> str:
    source = item.get("primary_source") or {}
    url = source_url if source_url is not None else str(source.get("url") or "")
    return _fit_with_url(
        str(item.get("headline") or "").strip(),
        url,
    )


def render_campaign_event(item: dict[str, Any]) -> str:
    evidence = item.get("evidence") or []
    source_url = ""
    for row in evidence:
        source_url = _valid_http_url((row or {}).get("source_url"))
        if source_url:
            break
    title = str(item.get("title") or "").strip()
    event_date = _format_fr_date_from_iso(item.get("scheduled_start"))
    body = f"{title}\n\n{event_date}" if event_date else title
    return _fit_with_url(body, source_url)


def _state_seen(state: dict[str, Any], kind: str) -> set[str]:
    seen = state.get("seen") or {}
    key = "recent_changes" if kind == "recent_change" else "campaign_events"
    return {str(value) for value in (seen.get(key) or []) if str(value)}


def _validate_state(state: dict[str, Any]) -> dict[str, Any]:
    if state.get("schema_version") != STATE_SCHEMA_VERSION:
        raise ValueError(
            "social state is missing or has an unsupported schema; "
            "run the workflow once in bootstrap mode before enabling publishing"
        )
    initialized_at = _parse_iso(state.get("initialized_at"))
    if not initialized_at:
        raise ValueError("social state has no valid initialized_at timestamp")
    seen = state.get("seen")
    if not isinstance(seen, dict):
        raise ValueError("social state has no seen registry")
    for key in ("recent_changes", "campaign_events"):
        if not isinstance(seen.get(key), list):
            raise ValueError(f"social state field seen.{key} must be a list")
    return state


def build_bootstrap_state(
    recent_changes: dict[str, Any],
    campaign_events: dict[str, Any],
    *,
    now: datetime,
) -> dict[str, Any]:
    recent_ids = sorted({
        str(item.get("id"))
        for item in (recent_changes.get("items") or [])
        if item.get("id")
    })
    event_ids = sorted({
        str(item.get("event_id"))
        for item in (campaign_events.get("campaign_events") or [])
        if item.get("event_id")
    })
    return {
        "schema_version": STATE_SCHEMA_VERSION,
        "initialized_at": _iso_z(now),
        "updated_at": _iso_z(now),
        "seen": {
            "recent_changes": recent_ids,
            "campaign_events": event_ids,
        },
    }


def _mark_seen(state: dict[str, Any], candidate: SocialCandidate) -> None:
    registry_key = (
        "recent_changes" if candidate.kind == "recent_change" else "campaign_events"
    )
    current = _state_seen(state, candidate.kind)
    current.add(candidate.key)
    state.setdefault("seen", {})[registry_key] = sorted(current)


def collect_recent_changes(
    payload: dict[str, Any],
    *,
    cutoff: datetime,
    seen_ids: set[str],
    url_resolver: Callable[[Iterable[str]], dict[str, str]] = resolve_publisher_urls,
) -> list[SocialCandidate]:
    eligible: list[dict[str, Any]] = []
    for item in payload.get("items") or []:
        item_id = str(item.get("id") or "").strip()
        category = str(item.get("category") or "").strip().lower()
        headline = str(item.get("headline") or "").strip()
        observed = _parse_iso(item.get("detected_at")) or _parse_iso(item.get("trusted_change_at"))
        source_url = _valid_http_url((item.get("primary_source") or {}).get("url"))
        if (
            item_id
            and category in ELIGIBLE_RECENT_CHANGE_CATEGORIES
            and headline
            and observed
            and source_url
        ):
            eligible.append(item)

    output: list[SocialCandidate] = []
    for cluster in _cluster_recent_changes(eligible):
        publishable = []
        has_preexisting_match = False
        for item in cluster:
            item_id = str(item.get("id") or "").strip()
            observed = _parse_iso(item.get("detected_at")) or _parse_iso(item.get("trusted_change_at"))
            if item_id in seen_ids or (observed is not None and observed < cutoff):
                has_preexisting_match = True
            elif observed is not None and observed >= cutoff:
                publishable.append(item)

        # If this development is already represented by a seen/pre-cutoff item,
        # later duplicate coverage must not resurrect it as a new social post.
        if has_preexisting_match or not publishable:
            continue

        raw_urls = [
            _valid_http_url((item.get("primary_source") or {}).get("url"))
            for item in publishable
        ]
        resolved_urls = url_resolver(raw_urls)
        selected = _select_social_change(publishable, resolved_urls)
        if selected is None:
            for item in publishable:
                raw = _valid_http_url((item.get("primary_source") or {}).get("url"))
                if _is_google_news_url(raw):
                    print(
                        "WARNING: skipping Évolutions item because its Google News URL "
                        f"could not be resolved to a publisher URL: {item.get('headline')}",
                        file=sys.stderr,
                    )
            continue

        item_id = str(selected.get("id") or "").strip()
        observed = _parse_iso(selected.get("detected_at")) or _parse_iso(selected.get("trusted_change_at"))
        raw_url = _valid_http_url((selected.get("primary_source") or {}).get("url"))
        source_url = resolved_urls.get(raw_url, "")
        assert observed is not None
        text = render_recent_change(selected, source_url)
        if text:
            output.append(
                SocialCandidate(
                    key=item_id,
                    kind="recent_change",
                    observed_at=observed,
                    text=text,
                    source_url=source_url,
                )
            )
    return output


def collect_campaign_events(
    payload: dict[str, Any],
    *,
    cutoff: datetime,
    today_paris: date,
    seen_ids: set[str],
) -> list[SocialCandidate]:
    output: list[SocialCandidate] = []
    for item in payload.get("campaign_events") or []:
        event_id = str(item.get("event_id") or "").strip()
        if not event_id or event_id in seen_ids:
            continue
        if str(item.get("status") or "").lower() not in {"scheduled", "confirmed"}:
            continue
        observed = _parse_iso(item.get("last_verified_at"))
        if not observed or observed < cutoff:
            continue
        scheduled = str(item.get("scheduled_start") or "")
        try:
            scheduled_date = date.fromisoformat(scheduled[:10])
        except ValueError:
            continue
        if scheduled_date < today_paris:
            continue
        evidence = item.get("evidence") or []
        source_url = ""
        for row in evidence:
            source_url = _valid_http_url((row or {}).get("source_url"))
            if source_url:
                break
        title = str(item.get("title") or "").strip()
        if not source_url or not title:
            continue
        output.append(
            SocialCandidate(
                key=event_id,
                kind="campaign_event",
                observed_at=observed,
                text=render_campaign_event(item),
                source_url=source_url,
            )
        )
    return output


def collect_update_candidates(
    recent_changes: dict[str, Any],
    campaign_events: dict[str, Any],
    state: dict[str, Any],
    *,
    now: datetime,
    lookback_hours: int,
) -> list[SocialCandidate]:
    state = _validate_state(state)
    now_utc = now.astimezone(timezone.utc)
    initialized_at = _parse_iso(state.get("initialized_at"))
    assert initialized_at is not None
    rolling_cutoff = now_utc - timedelta(hours=max(1, lookback_hours))
    cutoff = max(initialized_at, rolling_cutoff)
    today_paris = now.astimezone(PARIS).date()
    candidates = [
        *collect_recent_changes(
            recent_changes,
            cutoff=cutoff,
            seen_ids=_state_seen(state, "recent_change"),
        ),
        *collect_campaign_events(
            campaign_events,
            cutoff=cutoff,
            today_paris=today_paris,
            seen_ids=_state_seen(state, "campaign_event"),
        ),
    ]
    candidates.sort(key=lambda item: (item.observed_at, item.kind, item.key))
    return candidates


def _metric_rows(metrics: dict[str, Any] | None) -> list[dict[str, Any]]:
    if not isinstance(metrics, dict):
        return []
    rows = metrics.get("rows")
    return [row for row in rows if isinstance(row, dict)] if isinstance(rows, list) else []


def _top_delta_rows(metrics: dict[str, Any] | None, limit: int = 3) -> list[dict[str, Any]]:
    ranked: list[tuple[float, dict[str, Any]]] = []
    for row in _metric_rows(metrics):
        delta = _signed_number(row.get("delta"))
        if delta is None:
            continue
        ranked.append((abs(delta), row))
    ranked.sort(key=lambda pair: (-pair[0], str(pair[1].get("label") or pair[1].get("name") or "")))
    return [row for _magnitude, row in ranked[:limit]]


def visual_caption(kind: str, now: datetime, metrics: dict[str, Any] | None = None) -> str:
    current = now.astimezone(PARIS)
    date_label = f"{current.day} {FRENCH_MONTHS[current.month - 1].upper()}"

    if kind == "media":
        comparison = str((metrics or {}).get("comparison_label") or "").strip().lower()
        rows = _top_delta_rows(metrics, 3)
        comparable = rows and comparison and "raw" not in comparison and "indispon" not in comparison and "unavail" not in comparison
        if comparable:
            lines = []
            for row in rows:
                name = str(row.get("name") or row.get("label") or "").strip()
                delta = _signed_number(row.get("delta"))
                if not name or delta is None:
                    continue
                lines.append(f"{name}  {_fr_signed_points(delta)}")
            if lines:
                return (
                    f"COUVERTURE MÉDIATIQUE · {date_label}\n\n"
                    "Plus fortes variations du taux de mention :\n\n"
                    + "\n".join(lines)
                    + "\n\nhttps://france2027.app/"
                )
        return (
            f"COUVERTURE MÉDIATIQUE · {date_label}\n\n"
            "Taux de mention des personnalités, thèmes et principaux médias "
            "dans la couverture suivie par France 2027.\n\n"
            "https://france2027.app/"
        )

    if kind == "agenda":
        rows = _top_delta_rows(metrics, 3)
        lines = []
        for row in rows:
            full_label = str(row.get("label") or "").strip()
            label = AGENDA_SOCIAL_LABELS.get(full_label, full_label)
            count = " ".join(str(row.get("count") or "").split())
            delta = _signed_number(row.get("delta"))
            if label and count and delta is not None:
                lines.append(f"{label} {count} · {_fr_signed_points(delta)}")
        if lines:
            caption = (
                f"AGENDA DE CAMPAGNE · {date_label}\n\n"
                "Évolutions les plus marquées :\n\n"
                + "\n".join(lines)
                + "\n\nhttps://france2027.app/#signal-agenda"
            )
            if _weighted_x_length(caption) <= MAX_X_WEIGHTED_LENGTH:
                return caption
        return (
            f"AGENDA DE CAMPAGNE · {date_label}\n\n"
            "Évolution des thèmes de campagne sur 30 jours et comparaison "
            "des deux dernières semaines complètes.\n\n"
            "https://france2027.app/#signal-agenda"
        )

    if kind == "issues":
        rows = _top_delta_rows(metrics, 3)
        lines = []
        for row in rows:
            label = str(row.get("label") or "").strip()
            delta = _signed_number(row.get("delta"))
            if label and delta is not None:
                lines.append(f"{label}  {_fr_signed_points(delta)}")
        if lines:
            return (
                f"ENJEUX · {date_label}\n\n"
                "Plus fortes évolutions d’incidence :\n\n"
                + "\n".join(lines)
                + "\n\nhttps://france2027.app/#signal-issues"
            )
        return (
            f"ENJEUX · {date_label}\n\n"
            "Évolution sur 30 jours et comparaison hebdomadaire des enjeux "
            "dans la couverture présidentielle suivie par France 2027.\n\n"
            "https://france2027.app/#signal-issues"
        )

    raise ValueError(f"unsupported visual kind: {kind}")


class BufferClient:
    def __init__(self, token: str, organization_id: str, channel_id: str):
        self.token = token.strip()
        self.organization_id = organization_id.strip()
        self.channel_id = channel_id.strip()
        if not self.token or not self.organization_id or not self.channel_id:
            raise ValueError("Buffer token, organization ID and channel ID are required")

    @classmethod
    def from_env(cls) -> "BufferClient":
        return cls(
            os.environ.get("BUFFER_API_KEY", ""),
            os.environ.get("BUFFER_ORGANIZATION_ID", ""),
            os.environ.get("BUFFER_X_CHANNEL_ID", ""),
        )

    def graphql(self, query: str, variables: dict[str, Any] | None = None) -> dict[str, Any]:
        body = json.dumps({"query": query, "variables": variables or {}}).encode("utf-8")
        request = urllib.request.Request(
            BUFFER_ENDPOINT,
            data=body,
            method="POST",
            headers={
                "Authorization": f"Bearer {self.token}",
                "Content-Type": "application/json",
                "User-Agent": "fr27-social-publisher/1.0",
            },
        )
        try:
            with urllib.request.urlopen(request, timeout=45) as response:
                payload = json.loads(response.read().decode("utf-8"))
        except urllib.error.HTTPError as exc:
            detail = exc.read().decode("utf-8", errors="replace")
            raise RuntimeError(f"Buffer HTTP {exc.code}: {detail}") from exc
        except urllib.error.URLError as exc:
            raise RuntimeError(f"Buffer request failed: {exc}") from exc
        errors = payload.get("errors") or []
        if errors:
            raise RuntimeError(f"Buffer GraphQL error: {errors}")
        return payload.get("data") or {}

    def recent_post_texts(self, *, since: datetime) -> set[str]:
        query = """
        query RecentPosts(
          $organizationId: OrganizationId!,
          $channelId: ChannelId!,
          $startDate: DateTime!
        ) {
          posts(
            first: 100,
            input: {
              organizationId: $organizationId,
              filter: {
                status: [sent, scheduled],
                channelIds: [$channelId],
                startDate: $startDate
              }
            }
          ) {
            edges { node { id text createdAt dueAt status } }
          }
        }
        """
        data = self.graphql(
            query,
            {
                "organizationId": self.organization_id,
                "channelId": self.channel_id,
                "startDate": _iso_z(since),
            },
        )
        edges = (((data.get("posts") or {}).get("edges")) or [])
        return {
            str((edge.get("node") or {}).get("text") or "").strip()
            for edge in edges
            if str((edge.get("node") or {}).get("text") or "").strip()
        }

    def create_post(self, text: str, *, image_url: str = "") -> str:
        mutation = """
        mutation CreatePost($input: CreatePostInput!) {
          createPost(input: $input) {
            ... on PostActionSuccess {
              post { id text status dueAt }
            }
            ... on MutationError { message }
          }
        }
        """
        input_payload: dict[str, Any] = {
            "text": text,
            "channelId": self.channel_id,
            "schedulingType": "automatic",
            "mode": "shareNow",
            "aiAssisted": False,
        }
        if image_url:
            input_payload["assets"] = [{"image": {"url": image_url}}]
        data = self.graphql(mutation, {"input": input_payload})
        result = data.get("createPost") or {}
        message = result.get("message")
        if message:
            raise RuntimeError(f"Buffer rejected post: {message}")
        post = result.get("post") or {}
        post_id = str(post.get("id") or "")
        if not post_id:
            raise RuntimeError(f"Buffer returned no post id: {result}")
        return post_id


def _load_json(path: str) -> dict[str, Any]:
    with Path(path).open("r", encoding="utf-8") as handle:
        return json.load(handle)


def _save_json(path: str, payload: dict[str, Any]) -> None:
    target = Path(path)
    target.parent.mkdir(parents=True, exist_ok=True)
    target.write_text(
        json.dumps(payload, ensure_ascii=False, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )


def _print_candidates(candidates: Iterable[SocialCandidate]) -> None:
    for candidate in candidates:
        print(f"[{candidate.kind}] {candidate.key} @ {candidate.observed_at.isoformat()}")
        print(candidate.text)
        print("---")


def run_bootstrap(args: argparse.Namespace) -> int:
    now = _parse_iso(args.now) if args.now else datetime.now(timezone.utc)
    if now is None:
        raise ValueError("--now must be a valid ISO timestamp")
    state = build_bootstrap_state(
        _load_json(args.recent_changes),
        _load_json(args.campaign_events),
        now=now,
    )
    _save_json(args.output, state)
    print(
        "bootstrapped social state: "
        f"{len(state['seen']['recent_changes'])} recent changes, "
        f"{len(state['seen']['campaign_events'])} campaign events"
    )
    return 0


def run_updates(args: argparse.Namespace) -> int:
    now = _parse_iso(args.now) if args.now else datetime.now(timezone.utc)
    if now is None:
        raise ValueError("--now must be a valid ISO timestamp")
    state = _validate_state(_load_json(args.state))
    candidates = collect_update_candidates(
        _load_json(args.recent_changes),
        _load_json(args.campaign_events),
        state,
        now=now,
        lookback_hours=args.lookback_hours,
    )
    if args.dry_run:
        _print_candidates(candidates[: args.max_posts])
        return 0

    client = BufferClient.from_env()
    recent_texts = client.recent_post_texts(since=now - timedelta(days=3))
    published = 0
    resolved = 0
    for candidate in candidates:
        if published >= args.max_posts:
            break
        if candidate.text.strip() in recent_texts:
            print(f"already present in Buffer; marking seen: {candidate.kind} {candidate.key}")
            _mark_seen(state, candidate)
            resolved += 1
            continue
        post_id = client.create_post(candidate.text)
        print(f"published {candidate.kind} {candidate.key}: {post_id}")
        recent_texts.add(candidate.text.strip())
        _mark_seen(state, candidate)
        published += 1
        resolved += 1

    state["updated_at"] = _iso_z(now)
    _save_json(args.state_output, state)
    print(f"published_count={published} resolved_count={resolved}")
    return 0


def run_preview(args: argparse.Namespace) -> int:
    now = _parse_iso(args.now) if args.now else datetime.now(timezone.utc)
    if now is None:
        raise ValueError("--now must be a valid ISO timestamp")
    today_paris = now.astimezone(PARIS).date()

    recent_payload = _load_json(args.recent_changes)
    preview_items = []
    for item in recent_payload.get("items") or []:
        category = str(item.get("category") or "").strip().lower()
        headline = str(item.get("headline") or "").strip()
        source_url = _valid_http_url((item.get("primary_source") or {}).get("url"))
        observed = _parse_iso(item.get("detected_at")) or _parse_iso(item.get("trusted_change_at"))
        if category in ELIGIBLE_RECENT_CHANGE_CATEGORIES and headline and source_url and observed:
            preview_items.append(item)

    recent_rows = []
    suppressed_duplicate_count = 0
    for cluster in _cluster_recent_changes(preview_items):
        raw_urls = [
            _valid_http_url((item.get("primary_source") or {}).get("url"))
            for item in cluster
        ]
        resolved_urls = resolve_publisher_urls(raw_urls)
        selected = _select_social_change(cluster, resolved_urls)
        if selected is None:
            continue
        suppressed_duplicate_count += max(0, len(cluster) - 1)
        observed = _parse_iso(selected.get("detected_at")) or _parse_iso(selected.get("trusted_change_at"))
        raw_url = _valid_http_url((selected.get("primary_source") or {}).get("url"))
        source_url = resolved_urls.get(raw_url, "")
        if observed and source_url:
            recent_rows.append((observed, render_recent_change(selected, source_url)))
    recent_rows.sort(key=lambda pair: pair[0], reverse=True)

    event_payload = _load_json(args.campaign_events)
    event_rows = []
    for item in event_payload.get("campaign_events") or []:
        if str(item.get("status") or "").lower() not in {"scheduled", "confirmed"}:
            continue
        scheduled = str(item.get("scheduled_start") or "")
        try:
            scheduled_date = date.fromisoformat(scheduled[:10])
        except ValueError:
            continue
        if scheduled_date < today_paris:
            continue
        text = render_campaign_event(item)
        if text:
            event_rows.append((scheduled_date, text))
    event_rows.sort(key=lambda pair: pair[0])

    print("=== ÉVOLUTIONS — ÉCHANTILLON EXACT ===")
    for _observed, text in recent_rows[: args.recent_count]:
        print(text)
        print("---")
    if suppressed_duplicate_count:
        print(f"[aperçu: {suppressed_duplicate_count} couverture(s) dupliquée(s) supprimée(s)]")
    print("\n=== ÉVÉNEMENTS — ÉCHANTILLON EXACT ===")
    for _scheduled, text in event_rows[: args.event_count]:
        print(text)
        print("---")
    return 0


def run_visual(args: argparse.Namespace) -> int:
    now = _parse_iso(args.now) if args.now else datetime.now(timezone.utc)
    if now is None:
        raise ValueError("--now must be a valid ISO timestamp")
    metrics = _load_json(args.metrics_json) if args.metrics_json else None
    caption = visual_caption(args.kind, now, metrics)
    if _weighted_x_length(caption) > MAX_X_WEIGHTED_LENGTH:
        raise ValueError("visual caption exceeds X weighted limit")
    if args.dry_run:
        print(caption)
        if args.image_url:
            print(f"image={args.image_url}")
        return 0
    image_url = _valid_http_url(args.image_url)
    if not image_url:
        raise ValueError("--image-url is required when publishing a visual post")
    client = BufferClient.from_env()
    recent_texts = client.recent_post_texts(since=now - timedelta(days=3))
    if caption.strip() in recent_texts:
        print("visual already published; skipping")
        return 0
    post_id = client.create_post(caption, image_url=image_url)
    print(f"published {args.kind} visual: {post_id}")
    return 0


def run_buffer_info(_args: argparse.Namespace) -> int:
    token = os.environ.get("BUFFER_API_KEY", "").strip()
    if not token:
        raise ValueError("BUFFER_API_KEY is required")

    def graphql(query: str, variables: dict[str, Any] | None = None) -> dict[str, Any]:
        body = json.dumps({"query": query, "variables": variables or {}}).encode("utf-8")
        request = urllib.request.Request(
            BUFFER_ENDPOINT,
            data=body,
            method="POST",
            headers={
                "Authorization": f"Bearer {token}",
                "Content-Type": "application/json",
                "User-Agent": "fr27-social-publisher/1.0",
            },
        )
        with urllib.request.urlopen(request, timeout=45) as response:
            payload = json.loads(response.read().decode("utf-8"))
        if payload.get("errors"):
            raise RuntimeError(payload["errors"])
        return payload.get("data") or {}

    org_data = graphql("query { account { organizations { id name } } }")
    organizations = ((org_data.get("account") or {}).get("organizations")) or []
    result: list[dict[str, Any]] = []
    for org in organizations:
        channel_data = graphql(
            """
            query Channels($organizationId: OrganizationId!) {
              channels(input: { organizationId: $organizationId }) {
                id name displayName service isQueuePaused
              }
            }
            """,
            {"organizationId": org.get("id")},
        )
        result.append(
            {
                "organization": org,
                "channels": channel_data.get("channels") or [],
            }
        )
    print(json.dumps(result, ensure_ascii=False, indent=2))
    return 0


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="FR27 deterministic Buffer/X publisher")
    sub = parser.add_subparsers(dest="command", required=True)

    bootstrap = sub.add_parser("bootstrap", help="baseline existing items without posting")
    bootstrap.add_argument("--recent-changes", default="recent_changes.json")
    bootstrap.add_argument("--campaign-events", default="campaign_events.json")
    bootstrap.add_argument("--output", required=True)
    bootstrap.add_argument("--now")
    bootstrap.set_defaults(func=run_bootstrap)

    updates = sub.add_parser("updates", help="publish new What Changed and campaign-event items")
    updates.add_argument("--recent-changes", default="recent_changes.json")
    updates.add_argument("--campaign-events", default="campaign_events.json")
    updates.add_argument("--state", required=True)
    updates.add_argument("--state-output", required=True)
    updates.add_argument("--now")
    updates.add_argument("--lookback-hours", type=int, default=24)
    updates.add_argument("--max-posts", type=int, default=4)
    updates.add_argument("--dry-run", action="store_true")
    updates.set_defaults(func=run_updates)

    preview = sub.add_parser("preview", help="print exact current French text samples without publishing")
    preview.add_argument("--recent-changes", default="recent_changes.json")
    preview.add_argument("--campaign-events", default="campaign_events.json")
    preview.add_argument("--recent-count", type=int, default=5)
    preview.add_argument("--event-count", type=int, default=5)
    preview.add_argument("--now")
    preview.set_defaults(func=run_preview)

    visual = sub.add_parser("visual", help="publish one daily screenshot post")
    visual.add_argument("--kind", choices=("media", "agenda", "issues"), required=True)
    visual.add_argument("--image-url", default="")
    visual.add_argument("--metrics-json", default="")
    visual.add_argument("--now")
    visual.add_argument("--dry-run", action="store_true")
    visual.set_defaults(func=run_visual)

    info = sub.add_parser("buffer-info", help="discover Buffer organization and channel IDs")
    info.set_defaults(func=run_buffer_info)
    return parser


def main() -> int:
    parser = build_parser()
    args = parser.parse_args()
    try:
        return int(args.func(args) or 0)
    except (ValueError, RuntimeError, FileNotFoundError, json.JSONDecodeError) as exc:
        print(f"ERROR: {exc}", file=sys.stderr)
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
