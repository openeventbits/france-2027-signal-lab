# OpinionWay / Sébastien Bonnal: reviewed documentary publication

Notice 10264 is published as a source document, through the same bilingual page
and separately labeled browsing mechanism as 10319 and 10333. No numerical
observation, wave, study, candidate score or analytical eligibility is added.
The numerical coverage warning remains unresolved.

## Source authentication and unchanged evidence

The [original Commission PDF](https://www.commission-des-sondages.fr/notices/files/notices/2026/septembre/10264-pres-opinionway-facebook-15-septembre.pdf)
was independently downloaded and authenticated before this change:
SHA-256 `3e427407804098116e859a47f1ba3b0d0428145714b35c593e900e800768cd27`.
The published column on PDF p12 was visually checked against all eleven frozen
rows in `poll_source_tables.json`. The whole original table, methodology, bases,
review decision and source-table ID remain unchanged. Its individual record pin
remains `90fd17b6433f8af12e7fa0cd4914b142e91148e8da8d5e4d5c97e9f1feaacc70`.

| Published candidate | Published result |
|---|---:|
| Nathalie Arthaud | 1% |
| Jean-Luc Mélenchon | 16% |
| Fabien Roussel | 2% |
| Marine Tondelier | 3% |
| Raphaël Glucksmann | 12% |
| Gabriel Attal | 7% |
| Sébastien Bonnal | <1% |
| Édouard Philippe | 15% |
| Bruno Retailleau | 7% |
| Éric Zemmour | 3% |
| Marine Le Pen | 34% |

The exact-result subtotal is 100; this does not authorize normalizing the table,
dropping Bonnal or substituting 0, 0.5 or 1 for the strict upper bound.
Non-expression is separately published as 13%, not another candidate score.

PDF p2 identifies Sébastien Bonnal as commissioner and purchaser. “Facebook” is
the Commission listing label; it is disclosed as such, never substituted for
the actual commissioner. Methodology p3 gives fieldwork 2–4 September 2026,
1,034 adults and 951 registered voters. Pages 4/12 identify 700 certain voters
(ratings 9+10), a separate base rather than an expressed-intention count.
An expressed base is not reported. Template references to 903 people do not
override those bases. The selected weighting is sociodemographic + 2022
presidential first-round recall among certain voters, not a 2024 weighting
borrowed from another notice.

The notice is listed on 15 September. The study's publication date is
unconfirmed: the documentary projection stores null and titles/browsing labels
use the verified fieldwork interval. No day is inferred from the filename.

## Finite publication review

`FR27-10264-DOCUMENTARY-PUBLICATION-20261029` extends only the public-route
allowlist and browsing projection. Removing that publication review and its
10264 route reconstructs the exact prior collection digest
`2210c4943c4984099bf2c217433a8e4d4e0ed656052f5794c1c5c08c473c4737`.
All five individual table records, old page associations and the CNEWS
extension review are preserved. The new complete collection pin is
`189049b0d313ee734e316a13e2353acd1853ba21616adbfffd3d4b0458604828`.
Collection and individual-row authentication remain mandatory; no runtime
pin regeneration is introduced.

Public routes:

- `/sondages/documents/opinionway-bonnal-10264/`
- `/en/sondages/documents/opinionway-bonnal-10264/`

They use the existing poll-detail shell, canonical URLs, FR/EN/x-default
alternates and index/follow policy. The existing route registry registers them
as `poll-source-evidence`, and the sitemap publishes both. Static content and
the separately labeled documentary links are crawlable without JavaScript.
This enables search-engine discovery; it does not promise indexing or ranking.
The local preview helper remains noindex and unregistered.

Documentary pages increase from four to six (two to three source tables).
Numerical wave, observation, candidate, institute and page counts do not change.
The complete, institute and candidate browsing directories retain typed results;
Bonnal can be browsed as a documentary candidate without joining the numerical
candidate picker. The older fieldwork date does not artificially place this
record among the latest polls.

The read model has no numerical event/wave ID or scalar candidate score for
this table and sets analysis_eligible false. Charts, ranges, headline scores,
rankings, comparisons and runoff calculations still consume numerical waves
only. Browser validation specifically rejects Bonnal being changed to an exact
0, 0.5 or 1, a fabricated publication date, changed provenance or a preview URL.
The source-table ID and candidate identities are reused, not recomputed.

The OG refresh writer's explicit allowed-file list includes the two new pages,
so a future authorized cover refresh can rebuild them through the existing
builder. No workflow was triggered and no scheduling or ingestion rule changed.

## Future native bounded-score analytical contract (not implemented)

A separate design/review would need:

- A versioned atomic result type preserving the literal, exact values and
  exclusive upper bounds, with explicit units, denominator, population,
  weighting, rounding and provenance. Missing, absent and source-dash results
  must stay distinct from bounded measurements.
- Validators and serialization rules that never coerce bounds into point
  estimates, including at the strict 1% endpoint and at zero.
- Explicit downstream support or exclusion in every chart, range, ranking,
  comparison, headline and export. Overlapping intervals do not establish an
  ordering or exact difference; unsupported consumers must fail closed.
- A separately reviewed admission/correction mechanism preserving historical
  observations, IDs, study bindings and scenario anchors. A documentary route
  cannot silently activate analytical admission.
- A reviewed definition of faithful typed numerical coverage, complete lineup
  authentication and migration tests for exact/bounded mixtures, duplicate and
  missing configurations, source drift and every legacy scalar consumer.

This PR implements none of that analytical contract. The five unresolved
Commission decisions, including 10264, remain unchanged. The three known
10339 integration errors remain outside scope, as does notice 10342.

## Validation on 29 October 2026

Starting and final fetched `origin/main`:
`ec679f7e28d9bf206d7727e1ff322eb5d8837111`. No intervening commit required
synchronization. The main checkout was not edited.

Latest results across 622 distinct Python tests: 619 passed and the three
known baseline 10339 errors remained. The broader publication run executed 330
tests and initially found one CNEWS-only hub assertion; that assertion now checks
each authenticated commissioner and the complete candidate lineup. The full
seven-test hub module passed on rerun. The provenance run executed 192 tests with
only the three known errors. All 100 publication-manifest tests passed.
An earlier focused check used the route registry before regeneration; the
complete page, route and sitemap checks subsequently passed.

| Module | Latest result |
|---|---|
| `test_bonnal_source_publication` | 8 passed |
| `test_poll_pages` | 44 passed |
| `test_poll_explorer` | 45 passed |
| `test_poll_hub_static_links` | 7 passed |
| `test_route_registry` | 31 passed |
| `test_search_foundation` | 27 passed |
| `test_poll_scope` | 13 passed |
| `test_poll_studies` | 15 passed |
| `test_reviewed_scenario_coverage` | 65 passed |
| `test_frontend_facts` | 20 passed |
| `test_runoff_workspace` | 43 passed |
| `test_update_polls_contract_runner` | 12 passed |
| `test_commission_notice_coverage` | 32 passed |
| `test_commission_notice_discovery` | 41 passed |
| `test_commission_reconciliation_review` | 13 passed, 3 known baseline errors |
| `test_reviewed_source_retention` | 16 passed |
| `test_reviewed_cluster17_source_retention` | 17 passed |
| `test_poll_ingestion_stability` | 21 passed |
| `test_polling_accuracy_batch1` | 21 passed |
| `test_commission_coverage_batch2` | 27 passed |
| `test_publication_manifest` | 77 passed |
| `test_publication_manifest_registry_v2` | 23 passed |

The unchanged `CurrentReconciliationIntegrationTests` errors are:

- `test_live_cli_replays_cached_sources_twice_with_all_454_objects_unchanged`
- `test_production_layers_reproduce_only_the_three_audited_decisions`
- `test_registry_baseline_authenticates_original_scope_and_exact_reviewed_delta_without_mutation`

Each still reports `Reviewed Commission registry addition changed: commission:10339`.
No assertion was skipped, repinned or removed for 10339 or 10342.

Both `node test_poll_source_projection.js` and `node test_poll_scope.js` passed,
including source-only candidates, exact-value coercion negatives, chronological
browsing, ranges, charts, headline eligibility and raw-data preservation.
Page/hub builders, route registry, sitemap, search entrypoints, study/scope
validators and publication-manifest check mode all passed.

Browser checks verified both languages, language switching, the original PDF
link, documentary-section navigation and Bonnal's candidate directory entry:
“No numerical observation”, zero numerical waves, one documentary source and
the original `<1%` literal. Polling counts remain 83 total numerical waves;
the default 2027 projection remains 78 waves / 343 scenarios, and the full
corpus remains 83 waves / 349 first-round scenarios / 166 numerical pages.

A raw SHA-256 audit of all 1,090 pre-existing tracked files found exactly the
20 intended source/test/artifact changes; the other 1,070 files were byte
identical. In particular all numerical observations, study bindings, candidate
identities, historical reviews, registry decisions, 166 numerical pages, four
prior documentary pages and the publication manifest are unchanged. The complete
numerical explorer projection and both prior documentary projections also
compare equal to the baseline.

The five warnings remain: 10333, 10327, 10319, 10264 and 10260. Documentary
publication does not change their numerical coverage decisions. The next step
is PR review; native bounded-score analytics require the separate contract
review outlined above. Study publication date and the expressed-vote count
remain unconfirmed rather than inferred.
