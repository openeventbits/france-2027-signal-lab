# FR27 PR 1 — Historical Polling Scope: implementation and validation

## Synchronization

Fresh managed worktree and branch `codex/fr27-pr1-historical-polling-scope`.
The first fetch matched handoff base `e5a912ad72d1d814b591caaff27f1d1d9c19e951`.
The later candidate-family refresh was inspected and rebased normally; generated
route and publication conflicts were resolved from latest main and rebuilt from
its newer inputs. The final inspected base is `33a8c082379f59f9c7e5ff84d1eacd7f578e1b08`.
No force push, merge, deployment or manual production workflow dispatch.

## Exact corpus effects

| Quantity | Full archival corpus | Default 2027 view |
| --- | ---: | ---: |
| First-round scenarios | 349 | 343 |
| Numerical waves | 83 | 78 |
| Tested people | 47 | 44 |
| Institutes | 11 | 11 |
| First fieldwork | 2022-10-25 | 2023-03-30 |
| Latest fieldwork | 2026-10-22 | 2026-10-22 |

Six source-confirmed retrospective scenarios occur in six waves. Five waves are
wholly retrospective; the March 2023 Ifop wave retains all six scenarios on its
source page and five in default calculations. Its retrospective `#scenario-4`
anchor is unchanged. All 349 first-round records and 108 second-round records
remain byte-for-byte unchanged relative to the synchronized base.

The original 166 numerical source pages, four documentary pages, two compatibility
pages, 83 wave identities and every scenario anchor remain. The canonical route
registry still contains 334 routes. The archival application HUD still counts
83 numerical waves; scoped Polling Lab metrics use 78.

Candidate Signals retains its entire canonical universe and all non-history fields.
Seventeen candidate histories change; aggregate candidate/package observations
fall from 954 to 902 (52 removed). Ten histories lose observations; seven retain
their count while the mixed wave's selected score or evidence metadata changes.
All 11 changed dossier JSON files differ only within `polling.first_round_history`.

| Candidate | Previous observations | Default observations |
| --- | ---: | ---: |
| Bruno Le Maire | 7 | 7 |
| Fabien Roussel | 73 | 68 |
| François Bayrou | 2 | 2 |
| Gérald Darmanin | 7 | 7 |
| Jean Lassalle | 12 | 7 |
| Jean-Luc Mélenchon | 75 | 70 |
| Laurent Wauquiez | 17 | 17 |
| Marine Le Pen | 71 | 66 |
| Marine Tondelier | 61 | 61 |
| Nathalie Arthaud | 73 | 68 |
| Nicolas Dupont-Aignan | 69 | 64 |
| Olivier Faure | 20 | 20 |
| Philippe Poutou | 21 | 16 |
| Valérie Pécresse | 6 | 0 |
| Yannick Jadot | 8 | 2 |
| Édouard Philippe | 67 | 67 |
| Éric Zemmour | 72 | 67 |

## Source boundaries and preservation

The sidecar authenticates six complete observations by immutable ID and full-object
SHA-256, with bilingual evidence references, review date and finite scope status.
Production entrypoints reject missing, duplicated or changed reviewed observations
before writing. Reusable projections continue to support finite source-review test
subsets. Unknown observations stay `not_yet_reviewed` and included by default.

The other 23 early scenarios were audited and retained without additional scope
assignments. One Ifop report was not readable during the audit; next-Sunday wording
in other sources does not establish election year. No date, Macron, lineup, URL
or scenario-key heuristic controls exclusion. See
[POLLING_SCOPE_REVIEW_2026-10-28.md](POLLING_SCOPE_REVIEW_2026-10-28.md), including
the handoff's corrected October 2023 Cluster17 ID.

Raw polling, runoff, Commission registry, source tables, page inventory, Recent
Changes and latest-main public-signal provider inputs are unchanged. Existing
historical preservation tests and unrelated contract assertions were not changed.
The source-projection JavaScript test only loads the newly required runtime.

## Validation results

- The complete polling-production selection, dashboard gate and affected suites
  were combined without duplicate test IDs: **1,754 distinct tests**, using the
  existing authenticated historical runner. It reported 1,753 passes and one
  existing Race at a Glance package-order assertion failure, with no skips.
- The ranking boundary was repaired in implementation code; the assertion was
  retained. The **final affected rerun passed all 500 tests**, with no failures,
  errors or skips. It includes every affected comparison/ranking, scope, explorer,
  Candidate Signals, candidate-link, Recent Changes, navigation, route, search and
  publication-manifest test. There are no unresolved test failures.
- All three authenticated frozen-history preservation tests passed in the complete
  run. No frozen fixture or preservation assertion was changed.
- `node test_poll_scope.js`: PASS for both languages, six exclusions, negative
  controls, full-package preservation, 78-wave ranking, mixed-wave ranges and anchors.
- `node test_poll_source_projection.js`: PASS, including typed source-result isolation.
- `python -B poll_scope.py --check`: PASS.
- Poll pages, static hub links, all active candidate dossiers, route registry,
  semantic search, sitemaps and publication manifest: deterministic `--check` PASS.
- Two deterministic archived-source ingestion replays preserve every raw first-round
  object and reapply only the six sidecar classifications. Repeated builds are stable.
- `git diff --check`: PASS. Raw-corpus/provider-input preservation and non-history
  Candidate Signals/dossier field comparisons: PASS.


Browser verification covered both dashboards, both Polling Lab hubs, scoped counts,
the five-scenario mixed-wave selector, and both original retrospective source-page
anchor routes. Temporary preview tabs and the localhost server were closed.

The manifest retains five pre-existing unresolved Commission coverage warnings
(10333, 10327, 10319, 10264, 10260); this PR does not alter those unrelated records.

## Exact changed files

63 files relative to the synchronized base, including this report:

```text
.github/workflows/validate-dashboard.yml
assets/poll-scope.js
assets/polling-lab.js
build_candidate_signals.py
build_poll_explorer.py
build_poll_hub_static_links.py
build_poll_pages.py
candidate_signals.json
candidates/bruno-le-maire/data.json
candidates/edouard-philippe/data.json
candidates/eric-zemmour/data.json
candidates/eric-zemmour/index.html
candidates/fabien-roussel/data.json
candidates/fabien-roussel/index.html
candidates/jean-lassalle/data.json
candidates/jean-lassalle/index.html
candidates/jean-luc-melenchon/data.json
candidates/jean-luc-melenchon/index.html
candidates/marine-le-pen/data.json
candidates/marine-le-pen/index.html
candidates/marine-tondelier/data.json
candidates/nathalie-arthaud/data.json
candidates/nathalie-arthaud/index.html
candidates/nicolas-dupont-aignan/data.json
candidates/nicolas-dupont-aignan/index.html
candidates/olivier-faure/data.json
docs/METHODOLOGY.md
docs/POLLING_SCOPE_REVIEW_2026-10-28.md
docs/PR1_POLLING_SCOPE_VALIDATION_2026-10-28.md
en/candidates/eric-zemmour/index.html
en/candidates/fabien-roussel/index.html
en/candidates/jean-lassalle/index.html
en/candidates/jean-luc-melenchon/index.html
en/candidates/marine-le-pen/index.html
en/candidates/nathalie-arthaud/index.html
en/candidates/nicolas-dupont-aignan/index.html
en/index.html
en/sondages/2022-10-26-ifop-197782194f3a692c/index.html
en/sondages/2022-11-06-cluster17-f9d165450d63795a/index.html
en/sondages/2023-03-31-ifop-23ec5fda2b758947/index.html
en/sondages/2023-04-05-elabe-c5cda1822452a37f/index.html
en/sondages/2023-04-06-odoxa-19bffae821723630/index.html
en/sondages/2023-10-20-cluster17-30bb60d3928744ea/index.html
en/sondages/index.html
index.html
poll_election_scope.json
poll_explorer.json
poll_scope.py
poll_scope_runtime.js
publication_manifest.json
route_registry.json
sitemap-polls.xml
sitemap.xml
sondages/2022-10-26-ifop-197782194f3a692c/index.html
sondages/2022-11-06-cluster17-f9d165450d63795a/index.html
sondages/2023-03-31-ifop-23ec5fda2b758947/index.html
sondages/2023-04-05-elabe-c5cda1822452a37f/index.html
sondages/2023-04-06-odoxa-19bffae821723630/index.html
sondages/2023-10-20-cluster17-30bb60d3928744ea/index.html
sondages/index.html
test_poll_scope.js
test_poll_scope.py
test_poll_source_projection.js
```
