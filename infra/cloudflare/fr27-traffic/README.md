# FR27 traffic Worker

Repository preparation only: **no production route is active in this configuration**.
`wrangler.toml` explicitly has `routes = []`. Do not deploy as part of validation.
The existing validation deployment is https://fr27-traffic.driftsignals.workers.dev.
Keep all repository work on `feat/cloudflare-traffic-v1`; do not merge/rebase main
or activate production as part of this preparation.

## Architecture and privacy

On a future zone route, the Worker forwards the original request using
`fetch(request)` to the existing GitHub Pages origin, returns the same response
without reading or modifying its body/headers, and schedules eligible analytics
with `ctx.waitUntil`. Analytics errors are swallowed without logging request data.
Missing salt skips tracking; missing write binding or failed writes cannot change
the origin response. Origin fetch failures are not analytics failures and still
propagate. There are no cookies, browser scripts, reporting endpoints, synthetic
write endpoints, or admin endpoints.

On any `*.workers.dev` host, `/__health` returns:

```json
{"ok":true,"service":"fr27-traffic","mode":"validation","analytics":"disabled-on-workers-dev"}
```

Every other workers.dev path returns 404, with no origin fetch or analytics write.
On production, `/__health` has no special handling: it goes to GitHub Pages.

Eligible events are GET responses below 400 with a `text/html` MIME type.
Obvious bot user agents and `Purpose`/`Sec-Purpose` prefetch or prerender requests
are skipped. When a nonempty `Sec-Fetch-Dest` is supplied, only `document` and
`iframe` qualify. **Iframes remain eligible**, matching the original policy;
embedded documents can therefore add pageviews. Missing fetch metadata remains
eligible for browser compatibility. This is heuristic filtering, not proof of a
human visit; a qualifying HTML redirect below 400 can also count.

Stored in dataset `fr27_traffic` via the `TRAFFIC` write binding:

| Column | Meaning |
| --- | --- |
| `timestamp` | Analytics Engine event timestamp |
| `blob1` | URL pathname only, at most 300 characters; case, encoding and trailing slash preserved |
| `blob2` | Lowercase referrer hostname, stripping `www.` and a final dot, at most 200 characters; or `(direct)`, `(internal)`, `(unknown)` |
| `blob3` | Cloudflare country, or `XX` when absent |
| `blob4` | `desktop`, `mobile`, or `tablet` (UA heuristic) |
| `blob5` | `en` for `/en` or `/en/...`, otherwise `fr`; independent of browser language |
| `blob6` | Response status as a string |
| `double1` | Pageview count, always `1` |
| `index1` | Daily pseudonymous visitor ID; also Analytics Engine's sampling key |
| `_sample_interval` | Analytics Engine sampling weight |

The ID is the first 128 bits (32 hex characters) of HMAC-SHA-256 keyed by the
existing remote `FR27_ANALYTICS_SALT`. The message is UTC `YYYY-MM-DD`, newline,
Cloudflare connecting IP (or `unknown`), newline, first 300 UA characters.
**IDs reset every UTC day**, without rotating or replacing the salt. The same
IP/UA pair shares an ID that day; different IPs/UAs can split a person's visits.
Cross-day unique people cannot be inferred by deduplicating these IDs.

Raw IP and UA are processed transiently for HMAC/device classification, never
stored by this implementation. Query strings, fragments, full referrer URLs,
referrer credentials/ports/paths, request bodies and cookies are not stored.
Paths and referrer domains may themselves carry sensitive information. This
describes this Worker's dataset, not all Cloudflare/GitHub infrastructure logs.
Do not enable request logging that undermines this model.

Pseudonymization must **not automatically be described as anonymous under EU
privacy law**. Review the relevant privacy notice, lawful basis and retention
before activation; technical minimization alone does not establish compliance.
See the [EDPB pseudonymisation guidance](https://www.edpb.europa.eu/public-consultations/guidelines-012025-on-pseudonymisation_en).
Do not reveal, replace, delete, rotate, export or print `FR27_ANALYTICS_SALT`.

## Route strategy and quota

The proposed route is **`france2027.app/*`**, zone `france2027.app`, Worker
`fr27-traffic`. It covers both schemes and the apex only. `www` keeps its existing
redirect. GitHub Pages remains the origin; use a zone route, not a Custom Domain.

[Cloudflare routes](https://developers.cloudflare.com/workers/configuration/routing/routes/)
support more-specific no-script exclusions. However, the documented
[Wrangler route schema](https://developers.cloudflare.com/workers/wrangler/configuration/#types-of-routes)
and installed Wrangler 4.151.1 schema expose pattern/zone fields, not a no-script
assignment. Every configured route belongs to this Worker. Do not invent
`script = ""`, `script = false`, negated patterns, or Workers Static Assets
`run_worker_first` exclusions for this GitHub Pages origin. Dashboard changes can
be replaced by subsequent Wrangler deploys; see
[Wrangler deprecations](https://developers.cloudflare.com/workers/wrangler/deprecations/#route).
Use the simple route with **no manually maintained static exclusions**.

The production footprint audit at `43b80fc4dd0bb8a3c76f0b26ff15dc84fa426de2`
found 310 registry routes: root 1, agenda 14, candidates 47, en 155, enjeux 18,
sondages 75. `assets/` had 216 files (23 JS, 18 CSS, 175 images) and `locales/`
had 2 JS files, with no page source in either prefix. These are potential future
exclusions if a supported complete route-management model is adopted. `.github/`
is infrastructure. Other directories must not be presumed safe to exclude.

The tradeoff is that **all matching apex requests invoke the Worker**, including
static assets, bots, non-GETs and errors that never produce analytics. Code-level
filtering does not save invocations. With
[Workers Free](https://developers.cloudflare.com/workers/platform/limits/#daily-requests),
the account allowance is 100,000 requests/day, resetting at midnight UTC, shared
with other Workers. Monitor account request volume, not just pageview counts.
Quota exhaustion can create gaps in analytics.

**Set the production route to Fail open**: quota exhaustion bypasses the Worker
and goes to the origin; Fail closed returns error 1027. Cloudflare documents
this as a route toggle, not a Wrangler TOML field. Verify it in Domains & Routes
after activation and after every deployment; do not assume a default or that
Wrangler preserves it. This manual safety setting is distinct from route
ownership/exclusions. If the setting cannot be verified, do not leave the route
active. It is a quota fallback, not a guarantee against every runtime failure.
The Worker catches analytics failures separately. It does not use
`ctx.passThroughOnException()`, which is a different
[exception fallback with body/CPU limitations](https://developers.cloudflare.com/workers/runtime-apis/context/#passthroughonexception).

[Analytics Engine pricing](https://developers.cloudflare.com/analytics/analytics-engine/pricing/)
separately lists 100,000 writes/day and 10,000 read queries/day on Free, with a
current billing-availability caveat. Recheck current limits/pricing before
activation. No account/plan changes are authorized by this guide.

## Local validation

From `infra/cloudflare/fr27-traffic`, using Node 22 or later:

```powershell
npm ci
npm test
npx wrangler deploy --dry-run
npm run report -- pageviews
npm run report -- last7
```

The tests use Node's built-in test runner, Web APIs and WebCrypto. Origin fetches
and dataset writes are mocked; only dummy salts and documentation IPs are used.
They cover eligibility, workers.dev isolation, schema minimization, HMAC vectors
and UTC rotation, response preservation, write/scheduling failures, and local
report generation/HTTP error handling. The dry-run validates/bundles the Worker
without uploading it. It does not prove account permissions or remote writes.
Do not use `wrangler dev --remote` or add synthetic endpoints for this check.

Optional read-only validation of the **existing remote version**, without writing
events (workers.dev analytics is always disabled):

```powershell
curl.exe --fail-with-body https://fr27-traffic.driftsignals.workers.dev/__health
curl.exe -sS -o NUL -w "%{http_code}" https://fr27-traffic.driftsignals.workers.dev/
```

Expect the health JSON above and ordinary-path 404. These checks do not deploy
the locally edited code. Stop on test failures, unexpected repository/branch
changes, missing required credentials or unclear Cloudflare configuration.

## Private local reporting

The public Worker only needs `TRAFFIC` and the existing salt. `ANALYTICS_SQL` was
removed from repository configuration because no public runtime operation needs
read access. The existing deployed version remains unchanged until a separately
approved deployment. Reports run on the maintainer's machine using the
[dedicated Analytics Engine SQL API](https://developers.cloudflare.com/analytics/analytics-engine/sql-api/),
not the separate Analytics SQL binding/API dialect.

`npm run report -- <report>` prints inspectable SQL and makes **no network call**.
Add `--execute` to send the fixed aggregate query and print private JSON locally.
The script never starts an HTTP server, loads credentials from files, or retries
failed API requests. Supply `FR27_REPORT_ACCOUNT_ID` and `FR27_REPORT_API_TOKEN`
through your private local environment/credential tooling. The token needs
`Account > Account Analytics > Read`, restricted to the intended account where
possible; a Wrangler login does not automatically provide it. No hard-coded
credentials are provided. Do not use the analytics salt as an API token.

| Command suffix | Output |
| --- | --- |
| `pageviews` | Pageviews today, UTC |
| `daily` | Per-day pageviews and observed unique pseudonymous IDs |
| `pages` | Top 50 pathnames |
| `referrers` | Top 50 referrer domains/markers |
| `countries` | Top 50 countries |
| `devices` | Device split |
| `locales` | French vs English by path |
| `last7` | Daily report for the last 7 UTC dates including partial today |

Except `pageviews` (today), reports default to the last 7 UTC calendar dates.
`--days 1..31` changes this range; `last7` is fixed at 7. Every query has explicit
UTC lower/upper bounds and excludes **`blob1 = '/__synthetic_test__'`**, including
historical synthetic records. No public traffic should be generated for testing
before activation. Save any output only to private storage; local `reports/` is
gitignored. Never commit output or expose it through GitHub Pages.

For example, `npm run report -- daily --days 7` generates SQL equivalent to:

```sql
SELECT formatDateTime(timestamp, '%Y-%m-%d', 'Etc/UTC') AS day,
  SUM(_sample_interval * double1) AS pageviews,
  MAX(_sample_interval) AS max_sample_interval,
  COUNT(DISTINCT index1) AS observed_daily_visitor_ids
FROM fr27_traffic
WHERE timestamp >= toDateTime('<UTC start YYYY-MM-DD hh:mm:ss>', 'Etc/UTC')
  AND timestamp <= toDateTime('<UTC end YYYY-MM-DD hh:mm:ss>', 'Etc/UTC')
  AND blob1 != '/__synthetic_test__'
GROUP BY day
ORDER BY day ASC
FORMAT JSON
```

The script fills the date placeholders. `pageviews` uses the same filters and
weighted sum for today. `max_sample_interval > 1` indicates retained rows were
sampled. Pageviews use [sampling weights](https://developers.cloudflare.com/analytics/analytics-engine/sampling/);
`COUNT(DISTINCT index1)` counts only IDs present in the returned sample and cannot
reconstruct omitted visitors. Even a returned maximum of 1 does not prove no
IDs were omitted by adaptive sampling across many indices. Treat observed daily
IDs as a lower bound under sampling, never exact people; do not multiply distinct
counts by sampling weights or sum daily IDs into cross-day unique people.
Empty results/missing days may indicate no traffic, filtering, quota loss or
delayed data, not confirmed zero activity. Top-page/domain lists are capped at 50.

The prior protected synthetic validation demonstrated Worker write -> Analytics
Engine -> SQL read, but reads lagged writes. **Eventual consistency/latency was
observed**: retry read-only queries after a delay; do not infer write failure
from an immediate empty result. No latency SLA or exact delay was established.
The temporary test endpoints and temporary admin secret were removed; do not
recreate them. The local utility's live API execution needs the separate read
credentials and is not part of offline validation.

## Production activation — manual review required; not executed

1. Confirm the approved feature commit, clean worktree and unchanged remote
   branch. Repeat local validation. Confirm there is still no production route
   and GitHub Pages remains healthy through Cloudflare. Do not alter DNS, SSL,
   zone/account settings or secrets. Confirm the existing salt's installation
   without printing its value. Resolve any uncertainty before proceeding.
2. Obtain separate approval for production deployment/routing. The exact proposed
   **repository edit** replaces top-level `routes = []` with the following,
   immediately after `workers_dev = true` and before any TOML table:

   ```toml
   routes = [
     { pattern = "france2027.app/*", zone_name = "france2027.app" }
   ]
   ```

3. Validate and review that edit, then, **only after production approval**, run
   `npx wrangler deploy` from this directory. This deploys the reviewed Worker,
   drops its unused SQL binding, and attaches the apex route. It is a production
   change and must not be run during repository preparation. Keep workers.dev
   validation enabled. Do not create a second Worker/environment or new salt.
4. In Cloudflare Workers & Pages > `fr27-traffic` > Settings > Domains & Routes,
   verify the apex route and set its request-limit failure mode to **Fail open**.
   Plan this safety check before deploying and complete it immediately. If the
   toggle is unavailable or its state cannot be verified, remove the route and
   stop. Do not invent unsupported Wrangler flags to replace this check.
5. Repeat the origin checks below. After normal qualifying navigation, privately
   query the data allowing for delayed visibility. Check request quota and errors.
   Never add a public report endpoint. Retain the approved route edit in this
   branch so subsequent deploys use the same route list; recheck Fail open after
   each deployment.

## Verify origin continuity

Before activation, record baseline status, redirect location and representative
page/static content. After activation repeat:

```powershell
curl.exe -sS -D - -o NUL https://france2027.app/
curl.exe -sS -L -o NUL -w "%{http_code} %{url_effective}" https://www.france2027.app/
curl.exe -sS -D - -o NUL https://france2027.app/en/
curl.exe -sS -D - -o NUL https://france2027.app/agenda/
curl.exe -sS -D - -o NUL https://france2027.app/__fr27_missing_page_check__
```

Expect apex/root and real pages to remain 200, `server: cloudflare` and `CF-Ray`
to remain present, `www` to resolve to the apex, and an unknown path to retain
GitHub Pages' 404. Also open representative candidate/poll/issue pages and an
actual JS, CSS and image URL from the site; compare bodies, content types,
redirects and load behavior to the baseline. The Worker must not alter them.
These checks demonstrate continuity through Cloudflare; alone they do not prove
the Worker ran or that the underlying GitHub Pages configuration is correct.
The existing zone/mail verification is baseline context; do not change records.

## Production rollback — manual, if subsequently activated

For availability trouble, first detach **only** the `france2027.app/*` route from
`fr27-traffic` in Domains & Routes. Traffic then bypasses the Worker to the same
GitHub Pages origin. Do not delete the Worker/dataset/salt or change DNS/SSL.
Restore top-level `routes = []` in the repository, validate and commit it before
any later deployment so a deploy cannot silently reactivate the route. If using
Wrangler for a non-emergency detach instead, the approved `routes = []` config
plus `npx wrangler deploy` removes the route; it is also a production change.
Repeat origin and workers.dev health checks. Analytics gaps are acceptable;
public availability takes priority. Do not rely on a code-version rollback alone
to remove a route.

Routing/configuration references were checked against official Cloudflare docs
on 2026-10-17 and the locked Wrangler schema. No production deployment, route,
fail-mode setting, account setting or secret change is included in this work.
