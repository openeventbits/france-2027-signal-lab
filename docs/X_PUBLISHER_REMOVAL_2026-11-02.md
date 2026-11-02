# Automated X publisher removal — November 2, 2026

## Local scope and fresh baseline

Repository: `openeventbits/france-2027-signal-lab`.
Fetched `origin/main`: `d4640fb6e1466f33e198d25deed159d148d3e88a`.
Implementation began in a new isolated, detached worktree:
`C:/Users/Tanya/.codex/worktrees/remove-x-publisher/france-2027-signal-lab`.
The `issues-eligibility-audit` worktree and its three uncommitted files are
preserved separately. Its repair was neither copied wholesale nor committed.
At the initial local handoff, no commit, push, PR, merge, deployment or
production workflow had been performed.

The fresh baseline shared/product selection ran 63 tests: 61 passed and the two
known X-product expectations failed: the English Issues variant count (`3 != 4`)
and Candidate Media Pulse's expected `raphael-glucksmann` versus actual
`antoine-mikolajczak`. Both removed products are retired by this change; neither
failure is described as a repaired dashboard calculation.

Read-only GitHub workflow metadata reported `Publish FR27 to X`, workflow ID
375292456, as `disabled_manually`. The GitHub CLI was used because the connected
GitHub tool set does not expose workflow activation metadata. No setting was
changed. The latest five workflow-run summaries are all completed (two success,
three skipped, dated October 8, 2026); these metadata reads do not verify actual
Buffer delivery and do not access credentials or post/account state. The
retained local remote-tracking `origin/social-assets` reference is
`9a9a294d952d7f85faf30979c3aea6455de7ccfc`.

## Inventory and classification

### A — exclusive automated publishing components removed

These 30 exclusively obsolete files are removed. The old
`social/requirements.txt` path is the 31st removed path, relocated unchanged as
an optional manual-research dependency file in section C below:

- `.github/workflows/publish-x-fr.yml`
- `social/candidate_media_pulse.py`
- `social/daily_plan.py`
- `social/daily_queue.py`
- `social/newsroom_products.py`
- `social/planner_readiness.py`
- `social/queue_metadata.py`
- `social/radar_media.py`
- `social/signal_engine.py`
- `social/social_publish.py`
- `social/weekly_flagship.py`
- `social/weekly_flagship_catchup.py`
- `test_social_buffer_delivery_safety.py`
- `test_social_buffer_scheduling.py`
- `test_social_buffer_workflow.py`
- `test_social_candidate_media_pulse.py`
- `test_social_daily_plan.py`
- `test_social_daily_queue.py`
- `test_social_event_roundup.py`
- `test_social_launch_hardening.py`
- `test_social_newsroom_planner.py`
- `test_social_newsroom_products.py`
- `test_social_planner_trigger.py`
- `test_social_publish.py`
- `test_social_radar_media.py`
- `test_social_scheduler_tick.py`
- `test_social_signal_engine.py`
- `test_social_weekly_flagship.py`
- `test_social_weekly_flagship_catchup.py`
- `test_social_workflow.py`

The removed workflow contained its scheduled queue construction, exact-slot and
heartbeat triggers, producer `workflow_run` fan-in, Buffer scheduling and delivery
reconciliation, credential handling, bootstrap/state persistence, and manual
publishing/catch-up entrypoints. Removing it leaves every other producer and
Pages/publication workflow in place.

The Python removal covers the Buffer GraphQL client and post sender, immutable
post queues, planner/readiness barriers, slot scheduling, duplicate recovery,
state/quota/receipt management, publication-specific captions and ranked newsroom
products. No remaining workflow installs the URL decoder dependencies.
The URL decoder's optional dependency pins are preserved only for manual
research, as described below. No installed package or unrelated dependency was
uninstalled.

`social/signal_engine.py` is the obsolete planner's article-count scoring engine,
not a dashboard authority. Its only non-test consumer was the retired planner's
explicit legacy compatibility getter; V2.1 planning did not load it. It used
separate editorial weights, evidence floors and topic exclusions, and Issues
article shares rather than canonical source-day incidence. Removing this legacy
X ranking does not remove or change any canonical analytical threshold.

`social/candidate_media_pulse.py`, `radar_media.py` and `weekly_flagship.py`
consume existing dashboard/history authorities to select, constrain and format
posts. No public dashboard producer imports them. Their slot, caption-length,
publication freshness, route/receipt and editorial selection gates are obsolete
with their delivery consumer. Candidate visibility counts, publisher shares,
source-day metrics and history validation remain in their original authorities.

### B — shared analytics and publication preserved

- `coverage_metric_contract.py`: complete-day/week snapshots, evidence and
  denominator identities, raw/displayed values, deterministic ranking, bilingual
  labels, URLs and interpretation boundaries. Only its module docstring changes;
  the complete executable AST is equal to baseline.
- `issue_page_contract.py` and `agenda_page_contract.py`: calculation authorities,
  canonical taxonomy, public-page lifecycle, source diversity, evidence floors,
  missing/zero distinctions and historical compatibility. Byte-identical.
- All Issue/Agenda history, live projection and page builders; route registry,
  semantic entrypoints and publication manifests. Byte-identical. The site's
  production publication queue, Pages orchestration and producer concurrency
  locks are retained; they publish dashboard data, not X posts.
- `fetch_news_wire.py`, candidate visibility/history contracts and builders,
  Candidate Signals, candidate registries and public Media Pulse models.
  Byte-identical, including PR #330's complete UTC periods and retained-publication
  read compatibility.
- News inventory, corpus, source registries/provenance, polling, candidate evidence,
  current/historical observations and all immutable fixtures. No data regeneration.
- Candidate YouTube/Bluesky public-account research and OG/social-sharing metadata
  remain; neither is the project's automated X delivery subsystem.

### C — manual research tools preserved

`social/capture_social_panel.py` remains at its established path. Only the CLI
help description now says manual research. It still captures a stable published
panel and optionally exports metrics from that same render. No capture algorithm,
selector, geometry or output contract changes. Optional Playwright installation
is documented for manual use; it is not a production publishing dependency.

`social/README.md` now documents source-backed manual research, the neutral
snapshot APIs, candidate histories, source evidence and optional captures. A
read-only runnable Issues snapshot example produces all eight canonical rows
for October 26–November 1, 2026. Research output goes to `_trace_output`, not
protected evidence directories. The root README links to this guide instead of
advertising weekly X publishing and Buffer recovery.

The five reusable URL helpers (`_valid_http_url`, `_url_host`,
`_is_google_news_url`, `_decode_google_news_urls`, `resolve_publisher_urls`) are
extracted from `social/social_publish.py` into `tools/resolve_source_urls.py`.
Their lookup/filter/deduplication algorithms are preserved; the optional-install
error points to the new path. A read-only CLI prints the mapping without changing
source records. Failed or unverified decoder results remain excluded. Five new
offline tests cover direct URLs without dependencies, batching/deduplication,
successful decoder-status and non-Google HTTP result filtering, network failure,
missing optional packages and CLI output. No live decoder call was made during this task.

`social/requirements.txt` is relocated byte-for-byte from its committed content to
`tools/research-requirements.txt`, retaining `googlenewsdecoder==0.2.1` and
`selectolax==0.4.13` as optional manual-research dependencies. These packages are
useful for source checking, so are not treated as obsolete. No production job
installs them. Capture's optional Playwright support remains documented as well.

No production analytical authority needed relocation: all were already outside
`social/`. The useful capture tool retains its existing path.

## Shared tests and CI changes

The 18 removed test modules exercise only retired X clients, copy, scheduling,
queues, state, publication selection and workflow behavior. Their arithmetic
checks were checks of X consumers, not the sole tests for dashboard producers.
Existing independent source/history/Media Pulse/page/publication tests remain.

`test_issue_shared_metric_authority.py` drops only the obsolete newsroom-product
method that counts and formats X variants. All 17 independent authority, source-
day, numerator/denominator, rounding, window, canonical URL, missing/zero,
multilabel and historical tests remain. The separate investigation's new X-gate
regression is deliberately not carried forward after its product is retired.

`test_agenda_shared_metric_authority.py` drops the newsroom import and only the
product-generation tail of the optional-ranking-filter test. All 13 independent
shared/page/history tests remain, including proof that excluding polling from an
optional ranking does not remove it from the denominator. The three shared test
modules use neutral `metrics` names instead of the former `social` alias; the
third file's only change is a descriptive test-method rename.

The dashboard smoke workflow replaces `test_social_publish` with the three shared
metric modules and `test_publisher_retirement`. The latter checks that production
Python imports no retired modules and active workflow sources contain no X
client paths, credential configuration or historical-state branch writers.
It does not change producer triggers, schedules, permissions or publication steps.

## Validation

All commands run locally with UTF-8. Git Bash is selected explicitly for offline
workflow transaction tests; no production workflow is dispatched.

| Selection | Result |
|---|---|
| Shared Issue/Agenda/coverage and retirement boundaries | **39 passed**, 7.550 seconds |
| Retained manual URL lookup (final evidence-preservation regression included) | **5 passed**, 0.253 seconds |
| Media Pulse, candidate visibility, news provenance and PR #330 compatibility | **163 passed**, 25.236 seconds |
| Issues/Agenda/pages/history/frontend/routes/publication/workflow integration | **427 run, 426 passed**, 546.469 seconds; one independently verified baseline assertion below |
| Complete updated dashboard PR smoke selection | **869 run, 868 passed**, 1629.458 seconds; one unchanged provider replay exceeded its existing 180-second subprocess limit. The exact case then **passed alone in 132.123 seconds**, with the same assertions and timeout |
| Dashboard election-scope Python tests | **13 passed**, 93.028 seconds |
| Dashboard Node scope/source-projection suites | Both pass |

The full smoke invocation exited 1 because
`test_candidate_provider_rosters.ProviderRosterTests.test_actual_workflow_post_rebase_regeneration_and_exact_generated_scope`
raised `subprocess.TimeoutExpired` under the Windows full-run load. Its isolated
rerun exited 0. Every selected method therefore passed, but a single all-green
full invocation is not claimed. No test, timeout or source expectation was
relaxed. Offline workflow-body tests use temporary local bare remotes; they do
not commit or push to the project worktree or its GitHub remote.

The remaining integration failure is
`test_policy_agenda_frontend.PolicyAgendaFrontendTests.test_poll_compare_is_not_a_workspace`.
It expects the old literal `label: translate("signal_board.issues", "ISSUES")` in
`assets/hybrid-dashboard.js`. Both that script and the test are byte-identical to
baseline. A separate one-test run reproduces the same failure in 0.020 seconds.
It is unrelated to delivery removal and remains enabled and unchanged.

Official read-only checks pass for publication manifests, bilingual semantic
entrypoints, Agenda pages, route registry, all active candidate artifacts and
election scope. The Issues-page and two live-projection raw byte checks report
mismatches on this CRLF Windows checkout. Independent fresh generation matches
**exact committed Git blobs** for both live projections and **all 36 French/English
Issues pages plus their manifest**, and matches normalized working bytes. These
are checkout line-ending differences, not stale projections; no production files
were rewritten. All eight canonical issues remain current-qualified.

The manual research command in `social/README.md` was executed successfully and
exports eight canonical weekly issue rows. The five relocated URL-helper
algorithms authenticate to the baseline AST after only the installation-message
path change; their dependency file matches the original committed bytes. No
live decoder lookup or external delivery call was made.

Logs are `_trace_output/x-removal-baseline.log`, `x-removal-shared.log`,
`x-removal-research-final.log`, `x-removal-media-news.log`, `x-removal-integration.log`,
`x-removal-unrelated-baseline.log`, `x-removal-dashboard-final.log`,
`x-removal-provider-replay.log`, `x-removal-artifacts.log` and
`x-removal-artifact-parity.log`. The first smoke
startup was stopped after two test-alias references were caught and corrected;
the complete final selection is reported above, without hiding test failures.

The unchanged manifest warnings concern Commission notices 10333, 10327, 10319,
10264 and 10260. This is not a full repository test run: the earlier audit's three
localization methods were not rerun or repaired.

## Preservation and complete changed-file inventory

All **1,078 retained, unmodified tracked files** match raw SHA-256 hashes from
this worktree's fresh baseline. This includes **152 JSON files**, **393 frontend
HTML/CSS/JS files**, and **all 53 immutable fixture files**. News inventory/corpus,
source provenance, polling, candidate data, historical Issue/Agenda/visibility
observations and published dataset/page manifests are unchanged. No source
classification, evidence floor, completeness boundary or eligibility threshold
is changed.

The executable coverage-contract AST is identical to baseline; only its module
documentation changes. Every other retained analytical implementation is
byte-identical. Preservation metadata is stored locally in
`_trace_output/x-removal-inventory.json` and `x-removal-preservation.json`.
The old Issues worktree's three file hashes match their initial values, and the
`origin/social-assets` reference is unchanged. No actual publishing state JSON
was tracked in the removed main-branch directory; historical records remain on
the separate branch and in Git history, with no migration or deletion.

Besides the 30 deletions and the old dependency path relocated above, the
complete intended modified/added file list is:

- `.github/workflows/validate-dashboard.yml` — preserved analytical tests and
  retirement boundary checks replace the retired publisher selection.
- `README.md` — removes the obsolete X/Buffer operating instructions and points
  to manual research.
- `coverage_metric_contract.py` — neutral module documentation only.
- `social/README.md` — manual-research guide replaces publisher instructions.
- `social/capture_social_panel.py` — manual-research CLI help only.
- `test_issue_shared_metric_authority.py` — removes obsolete X assertions;
  preserves independent metric/history/page checks.
- `test_agenda_shared_metric_authority.py` — removes obsolete X consumer checks;
  preserves authority, ranking-filter and denominator checks.
- `test_coverage_metric_contract.py` — neutral descriptive method name only.
- `test_publisher_retirement.py` — new production dependency/workflow boundary tests.
- `tools/resolve_source_urls.py` — reusable URL helpers extracted into a manual
  source-checking tool with no delivery client or publication state.
- `tools/research-requirements.txt` — exact optional dependency pins relocated
  from `social/requirements.txt`; no production installation.
- `test_source_url_resolution.py` — offline coverage of the retained lookup and CLI.
- `docs/X_PUBLISHER_REMOVAL_2026-11-02.md` — this inventory and handoff.

Historical cross-topic audit/review documents remain historical records; their
mentions of prior X tests/runs do not activate or import publishing code.
Ignored `_trace_output/x-removal-*` files are local diagnostics/research only,
not generated production artifacts or historical publishing records.

## External cleanup requiring separate authorization

No Buffer/X credentials or account state were accessed or modified. The following
names come from the retired workflow's source, not secret values:

| External configuration | Later manual review |
|---|---|
| GitHub secret `BUFFER_API_KEY` | Remove if unused elsewhere; revoke the corresponding token only with approval. |
| GitHub variable `BUFFER_ORGANIZATION_ID` | Remove the retired workflow's configuration if unused elsewhere. |
| GitHub variable `BUFFER_X_CHANNEL_ID` | Remove the retired workflow's channel configuration if unused elsewhere. |
| GitHub variable `FR27_SOCIAL_ENABLED` | Remove the obsolete activation flag. |
| GitHub variable `FR27_BUFFER_SCHEDULING_ENABLED` | Remove the obsolete scheduling flag. |
| Buffer's connected X channel and any already scheduled deliveries | Review separately; removing GitHub code does not cancel posts already handed to Buffer. No delivery state was inspected. |
| `social-assets` branch, JSON records, old Actions logs/artifacts | Retain as historical records; no deletion or state migration is proposed. |

Do not revoke shared GitHub, candidate-provider or dashboard credentials. Do not
delete existing X posts, the historical branch or publishing records. No remote
workflow disabling/enabling/deletion was performed; the retired workflow remains
on production until a separately authorized change is merged/deployed.

## Risks and next authorization boundary

**GO for review and subsequent authorized commit/PR preparation after the fresh
synchronization below.** No production dependency on the removed publisher was
found. Shared analytical behavior and source evidence are preserved; no artifact
regeneration is necessary. All smoke-selected methods pass with one isolated
replay following a full-run timeout. Disclose that timing limitation and the
unchanged frontend-label baseline failure; this is not an all-repository-green
claim.

The retained optional URL decoder was tested offline; live third-party lookup
availability was not asserted. Current production still has its disabled X
workflow until an authorized repository change is merged/deployed. This local
removal does not cancel any delivery already handed to Buffer. External account,
credential and pending-post cleanup remains a separate authorization boundary.

Before any later authorized commit or PR: fetch `origin/main` again, record and
inspect intervening commits and path overlaps, synchronize this isolated worktree
without overwriting newer automated data, then rerun the affected validations.
Today's results apply to the baseline SHA above, not to an assumed future main.
Never force-push. The initial handoff did not authorize repository publication.
The subsequent owner instruction authorizes commit, normal push and a review PR
only after these checks; merging, manual deployment, production workflow dispatch
and external Buffer/X cleanup remain unauthorized.

## Final owner-authorized commit/PR preparation

- Re-fetched `origin/main`: `d4640fb6e1466f33e198d25deed159d148d3e88a`, identical
  to the implementation baseline. There are no intervening commits or overlapping
  upstream changes, and no synchronization rewrite is necessary.
- Review branch: `codex/remove-x-publisher` in the same isolated worktree.
- The complete 44-path inventory matches this report: 30 exclusive deletions,
  the old optional requirements path relocated, eight modified tracked paths
  and five added paths. Git may represent the requirements move as one renamed
  file rather than two path statuses.
- Rechecked all 1,078 retained/unmodified tracked-file hashes, including all
  152 JSON files, 393 frontend files and 53 immutable fixtures. Shared analytical
  implementations, the original Issues worktree and `social-assets` are preserved.
  The coverage executable AST and extracted research helpers still authenticate
  to baseline. No dataset or generated dashboard artifact changes are intended.
- Final focused selection: **207 tests passed in 8.398 seconds**, covering shared
  metrics, retirement boundaries, manual research, Media Pulse, news provenance
  and all nine PR #330 regressions. The initial sandbox invocation encountered
  temporary-directory ACL errors; the identical selection passed with normal
  temporary-file access, without source or assertion changes.
- Freshly generated live projections and all 36 FR/EN Issues pages plus their
  manifest still match exact current-main Git blobs. Publication-manifest,
  bilingual entrypoint and route-registry check commands pass. Existing five
  unresolved Commission-notice warnings remain unchanged.
- The complete smoke outcome remains **868/869 passed in the full invocation**;
  the provider replay that timed out subsequently passed alone in 132.123 seconds
  with unchanged 180-second timeout/assertions. The independently reproduced
  frontend-label baseline failure remains unchanged. No all-green full-smoke
  invocation or all-repository-green result is claimed.
- Only the explicit reviewed inventory may be staged. Diagnostics and research
  output remain ignored. Whitespace checks must pass before the authorized commit.
- Remaining production workflows retain main-only branch/path gates; this feature
  branch and review PR do not dispatch production workflows. No credential,
  historical-record, `social-assets`, post or scheduled-delivery cleanup is included.

Final check logs: `_trace_output/x-removal-precommit-focused-final.log` and
`_trace_output/x-removal-precommit-artifacts.log`.
