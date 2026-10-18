# Candidate prediction-market evidence

Polymarket is a third-party prediction market. FR27 displays its implied
probability, not a value calculated by FR27, voting intention or an FR27
forecast. Participants are not a representative sample of French voters.
Liquidity and trading conditions may influence prices. Missing evidence does
not mean 0%. FR27 does not combine this evidence with polling, Wikipedia,
media visibility, agenda or other evidence into a synthetic score.

Polymarket est un marché prédictif tiers. FR27 affiche sa probabilité implicite,
non calculée par FR27 : ce n’est ni une intention de vote ni une prévision FR27.
Les participants ne constituent pas un échantillon représentatif des électeurs
français. La liquidité et les conditions de négociation peuvent influencer les
prix. Une absence ne signifie pas 0%. Aucun score synthétique ne combine ce
signal avec les sondages, Wikipédia, les médias, l’agenda ou d’autres éléments.

## Source and selection

Verified on 17 October 2026 against the official documentation and public API:

- [Gamma event by slug](https://docs.polymarket.com/api-reference/events/get-event-by-slug):
  `GET https://gamma-api.polymarket.com/events/slug/next-french-presidential-election`.
- [Market details](https://docs.polymarket.com/market-data/market-details):
  `outcomes`, `outcomePrices`, `clobTokenIds` are aligned JSON-encoded arrays for
  protocol v1. Prices are decimal values on the 0–1 scale.
- [Price semantics](https://help.polymarket.com/en/articles/13364488-how-are-prices-calculated):
  displayed prices normally use the bid/ask midpoint, with last-trade fallback
  when the spread exceeds $0.10. FR27 preserves Gamma's supplied YES price;
  it does not reconstruct the display-price algorithm or promise exact real-time
  parity with Polymarket's interface. `updatedAt` is metadata, not a trade timestamp.

Event `79987`, `next-french-presidential-election`, resolves to the **overall
election winner, including any second round**, including an early election.
The separate `french-presidential-election-first-round-winner` event and primary
or eligibility markets are deliberately excluded. The selected event rules
include an Other resolution if results are unknown by 31 December 2027.

## Reviewed mappings and contract

`polymarket_candidate_markets.json` pins the event ID/slug, Gamma market ID/slug,
candidate's upstream `groupItemTitle`, YES label and v1 CTF token ID to an existing
canonical FR27 candidate ID. Production uses no name matching. No registry IDs
or display tiers are changed. Renamed labels, changed tokens, slugs or protocol
versions fail validation and require review. Protocol v2 is intentionally not
accepted automatically.

`candidate_polymarket.json` is a separate version 1.0 candidate artifact, following
the existing Wikipedia companion-artifact pattern. The core candidate-signals
contract keeps its prohibition on probability/forecast fields. The artifact
contains `schema_version`, `provider`, `event_id`, `event_slug`, `source_url`,
`generated_at`, `observed_at`, nullable `source_updated_at`, `stale_after_hours`,
`candidates`, and `ignored_markets`.

Every registry candidate at collection time has `candidate_id`, `status`, nullable
`implied_probability` (numeric 0–1), nullable `market_id`, `market_slug`,
`outcome_id`, `outcome_name`, `source_updated_at`, `source_url`. Observation time
is shared by the snapshot; update time comes from the upstream market when
available. Unmapped candidates have null identifiers as well as null probability.
Unreviewed markets retain `market_id`, upstream `name` and reason
`unreviewed_market`; this includes Other, placeholders, and candidates outside
the registry. New mappings require explicit review.

Statuses: `observed`, `unavailable_no_market`, `unavailable_missing_market`,
`unavailable_market_inactive`, `unavailable_price`. Every unavailable value is
null. Missing/empty market arrays, an event containing no reviewed markets,
invalid prices, duplicate IDs or incorrect identities are hard failures.
Available zero is accepted only when it was actually supplied by the API.
Probabilities are never normalized across candidates or forced to total 100%.
Volume, liquidity, rankings and deltas are omitted.

## Publication and freshness

The existing candidate-family workflow collects once daily at its existing
10:41 UTC schedule, or on manual dispatch. Other triggers reuse the validated
snapshot. No secrets or client-side provider requests are used. Requests use a
FR27 User-Agent, 20-second timeout, 5 MiB limit, and at most three attempts with
bounded retries for network errors, 429 and transient HTTP failures.

Validation completes before atomic replacement. Any collection failure exits
nonzero and leaves previous bytes untouched; the workflow fails before committing
or publishing generated pages. No fabricated empty snapshot is produced.
The publication manifest hashes and validates the separate lane; candidate
projections validate current registry and reviewed mapping identities. The registry
may subsequently add people; an absent snapshot record is displayed as
unavailable until a real collection includes that person. Existing snapshots are
not rewritten to invent observations during independent registry updates. The Candidates
detail-page attention section renders a compact independent unit after Wikipedia.
Freshness measures only the age of the last successful FR27 observation (`observed_at`),
with a 48-hour threshold. Upstream `source_updated_at` remains provenance metadata;
it does not establish last trade time, price age or market activity and never
determines the freshness label. Without JavaScript, collection time and a freshness-check prompt remain
visible. A stale price is explicitly labeled as an old observation, never refreshed
artificially by a page build. An existing snapshot may remain visible during an
outage until the next successful publication.

Only the current value is stored. Existing media/agenda histories and Wikimedia
pageview series have different source semantics; extending them would broaden
this task. Shared observation timestamps and stable outcome IDs leave room for
real timestamped observations later. No 24h/7d history or delta is inferred.

Source-linked values and provider identification remain subject to the existing
third-party rights policy. No Polymarket logo or other brand asset is introduced.
