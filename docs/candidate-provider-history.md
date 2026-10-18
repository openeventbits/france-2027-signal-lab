# Independent candidate provider histories

Three parallel artifacts retain provider-native observations:

| Artifact | Identity lock | Recorded unit |
| --- | --- | --- |
| `candidate_polymarket_history.json` | candidate, reviewed market and YES token | implied probability in [0, 1] |
| `candidate_youtube_history.json` | candidate and stable channel ID | API `subscriber_count` |
| `candidate_bluesky_history.json` | candidate and pinned DID | API `followers_count` |

There is no combined social history, ranking, normalization or momentum score.
These measures are not voting intention and are not directly comparable.
Task 5A adds no visible values, movement lines, charts or browser requests.

## Retention, timestamps and identity

Each artifact covers the complete canonical registry, with empty point arrays
for candidates without numeric observations. Identity fields are null only for
unmapped candidates. The envelope's `observed_at` is the source snapshot's real
observation time: it is the history cutoff, not the time the history builder ran.
The retention interval contains that UTC date and the preceding 89 UTC dates.
Only points at or before that exact timestamp are retained, up to 90 points per
candidate. Missing days remain missing, rather than interpolated or filled.

The latest successful observation per candidate/UTC date wins. Equal timestamps
with different values from the same source fail validation. A CLOB/Gamma
price pair at the same timestamp remains separate through source provenance;
the canonical daily point uses the authoritative FR27 snapshot. Ordering is deterministic. Retries with
the same observation are idempotent. An older snapshot cannot roll history back.
History keeps an established identity even while an account is unavailable.
Changing/removing an established mapping fails closed; an explicit reviewed
history migration would be required. A newly reviewed identity may start an
empty previously-unmapped series. New registry candidates start with empty rows;
removing a historical registry ID requires explicit review. Different identities
are never spliced.

## Polymarket: official historical backfill

Source: [official CLOB prices-history documentation](https://docs.polymarket.com/api-reference/markets/get-prices-history).
Only `GET https://clob.polymarket.com/prices-history` is called, without auth.
`market` is the exact pinned YES `outcome_id` in the existing reviewed mapping;
current snapshot market/outcome identity is validated against that same mapping
before requests. The response does not echo identity: binding is established by
the exact request token, not by a candidate-name lookup.

Requests use absolute integer `startTs`/`endTs` and `fidelity=1440` minutes;
`interval` is omitted. The initial bound starts at 00:00 UTC on the oldest
retained date and ends at the committed current snapshot's observation time.
The live endpoint rejects a single 90-day interval, so requests are split into
windows no longer than seven days, overlapping by one second to avoid boundary
loss with exclusive filters. No minute-level series is requested. At most 13
request windows per mapped token are needed for this initial cutoff.

All raw points must have valid epoch timestamps and finite numeric probabilities
in [0, 1]. Exact duplicate timestamps with equal prices deduplicate; conflicting
prices fail closed. Sampling-edge points outside a chunk may be returned by the
service. Valid samples are merged and clipped to the overall requested UTC
window; discarded sample counts are reported. Within each UTC date the latest
actual returned timestamp wins. This is a daily sampled price, **not** a claim
to a daily closing price, OHLC, average or continuous market coverage.

Each point retains `source=clob_prices_history` or `source=fr27_snapshot`.
The existing Gamma snapshot remains authoritative for current card values and
is never overwritten. Its actual observation is appended to history with its
timestamp; on that UTC date it supersedes earlier historical samples. Both
refer to the same reviewed market's YES asset. Different sample times and
pricing sources can produce different values. Each row also retains a bounded
`latest_source_point` containing the latest actual CLOB timestamp/price, so the
source sample and current FR27 price remain independently auditable even when
they fall on the same date. This raw audit value is not a presentation metric.
Historical quotes are not claimed
to equal Gamma prices exactly. No source timestamp is replaced with a day-end
or execution timestamp. Empty source history creates no fabricated prices.

`--backfill` requests the bounded initial interval. `--incremental` starts at
the later of the retention boundary and the day before each token's previous
`source_checked_through` date. This small overlap refreshes the previous partial
UTC day. Equal snapshot/watermark timestamps need no new request. A missing
watermark (including a newly reviewed market) needs an initial bounded fetch.
The watermark advances only after every requested window has validated. A
successful empty response still records the checked bound, preventing repeated
full-window downloads. Default mode appends the current snapshot offline.

Requests have a 20-second timeout, at most three attempts, capped Retry-After
delays (30 seconds), a 1 MiB response limit and 10,000-point validation bound.
HTTP 408/425/429 and selected 5xx/network failures retry; malformed data and
other HTTP failures block publication. Diagnostics contain bounded safe status
messages, not raw responses or credentials.

## YouTube: FR27 observations only

There is no official subscriber-count backfill in this method. The first point
is the existing `candidate_youtube.json` observation, not the Task 5A execution
time. Later successful snapshots append through the same daily retention rule.
Hidden subscribers, null counts or unavailable channels never create a numeric
point. An invalid snapshot fails validation instead of being converted to zero.
YouTube rounds subscriber counts down to three significant figures. History
retains exactly those API values; small real changes may remain invisible.
The history builder makes no API call and consumes no additional YouTube quota
or credential. The existing collector alone uses `YOUTUBE_API_KEY`.

## Bluesky: FR27 observations only

There is no follower backfill in this method. History begins with the existing
`candidate_bluesky.json` observation. A changed handle with the same pinned DID
continues the same series. Handles are not series keys. Unavailable or public-web
opt-out snapshots create no numeric point; no follower value is inferred.
Earlier valid observations remain bounded historical evidence, not a claim of
current availability. Any future display must also respect current availability
and opt-out state. The history builder makes no network call and needs no auth.

## Delta helpers, not UI

`derive_delta(row, 7)` and `derive_delta(row, 30)` use the latest retained point
as current. The baseline is the latest retained observation whose **timestamp**
is at or before current minus exactly 7 or 30 days. This is not an array-index
offset, nearest-point interpolation or a claim of an observation on every day.
The helpers return null when no baseline exists, including initial one-point
YouTube/Bluesky histories. Missing history is never zero movement.

Polymarket differences are percentage points (0.459 minus 0.421 returns 3.8),
using decimal arithmetic; counts are signed raw subscriber/follower differences.
There are no relative-growth percentages or normalized deltas. Helpers return
numbers in provider-native units.

## Publication transaction

The existing candidate-family scheduled/manual workflow collects all current
providers, runs offline history tests, updates histories, validates them, then
builds the manifest and candidate family. Provider collection failure skips the
history step and publication. All data validates before an fsync + atomic
replacement per artifact. Any history/network/identity failure leaves its prior
artifact intact and prevents the Git publication transaction. Partial worktree
updates are never published. All three histories are explicitly staged together.

The manifest has independent history lanes, each with its history hash, mapping
and current-snapshot dependency hashes, schema, registry coverage, point count
and actual latest point timestamp. Missing/corrupt/out-of-date histories block
publication. Candidate JSON does not duplicate 90-day raw history. The bounded
artifacts are consumed by the static candidate-page builder; candidate JSON
does not acquire history or derived presentation fields.

## Static card presentation

The separate public-signal cards use the existing provider delta helpers for
seven-day change. Polymarket uses percentage points, YouTube raw subscribers,
and Bluesky raw followers. The authoritative current snapshot remains the
headline and terminal chart observation; validation requires history to contain
that exact timestamp, value and pinned identity. The current CLOB source quote
never replaces the FR27 snapshot. Rendering does not append or rewrite history.

A valid seven-day baseline enables a compact trendline containing only actual
observations from the preceding 30 days, including the current point. No valid
baseline means no movement row, chart or placeholder. A chart also needs two
visible points. YouTube and Bluesky activate automatically as their histories
accumulate; their initial one-point histories produce no trends.

The inline SVG uses chronological time spacing and a separate local vertical
scale for each provider. Its horizontal extent runs from the earliest visible
observation to the current observation. Vertical padding is ten percent of the
visible value range, inside four-pixel margins; flat series are centered.
Gaps longer than 48 hours break the line, with isolated recorded observations
shown as dots. Missing dates are never filled. Shapes cannot be compared across
platforms. Accessible descriptions name the provider, native unit and seven-day
change. The existing FR27 info controls carry these qualifications. All values
and SVG coordinates are generated at build time, with no browser history/API
requests and no modification to Wikipedia Attention.

PR/general validation runs offline checks only. Live incremental CLOB requests
are restricted to the existing scheduled/manual collection branch. No separate
provider workflows or new secrets were introduced.
