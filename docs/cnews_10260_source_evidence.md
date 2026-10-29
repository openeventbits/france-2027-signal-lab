# OpinionWay / CNews 10260: documentary publication of H3

This review publishes only the existing authenticated third first-round
configuration, H3. It extends the mechanism introduced for 10319/10333 and
[10264 in PR #322](https://github.com/openeventbits/france-2027-signal-lab/pull/322),
whose exact commit `16160ad72c580e35595802e2ee04a1380566b61f` was inspected.
No numerical score contract, ingestion rule, observation or historical identity
is changed. The entire H3 table remains `excluded_whole_table` from numerical
comparisons, and notice 10260 remains unresolved for numerical coverage.

## Authenticated source and complete H3 table

The [original Commission PDF](https://www.commission-des-sondages.fr/notices/files/notices/2026/septembre/10260-pres-iv-opinionway-cnews-11-septembre.pdf)
was downloaded independently: 578,568 bytes, 17 pages, SHA-256
`bcc6f5e46048615f31188b9d98cd708339f276e8fe959d3c9c1b5833a1d58b0c`.
The published column on PDF p14 was rendered and visually checked against the
frozen transcription, in original source order:

| Candidate | Published result |
|---|---:|
| Nathalie Arthaud | <1% |
| Jean-Luc Mélenchon | 17% |
| Fabien Roussel | 2% |
| Marine Tondelier | 3% |
| Raphaël Glucksmann | 9% |
| Karim Bouamrane | <1% |
| Gabriel Attal | 7% |
| Édouard Philippe | 15% |
| Bruno Retailleau | 7% |
| David Lisnard | 2% |
| Nicolas Dupont-Aignan | 2% |
| Éric Zemmour | 2% |
| Marine Le Pen | 34% |

Both `<1%` values remain strict upper bounds, without an exact percent. The
exact-value subtotal is 100; no normalization or inferred 0, 0.5 or 1 is allowed.
Other weighting columns contain different representations and do not replace
the explicit `Publié` column.

The unchanged documentary source-table ID is
`fr27-source-table-v1:13c78f8439b7a6183f043bf9c6cadd0f93e6d3cfb847a2734329240317557b24`.
The unchanged individual record SHA-256 is
`535cb08075a8c3bb1eb9b8d9ddd0178b7296308872490e546e03c19250369788`,
and the original review is `FR27-SST-P1-TABLE-10260-P14`.

PDF p2 identifies OpinionWay and commissioner/purchaser `CNews`. This exact
authenticated spelling is retained; existing 10319/10333 `CNEWS` records are
unchanged. Methodology p3 gives fieldwork 9–10 September 2026, 1,001 adults aged
18+, 935 registered voters, online CAWI collection and demographic quota sampling.
Pages 4/14 identify 690 respondents certain to vote (ratings 9+10). The expressed
base is not separately documented. Template “903 people” labels do not override
these bases. The Commission listing date is 11 September; the study publication
date remains unconfirmed and the browsing projection stores null.

The retained methodology is sociodemographic weighting plus first-round recall
for the 2022 presidential and 2024 legislative elections among respondents certain
to vote. Non-expression, 15%, is independently reported using sociodemographic
weighting across all respondents (pp3/14); it is not a fourteenth candidate.
The H3 question and its blank/invalid and abstention options are on p6.

## Relationship among the five configurations

| Configuration | PDF page | Existing representation |
|---|---:|---|
| H1, François Hollande | 12 | Numerical first-round observation, unchanged |
| H2, Ségolène Royal | 13 | Numerical first-round observation, unchanged |
| H3, Raphaël Glucksmann | 14 | Existing typed table; bilingual documentary publication added |
| Mélenchon / Le Pen, 33% / 67% | 15 | Numerical runoff observation, unchanged |
| Philippe / Le Pen, 45% / 55% | 16 | Numerical runoff observation, unchanged |

The existing numerical first-round wave is `wave-5cfde20f50cfb247`, containing
exactly two numerical scenarios. The new documentary entry uses
`survey_id: commission:10260`, its existing source-table ID, and no numerical
event/wave ID, comparison vector or scalar candidate score. It represents H3
of the same study, not another independently measured survey.

Four preserved complete observation objects were authenticated before the change:

| Configuration | Immutable event ID | Complete object SHA-256 |
|---|---|---|
| H1 | `34b67c973777cf14f9c19068b4642d119367e3312053f442ba16e9612c051cac` | `982c06ab3e9bbcada39561b9bca84674d5028f3e69a36a71d43fc79c5bde3ec0` |
| H2 | `547d14cf13fb2f407e743b91f6347dad9c0a3db48e750b380bdfc27b8fede2cd` | `5432011f93502846bd0a02709ecdad5d9e38ca563d06ddfc21621d9715786d1f` |
| Runoff 1 | `74f414c18b471202a9e99991b3aef62a3765aab33af40c333c19c1275ef7cd67` | `a0b80d5a1bdf899987747374e567af501ac74548981caee822250ebc3358fd2c` |
| Runoff 2 | `fdf663f564346145574ec28b75f4f9810bc2501065aa6790f9fb014e9148eea4` | `724a206992de5c13a36f82ef279f0b0a19174e350e66b452f1db51479c5d0f02` |

Object hashes use the existing source-table canonical JSON digest function.
Runoff scores and lineups were compared to pp15–16; first-round H1/H2 lineups
and published values were compared to pp12–13. Historical runoff metadata still
records `sample_size: 1001`, `sample_scope: reported`, and commissioner null.
Those migrated representations are preserved verbatim; this documentary review
does not retrospectively correct them using the PDF's distinct respondent bases.

## Finite publication review and browsing

`publication_review_10260` records
`FR27-10260-H3-DOCUMENTARY-PUBLICATION-20261029`. Removing only that review and
the added 10260 standalone-route entry reconstructs the exact prior collection:
`189049b0d313ee734e316a13e2353acd1853ba21616adbfffd3d4b0458604828`.
The new collection pin is
`be4d8aa8c8059675d8d2e55246375885445bdcfe45cb8eb6be29ce689e3e9cf3`.
All five original records, their individual pins, the numeric-page associations,
the CNEWS extension review and the 10264 publication review remain unchanged.
The loader still authenticates the complete collection and each table. No
runtime repinning or PDF fetching is introduced.

Public routes:

- `/sondages/documents/opinionway-cnews-10260/`
- `/en/sondages/documents/opinionway-cnews-10260/`

The existing poll detail shell, source card, canonical URLs, FR/EN/x-default
alternates, index/follow policy, `poll-source-evidence` registration and sitemap
builder are reused. Titles and browsing use verified fieldwork dates. H3 is
explicit in page titles, explanatory text, source-section links, static and
runtime complete/institute/candidate browsing labels. The page links to the
existing H1/H2 numerical detail and the original runoff pages.

Documentary pages increase 6 → 8, or three → four standalone source tables.
Numerical waves/studies remain 83; numerical pages remain 166. H3 has
`analysis_eligible: false`; all results remain typed source literals. Arthaud
and Bouamrane numerical histories, latest indicators, ranges and comparison
eligibility still come exclusively from numerical inputs. Source entries are
counted separately, never as another numerical survey.

The browser validator has a finite 10260 allowance for exact `CNews`, source
ID/hash/locator, all candidate identities/names/order/literals, null publication
date and the three bases. Existing source-specific authenticity rules are
unchanged. Negative tests reject scalar substitution for either bound, score
or identity drift, changed source, invented publication dates, duplicate H3,
unauthorized routes and attempts to admit H3 into numerical analytics.

The existing OG-refresh output allowlist gains only the two new HTML paths.
The existing polling test step gains the H3 regression module; scheduling and
ingestion rules are unchanged. No production workflow is manually invoked.

## Validation and limitations

Initial fetched main: `d3914e54c7a17bba8e6bde1cba6b2dd86a200d9e`.
Final fetched main: `d3914e54c7a17bba8e6bde1cba6b2dd86a200d9e`.
No intervening commits required synchronization.
The main checkout is untouched.

The numerical coverage state remains `unresolved`, method
`reviewed_incomplete_bounded_score_configuration`. All five warnings remain:
10333, 10327, 10319, 10264, 10260. No 10339/10342 registry or historical review
object is changed. The three known 10339 regression errors remain outside scope.
Native bounded-score analytics still require a separate reviewed contract;
publication date and expressed base remain undocumented.


### Test results

The broad publication group passed 340/340 tests. The source/provenance group
ran 192 tests: 189 passed, with the three known 10339 baseline errors. The
publication-manifest group passed 100/100 tests. Total: 632 distinct tests,
629 passed and three pre-existing errors; no new failures, skips or weakened
10339 assertions. An initial focused run passed 36/36; the final focused rerun
after refreshing main passed 43/43.

| Module | Result |
|---|---|
| `test_cnews_10260_source_publication` | 10 passed |
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
| `test_commission_notice_discovery` | 42 passed |
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

Each reports `Reviewed Commission registry addition changed: commission:10339`.
The complete reconciliation module was run; no historical expectation was
repinned or skipped. Notice 10342 is unchanged.

Both JavaScript suites passed: `test_poll_source_projection.js` and
`test_poll_scope.js`. Source authentication, both strict bounds, score and
identity drift, duplicated H3, routes, commissioner case, dates and numerical
admission negatives are covered. H1/H2 coexistence, candidate/institute browsing
and numerical histories/headlines/ranges are checked in the actual frontend code.
Page, hub, route, sitemap, search-entrypoint, study/scope and publication-manifest
check modes all passed. All five coverage warnings remain.

Browser verification covered French and English rendering, language switching,
the original p14 source link, the H1/H2 numerical link, source-section discovery,
OpinionWay browsing and both bounded-result candidates. OpinionWay has nine
numerical waves plus four separately counted source configurations, not a new
numerical study. H3 is labeled explicitly beside the existing two-scenario wave;
Bouamrane retains numerical 1% across H1/H2 alongside the documentary H3 `<1%`.
The global numerical count remains 83, with 349 first-round scenarios and
166 numerical pages. No browser console errors were observed.

The raw preservation audit checked all 1,094 pre-existing tracked files.
The 1,077 outside the 17 intended tracked source/test/artifact changes remained
byte-identical. This includes both numerical corpora, all historical reviews,
all registry decisions, study bindings and identities, all 166 numerical pages,
all six previously published documentary pages and the publication manifest.
The entire numerical explorer projection and all three prior source projections
are also identical to the initial main. All five frozen table records and prior
publication-review objects retain their original authenticated content.

### Exact changed files

- `.github/workflows/refresh-og-cover.yml`
- `.github/workflows/update-polls.yml`
- `assets/polling-lab.js`
- `build_poll_hub_static_links.py`
- `build_poll_pages.py`
- `docs/cnews_10260_source_evidence.md`
- `en/sondages/documents/opinionway-cnews-10260/index.html`
- `en/sondages/index.html`
- `poll_explorer.json`
- `poll_pages_manifest.json`
- `poll_source_tables.json`
- `poll_source_tables.py`
- `route_registry.json`
- `sitemap-polls.xml`
- `sondages/documents/opinionway-cnews-10260/index.html`
- `sondages/index.html`
- `test_bonnal_source_publication.py`
- `test_cnews_10260_source_publication.py`
- `test_poll_explorer.py`
- `test_poll_pages.py`
- `test_poll_source_projection.js`
