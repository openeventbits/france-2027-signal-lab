# Candidate lifecycle evidence

`candidate_candidacy_sources.json` is the existing curated evidence inventory.
Its schema 1.0 now also accepts dated lifecycle entries: the normal source fields
plus `effective_at` (canonical UTC timestamp) and `event_type`. Keep these entries
as an append-only decision ledger. Add a newer event to change a candidate's
state; do not replace an earlier result to represent a later declaration.

Supported event types and resulting statuses:

| Event | Status |
| --- | --- |
| `primary_result` | `party_selected`, `primary_eliminated` |
| `declaration` | `declared` |
| `withdrawal` | `withdrawn` |
| `selection` | `party_selected` |
| `ruled_out` | `ruled_out` |

Candidate and party first-party sources remain supported. `primary_result_report`
also accepts a curated report of the organizing authority's completed-primary
result, only for a `primary_result` event. Review the source before adding it;
the collector validates the inventory but does not independently authenticate
its political claims. Each entry retains URL, publisher, title, date and reason.
Duplicate event instants for one identity fail validation.

Reconciliation order:

1. The main Wikipedia page wins over supplemental extraction for the same identity.
2. Stable identities, names and article IDs reconcile against the last-good registry.
   Supplemental pages cannot create new identities. Missing identities are retained.
3. Existing undated curated sources keep their date/freshness rules.
4. The latest authoritative lifecycle event effective at the requested cutoff wins.
   A newer Wikipedia page revision alone cannot supersede a lifecycle decision.
   Reactivation requires a newer authoritative event, such as a declaration.

`upstream_presence` continues to describe source-page discovery. A defeated
participant still listed on an official-candidates page remains `present`.
`primary_eliminated` maps to `hidden`, so the existing canonical active helpers
exclude them. The complete registry and Candidate Signals retain their identities;
the generated active field follows the canonical helpers. Previously published
dossiers use the existing retained-archive path and keep both language routes.
The directory's existing archive filter exposes retained dossier links separately
from active candidate cards. Published archive routes also remain available to
dashboard navigation; route existence does not confer active candidacy.

The October 2026 Social Democratic primary result entries use LCP's report of
organizing-commission president Patrick Mennucci's announcement. The effective
boundary is 2026-10-11T16:30:00Z, LCP's first publication time (18:30 in Paris).
The report says the proclamation was shortly after 18:00; it does not provide
an exact second. The publication time is a conservative, reproducible boundary,
not a claim to know the precise proclamation time.

The updater uses current UTC time unless `--as-of` is supplied. Historical
rebuilds require pinned source revisions and a last-good registry from at or
before that period, before any later applied event. The current registry is a
snapshot, not an event-sourced archive of every previous presence/name state.
The inventory preserves the effective timestamps; Git preserves prior snapshots.
The builder rejects future input snapshots instead of inventing historical state.
Historical replay uses `build_payload()` with saved revision HTML and its matching
last-good registry. The CLI still collects current revisions; a cutoff earlier
than those revisions deliberately fails rather than fetching historical inputs
implicitly.

`candidate_visibility_history.json` is media-observation history, not an active
roster ledger. Its builder uses all retained registry identities and published
news matches, independent of today's status. Rebuild it normally; do not filter
its observations using today's active roster or edit the generated history by hand.

Local regeneration (does not publish):

```powershell
python -B fetch_candidate_candidacy_status.py --previous candidate_candidacy_status.json --output candidate_candidacy_status.json
python -B build_candidate_signals.py
python -B build_candidate_visibility_history.py
# Refresh the dependent Candidate Attention and Claims projections before dossiers.
python -B build_candidate_reference.py --all-active
python -B build_route_registry.py
python -B build_search_entrypoints.py
python -B build_route_registry.py
python -B build_sitemaps.py
python -B build_publication_manifest.py
```

Run `python -B -m unittest test_candidate_lifecycle` with the other candidacy,
visibility, dossier and publication tests. The scheduled candidate-universe
workflow includes this regression suite.

Candidate Attention can be rebuilt for its existing period with
`build_candidate_attention_payload()` and the stored daily observations, selecting
the canonical active fetch plan. This changes membership and provenance without
changing any retained candidate's measurements. Before dropping a now-inactive row
from that current projection, verify its 90-day series remains in the retained
dossier. Claims' `build_public_bundle()` can similarly rebuild the active query
metadata around unchanged accepted reviews and historical associations. Neither
operation requires deleting historical evidence or changing its observation dates.
