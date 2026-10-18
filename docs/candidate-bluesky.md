# Candidate Bluesky public-account evidence

Bluesky is an independent **social platform / public account** evidence stream.
Followers are current Bluesky platform followers, not voters, supporters,
approval, unique readers, electoral reach or popularity among French voters.
Following is the number of accounts followed, not an audience measure.
`postsCount` retains Bluesky's platform counter semantics; it is not a count of
original political posts. Counts remain independent. No ratio, ranking,
engagement, sentiment, momentum, forecast or synthetic FR27 score is created.
Bluesky, Wikipedia, Polymarket, YouTube and polls measure different concepts and
are not directly comparable or combined.

## Official infrastructure and identity

Reviewed on 17 October 2026:

- [Official API hosts guide](https://bsky.network/docs/api-directory/) recommends
  `https://public.api.bsky.app` for public requests, with additional caching.
  The former docs.bsky.app guide redirects to the current Bluesky-operated docs.
- [Official getProfiles lexicon](https://github.com/bluesky-social/atproto/blob/main/lexicons/app/bsky/actor/getProfiles.json)
  defines a maximum of 25 actors per request.
- [Official identity guide](https://bsky.network/docs/resolving-identities/) and
  [AT Protocol handle specification](https://atproto.com/specs/handle) distinguish
  persistent DIDs from mutable handles and require bidirectional identity links.
- [Current visibility guidance](https://bsky.network/docs/about-bluesky-content/visibility-preferences/)
  explains that the logged-out visibility preference is exposed as the account
  label `!no-unauthenticated`; applications can honor it without reading a
  separate preference record.

Only reviewed official personal/campaign accounts are configured in
`bluesky_candidate_accounts.json`. It pins `did`, alongside `candidate_id`,
`reviewed_handle`, `verification_url` and the exact reviewed `account_url`.
The mapping review records the exact outbound link where present; a custom-domain
handle can instead qualify when it matches the independently established official
personal domain and official identity resolution/DID-document links agree.
The supported DID forms are did:plc and simple hostname-based did:web; other
methods or did:web path/port forms need explicit review before use.
Names, search ranking, avatars and counts are insufficient. Party, movement,
parliamentary-group, institutional, media and fan accounts are excluded.
All 75 canonical candidates have a decision in
[the mapping ledger](candidate-bluesky-mapping-review.md). Unmapped is not a
claim of account absence.

## Collection and public-web opt-out

The collector uses only these unauthenticated official endpoints:

| Endpoint | Purpose |
| --- | --- |
| `GET https://public.api.bsky.app/xrpc/app.bsky.actor.getProfiles` | Sorted pinned DIDs, at most 25 actors per batch; current identity, counters and visibility labels. |
| `GET https://public.api.bsky.app/xrpc/com.atproto.identity.resolveHandle` | Verify each observed current handle resolves back to its pinned DID. |

No authentication, secret, browser request, HTML scraping of Bluesky,
third-party analytics or fuzzy production account search is used. During initial
identity review, exact handle resolution and official PLC DID documents establish
bidirectional identity before pinning. Runtime always fetches the pinned DID,
checks every returned DID and resolves the **currently observed** handle back to
that DID. A changed handle with the same DID is a normal update. Unexpected DIDs,
reassigned handles or mismatched resolution fail the whole collection. An old
reviewed handle is never used to silently follow a replacement account.

Every collection inspects returned profile labels before consuming metrics.
An active `!no-unauthenticated` label targeting the account or its profile record
suppresses all profile fields and counters. Label negation, creation time,
expiration and latest state per source/target are checked; malformed or
conflicting opt-out metadata fails closed. No labels is permitted by the API's
optional label field. FR27 does not bypass opt-out by authenticating or consulting
another service. The explicit opt-out row retains only candidate identity, pinned
DID and status; all other evidence fields are null.

Only DID, current handle, optional display name, stable DID-based profile URL,
followers, following and post counts are retained for an observed account.
Descriptions, avatars, banners, account creation time and verification badges are
not retained. Verification badges are not needed to replace first-party mapping
evidence. Raw profiles and labels are not published.

## Artifact contract and failures

`candidate_bluesky.json` has exactly `schema_version` (1.0), `provider` (bluesky),
`generated_at`, `observed_at`, `stale_after_hours` (48) and `candidates`.
Generation and observation timestamps match the real UTC collection-start instant.
API requests subsequently read changing platform data; this is a bounded snapshot,
not a claim that all counters were measured simultaneously. Caching can add
upstream latency. A page rebuild does not refresh the observation timestamp.

Each sorted candidate row contains exactly:

`candidate_id`, `status`, `did`, `handle`, `display_name`, `profile_url`,
`followers_count`, `follows_count`, `posts_count`.

Statuses:

- `observed`: verified DID/current handle and all three API counters present.
- `unavailable_no_account`: no reviewed mapping; all evidence fields are null.
- `unavailable_public_web_opt_out`: mapped DID retained, all profile fields and
  counters null, even when the API supplied them.
- `unavailable_account_missing`: recognized explicit contract state with the
  mapped DID and null profile fields/counters. The collector does not emit it
  to mask a missing batch account or failed API request; those fail collection.

Unavailable is never zero. A returned integer zero is valid for an observed
account. All counts must be non-negative JSON integers no greater than `2**53-1`;
strings, booleans, fractional/negative/unsafe numbers and missing counters fail.
Registry coverage must be exact and mappings must be unique by candidate, DID and
reviewed handle. Unexpected fields, identities, duplicates or malformed metadata
fail before writing.

Requests have a 20-second timeout, 2 MiB response limit and at most three attempts.
Network errors/timeouts and HTTP 408/425/429/500/502/503/504 retry with bounded
backoff (1 then 2 seconds; numeric Retry-After capped at 30 seconds).
HTTP 400/404 and other non-retryable responses fail immediately. A missing mapped
profile, malformed JSON/schema, invalid counts or identity mismatch fails the
entire observation. Diagnostics expose only a safe HTTP code or generic failure,
not response bodies, URLs or exception details. Complete validation precedes the
existing atomic fsync/replace writer. Failure leaves prior artifact bytes intact
and blocks the publication transaction; it never fabricates unavailable/zero data.

## Recent activity deferred

Seven-day posting activity is deferred. The author-feed endpoint includes posts
and reposts and would require a separately tested reply/repost/quote definition,
timestamp policy and bounded completeness treatment. Profile counters are
sufficient for this task. No recent-window, latest-post, history, delta or
engagement field is inferred from `postsCount`.

## Publication transaction and UI boundary

Candidate `data.json` gains an independent top-level `bluesky` projection,
including provider, observation time and freshness policy. It is never nested
inside YouTube, Polymarket, attention or candidate signals. The renderer ignores
the object: no Bluesky markup, icon, profile link, follower value, CSS or browser
JavaScript is added. Unified presentation remains Task 4.

The existing publication-manifest schema 1.5 gains an independent
`candidate_bluesky` lane, preserving browser compatibility with the existing
manifest format; no browser validator change is required.
It hashes both artifact and mapping, validates them and the full current canonical
candidate universe, and derives evidence time solely from Bluesky `observed_at`.
No other provider's validity or metrics are substituted into this lane.

The existing candidate-family workflow collects once on its existing daily
10:41 UTC schedule or manual dispatch, after dependency checks. Other triggers
reuse the validated artifact. Collection failure blocks the transaction. Its
artifact joins the existing exact generated-output commit scope. Publication time
prefers the Bluesky collection step's completion timestamp, then YouTube, then
Polymarket, then the prior manifest publication time. Independent provider
observation times are preserved. PR/general validation and all normal tests stay
offline with synthetic fixtures. No secret or separate workflow is required.
