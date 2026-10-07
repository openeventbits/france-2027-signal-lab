# Reviewed post-audit first-round corrections

This lane is separate from the immutable French cutover registry. The original 75 reviewed mappings, original acceptance figures and audited fixture are unchanged. It corrects Commission notice 10284 and withholds the unrelated notice-10292 source row.

## Sample contract

FR27 has no universal implicit numerical denominator. `sample_scope` specifies the population represented by `sample_size`. Raw French table cells are parsed as `reported`; this records the source value without certifying whether it denotes adults, registered voters, or respondents expressing a preference. Exact factual identity includes both size and scope.

Reviewed first-round migration decisions use an explicitly documented registered-voter base where available. Existing Ifop May 2026 uses 1368 registered voters rather than 1501 adults; Harris July 2026 uses 1592 registered voters rather than 1837 adults. Official Ipsos May 2026 provides 1500 registered voters, separately describing scenario-specific expressed-intention bases. OpinionWay September 2026 likewise distinguishes 1001 adults, 935 registered voters and a certain-voter subset. Legacy `reported` rows are not globally rewritten by this repair.

Primary examples:
- [Ifop May notice 10193](https://www.commission-des-sondages.fr/notices/files/notices/2026/mai/10193-pres-ifop-le-figaro-29-mai.pdf), methodology page 2.
- [Harris July notice 10223](https://www.commission-des-sondages.fr/notices/files/notices/2026/juillet/10223-pres-iv-toluna-harris-interactive-rtl-8-juillet.pdf), methodology page 3.
- [Ipsos May notice](https://www.commission-des-sondages.fr/notices/medias/fichiers/add/2197), methodology and scenario-base discussion.
- [OpinionWay September notice 10260](https://www.commission-des-sondages.fr/notices/files/notices/2026/septembre/10260-pres-iv-opinionway-cnews-11-septembre.pdf), methodology page 3.

For [notice 10284](https://www.commission-des-sondages.fr/notices/files/notices/2026/septembre/10284-pres-barometre-election-presidentielle-v6-ifop-le-figaro-30-septembre.pdf), page 2 reports 1527 adults including 1393 registered voters. Every presidential scenario on pages 9–18 labels its base as the full registered-voter population and publishes percentages of expressed votes. Footnotes separately count respondents expressing an intention, including a certain-voter subset. Following the existing reviewed first-round convention, the canonical metadata is **1393 / registered_voters**, not 1527 / reported and not a conflation with the scenario-specific expressed-intention counts below.

| Locator | Notice page | Adults | Registered voters (canonical sample) | Expressed intentions | Certain voters expressing intentions | Classification |
|---|---:|---:|---:|---:|---:|---|
| FR-T0R1 | 9 | 1527 | 1393 | 1027 | 837 | A: sample metadata only |
| FR-T0R2 | 10 | 1527 | 1393 | 1003 | 817 | A: sample metadata only |
| FR-T0R3 | 11 | 1527 | 1393 | 970 | 792 | A: sample metadata only |
| FR-T0R4 | 13 | 1527 | 1393 | 964 | 785 | A: sample metadata only |
| FR-T0R5 | 12 | 1527 | 1393 | 928 | 763 | A: sample metadata only |
| FR-T0R6 | 14 | 1527 | 1393 | 974 | 796 | A: sample metadata only |
| FR-T0R7 | 15 | 1527 | 1393 | 971 | 795 | A: sample metadata only |
| FR-T0R8 | 16 | 1527 | 1393 | 969 | 799 | A: sample metadata only |
| FR-T0R9 | 17 | 1527 | 1393 | 980 | 809 | A: sample metadata only |
| FR-T0R10 | 18 | 1527 | 1393 | 1015 | 827 | B: factual scenario correction |

All ten share Ifop/Ifop-Fiducial fieldwork September 25–29, 2026, for LCI, Le Figaro and Sud Radio. Prior production metadata is 1597 / reported; the reviewed live Wikipedia metadata is 1527 / reported. For rows 1–9 the old/live/official candidate sets and every score match. For row 10 old/live omit François Ruffin 3%; all thirteen other values match the official fourteen-candidate table.

## Individually verified identities and complete canonical lineups

### FR-T0R1

Previous ID: `3faf55681bc28ffd2da5210c65a232b263e8825879539f9fa3a93e22669bfc44`.
Canonical ID: `3faf55681bc28ffd2da5210c65a232b263e8825879539f9fa3a93e22669bfc44`.
Action: `correct_retained_sample`.
Official candidates and scores: Nathalie Arthaud 0.5%; Jean-Luc Mélenchon 15%; Fabien Roussel 2.5%; Marine Tondelier 3%; Raphaël Glucksmann 11%; Gabriel Attal 8%; Édouard Philippe 16%; Bruno Retailleau 7%; Nicolas Dupont-Aignan 1%; Marine Le Pen 32%; Éric Zemmour 4%.
Old/live candidate difference: none; every candidate and score is identical.

### FR-T0R2

Previous ID: `5810eda3138de004f8f5775c96b3f7b3620abbe6086e00af87829267c1398409`.
Canonical ID: `5810eda3138de004f8f5775c96b3f7b3620abbe6086e00af87829267c1398409`.
Action: `correct_retained_sample`.
Official candidates and scores: Nathalie Arthaud 0.5%; Jean-Luc Mélenchon 16%; Fabien Roussel 2.5%; Marine Tondelier 3%; Raphaël Glucksmann 11%; Édouard Philippe 21%; Bruno Retailleau 8%; Nicolas Dupont-Aignan 1.5%; Marine Le Pen 33%; Éric Zemmour 3.5%.
Old/live candidate difference: none; every candidate and score is identical.

### FR-T0R3

Previous ID: `cca95266da8cc497acc3ea505c8a5397880c626b0e7d264fed3f4ffc7c69a190`.
Canonical ID: `cca95266da8cc497acc3ea505c8a5397880c626b0e7d264fed3f4ffc7c69a190`.
Action: `correct_retained_sample`.
Official candidates and scores: Nathalie Arthaud 1%; Jean-Luc Mélenchon 15%; Fabien Roussel 2.5%; Marine Tondelier 4%; Raphaël Glucksmann 13%; Gabriel Attal 15%; Bruno Retailleau 10%; Nicolas Dupont-Aignan 2%; Marine Le Pen 34%; Éric Zemmour 3.5%.
Old/live candidate difference: none; every candidate and score is identical.

### FR-T0R4

Previous ID: `e938c80b676988665c0bedc3f87f835f5f12c875306931e833290167068233e7`.
Canonical ID: `e938c80b676988665c0bedc3f87f835f5f12c875306931e833290167068233e7`.
Action: `correct_retained_sample`.
Official candidates and scores: Nathalie Arthaud 1%; Jean-Luc Mélenchon 17%; Fabien Roussel 3%; Marine Tondelier 5.5%; Olivier Faure 4%; Gabriel Attal 17%; Bruno Retailleau 11%; Nicolas Dupont-Aignan 1%; Marine Le Pen 36%; Éric Zemmour 4.5%.
Old/live candidate difference: none; every candidate and score is identical.

### FR-T0R5

Previous ID: `dc7deea05ea268e319016dcbae38cd6a362d4b8f3428b11a9982d89cc02491e5`.
Canonical ID: `dc7deea05ea268e319016dcbae38cd6a362d4b8f3428b11a9982d89cc02491e5`.
Action: `correct_retained_sample`.
Official candidates and scores: Nathalie Arthaud 1%; Jean-Luc Mélenchon 16%; Fabien Roussel 3.5%; Marine Tondelier 5%; Olivier Faure 3%; Édouard Philippe 23%; Bruno Retailleau 8%; Nicolas Dupont-Aignan 1.5%; Marine Le Pen 35%; Éric Zemmour 4%.
Old/live candidate difference: none; every candidate and score is identical.

### FR-T0R6

Previous ID: `12a0639abdc7d065ae67b0a4613c2b56a3cf8f854bad12c628e46bf982e1b5eb`.
Canonical ID: `12a0639abdc7d065ae67b0a4613c2b56a3cf8f854bad12c628e46bf982e1b5eb`.
Action: `correct_retained_sample`.
Official candidates and scores: Nathalie Arthaud 0.5%; Jean-Luc Mélenchon 15%; Fabien Roussel 3%; Marine Tondelier 6%; Ségolène Royal 3%; Édouard Philippe 24%; Bruno Retailleau 8%; Nicolas Dupont-Aignan 1.5%; Marine Le Pen 35%; Éric Zemmour 4%.
Old/live candidate difference: none; every candidate and score is identical.

### FR-T0R7

Previous ID: `d6a2cb3620d25f29157b0654965fcfb52d1a21ab3f18b519661468502bd05f54`.
Canonical ID: `d6a2cb3620d25f29157b0654965fcfb52d1a21ab3f18b519661468502bd05f54`.
Action: `correct_retained_sample`.
Official candidates and scores: Nathalie Arthaud 1%; Jean-Luc Mélenchon 17%; Fabien Roussel 3.5%; Marine Tondelier 5.5%; Jérôme Guedj 3%; Édouard Philippe 23%; Bruno Retailleau 8%; Nicolas Dupont-Aignan 1%; Marine Le Pen 35%; Éric Zemmour 3%.
Old/live candidate difference: none; every candidate and score is identical.

### FR-T0R8

Previous ID: `40f28f59058261a5f0f984caf39f816c612a06b0e11d36b6daabdb1737c4914e`.
Canonical ID: `40f28f59058261a5f0f984caf39f816c612a06b0e11d36b6daabdb1737c4914e`.
Action: `correct_retained_sample`.
Official candidates and scores: Nathalie Arthaud 1%; Jean-Luc Mélenchon 17%; Fabien Roussel 3.5%; Marine Tondelier 6%; Emmanuel Maurel 1%; Édouard Philippe 23%; Bruno Retailleau 9%; Nicolas Dupont-Aignan 1.5%; Marine Le Pen 35%; Éric Zemmour 3%.
Old/live candidate difference: none; every candidate and score is identical.

### FR-T0R9

Previous ID: `6f6756d00e9d2a390e9e55c7883ee66bc383d47f257f49fa00e49d1e48367ec9`.
Canonical ID: `6f6756d00e9d2a390e9e55c7883ee66bc383d47f257f49fa00e49d1e48367ec9`.
Action: `correct_retained_sample`.
Official candidates and scores: Nathalie Arthaud 0.5%; Jean-Luc Mélenchon 16%; Fabien Roussel 2.5%; Marine Tondelier 5%; François Hollande 8%; Édouard Philippe 22%; Bruno Retailleau 7%; Nicolas Dupont-Aignan 1%; Marine Le Pen 34%; Éric Zemmour 4%.
Old/live candidate difference: none; every candidate and score is identical.

### FR-T0R10

Previous ID: `c439985b6ac05c603c6ac693aaaf4b7cbb82d7e6846717c1c0ef07af8722a882`.
Canonical ID: `7ae37b33f52f31df34aa2b1fd0e5a326fff1c7e6b8683255b30472d9fb44309a`.
Action: `supersede_event`.
Official candidates and scores: Nathalie Arthaud 0.5%; Jean-Luc Mélenchon 14%; Fabien Roussel 2%; François Ruffin 3%; Marine Tondelier 3%; Raphaël Glucksmann 9%; Gabriel Attal 7%; Édouard Philippe 15%; Dominique de Villepin 2%; David Lisnard 3.5%; Bruno Retailleau 5%; Nicolas Dupont-Aignan 1%; Marine Le Pen 31%; Éric Zemmour 4%.
Old/live candidate difference: both omit François Ruffin 3%; all other scores are identical.

## Storage and execution contract

`fr27_post_audit_first_round_corrections.json` schema 1.0 contains finite reviewed corrections and finite excluded source representations. Each correction records old/incoming/canonical factual keys, explicit historical and incoming revisions, exact locator and URL, ordered canonical candidates, old/new deterministic hypotheses and IDs, a permitted treatment, official page, evidence URLs and a specific review reason. Validation rejects unexpected fields, duplicate locators or incoming keys, ambiguous targets, identity chains, malformed URLs, unsupported actions, or inconsistent candidate/hypothesis/ID representations.

Parsing is followed by exact correction validation before ordinary reconciliation. Reviewed page revision IDs remain recorded as provenance. At or after the earliest reviewed incoming revision, locator, URL and every factual-key field must match the reviewed incoming representation exactly; unrelated page edits do not invalidate it. The explicitly recorded historical revision remains the only replay of the old representation. A registered correction wave must be complete, with no unknown rows. Weak review anchors never authorize corrections or merging. Withheld-row anchors can only reject changed excluded evidence. Target sample/scope, candidate membership or score, dates, pollster, URL or locator mutations still fail closed. Unreviewed pre-review representations and unknown correction-wave rows also fail closed.

An existing event must have either the exact reviewed old facts or the exact already-applied canonical facts; any other prior mutation fails. Metadata corrections retain their hypothesis/source event ID because sample fields are not ID inputs. Adding Ruffin changes the hypothesis/candidate lineup and therefore supersedes the old ID. The successor carries `supersedes_event_id`; the registry preserves both exact identities and factual representations. Both IDs coexisting is rejected.

Historical revision 240063728 is explicitly replayable. The old source representation reconstructs the same canonical result and cannot restore 1597 or remove Ruffin. The initial repair fixture records revision 240128358 at 2026-10-06T12:55:03Z. Revision 240128246 identifies the edit introducing sample drift. During validation, revision 240131611 (parent 240128358, timestamp 2026-10-06T14:47:16Z) added only the year 2026 to the YouGov September 17–21 date cell. Its raw wikitext diff and complete normalized poll records were compared independently; all poll facts, locators and source URLs are identical. Both 240128358 and 240131611 remain recorded as reviewed provenance. Revision 240133071 (2026-10-06T15:38:39Z) adds the year 2026 to five other YouGov runoff date cells; all normalized poll records are unchanged. Later page revisions may reuse only exact reviewed target facts, locator and URL. Revision 240133071 is not added to an allowlist or as another large fixture.

Fixture SHA-256: `43c06ccfe504ca322a8ffb8dee3187efd0eb4debe8598afe727fa2844554ee5f`.
Subsequent revision fixture SHA-256: `6a149affbd3acfedbf22dd7aeabe0360a87df05da758045337859d49354663eb`.
Official notice SHA-256: `ed665185fb1bae1a07d477439844c359eb9e4c158ccc7f7e6fa8a7783ed82dd9`.
The ten prior events are frozen separately for regression input; no tracked production outputs are changed.

## Unrelated evidence

FR-T0R28, Ifop September 9–11, 2026, n=1548, source notice 10292, is exactly withheld. Its companion new row remains parser-rejected. Neither is accepted as a new event in this repair. A changed withheld locator, source URL or factual representation fails closed; later unrelated page revisions keep the exact row withheld.

## Architecture review

1. Historical 75-mapping audit unchanged: **yes**.
2. Future random review-anchor collision can pass: **no**.
3. Unreviewed sample correction can pass: **no**.
4. Unreviewed candidate-set correction can pass: **no**.
5. Primary evidence is encoded: **yes**, with notice URL, page and independently extracted scenario fixture.
6. Every correction is exact and deterministic: **yes**, including canonical factual-key and event-ID verification.
7. Second-round behavior is modified: **no**; no second-round contract or registry changes.
8. Unrelated new row is accepted: **no**; exact withholding decision.
9. Another explicit post-audit review can use this lane without relaxed matching: **yes**, through a new strictly validated record with primary evidence.

Production publishes corrected data through the normal Update polls workflow after merge. Do not manually promote temporary outputs.

## Live production verification and semantic output comparison

The exact scheduled fetch command, using both tracked previous corpora, wave overrides and Commission registry and writing all four outputs to temporary paths, exited 0 at revision **240131611**. The workflow's complete `Validate and stage fetched data` Python block also exited 0 against isolated temporary copies of the tracked inputs: 298 first-round events (285 complete, 13 partial), 81 second-round events, closest-runoff status `agree`, latest first-round fieldwork September 29. The live source has 13 reviewed runoff table families, 14 parser fail-closed rows and 3 ambiguous identity rows. The post-audit lane separately withholds one exact notice-10292 row. All ten notice-10284 scenarios are corrected; none is unresolved. Commission coverage is 30 relevant notices: 3 parsed, 18 reconciled, 9 unresolved. Existing unresolved notices are not accepted through this correction lane.

The first-round semantic diff is exact: nine retained IDs change only `sample_size` 1597 → 1393 and `sample_scope` reported → registered_voters. FR-T0R10 replaces its old ID with the documented successor, adds Ruffin 3%, changes the corresponding hypothesis and scenario key, records `supersedes_event_id`, and recomputes completeness from partial/97%/3% unreported to complete/100%/no unreported share. All thirteen previously reported scores remain unchanged. No other retained event changes, no duplicate is created, and no genuinely new poll event is introduced. Counts remain 298/81. The fetch's existing “Net new official events: 22” merge diagnostic counts official parser inputs; the final corpus diff and reconciliation report introduce zero new poll scenarios.

All 81 second-round event objects are identical. `second_round_polls.json` and `closest_tested_runoff.json` differ only in `generated_at` and source revision metadata; the workflow's `semantic_runoff_payload` comparisons are equal for both.

Commission registry differences are ordinary live discovery, separate from the correction implementation: 127 → 129 notices, adding 10291 (Avenir jeunesse, excluded for lack of voting-intention language) and 10292 (vote blanc, excluded for lack of 2027 context). No notice is removed. Existing notice 10284 has an updated listing title and listing/resolved alias `/add/2303` → `/add/2308`; its direct PDF correction evidence remains the pinned URL/hash above. No other existing notice record changes. These outputs remain temporary; the four tracked production JSON files are unchanged.

## Recent-edit assessment

`git diff 019fe3f1ac391d151d8ff3562ef53eefced2ed25 4d06526b479299d51b84c2af086a075aa0008bec -- fetch_polls.py poll_migration.py fr27_poll_migration_registry.json poll_wave_overrides.json .github/workflows/update-polls.yml poll_contract.py` is empty. Path-filtered history is also empty. The intervening X/social scheduler edits after the failing f77fa6da checkout affect only the X workflow, social modules/documentation and scheduler/social tests. They did not cause this poll migration failure; the exact external sample edit in revision 240128246 explains the new collision.

## Initial validation commands (before revision-provenance refinement)

Before mutation, the unchanged production contract passed 186 tests and the exact live production fetch reproduced `unregistered French row shares a review anchor; explicit mapping required`.

Final focused and complete polling suites:

```text
python -B -m unittest -v test_post_audit_first_round_corrections.py
# 27 tests, OK (13.780 s)
python -B -m unittest -v test_poll_migration.py test_fetch_polls.py test_poll_second_round_evidence_drift.py test_post_audit_first_round_corrections.py
# 169 tests, OK (174.752 s)
```

Exact updated production-contract command extracted from `.github/workflows/update-polls.yml`:

```text
python -B -m unittest -v test_commission_notice_discovery.py test_commission_notice_coverage.CommissionNoticeCoverageTests test_fetch_polls.CandidateNameEvidenceTests test_fetch_polls.PollEventContractTests test_fetch_polls.SemanticRunoffPayloadTests test_fetch_polls.SemanticFirstRoundDiscoveryTests test_fetch_polls.WikipediaSourceSelectionTests.test_default_source_remains_english_and_scheduled_source_is_french test_fetch_polls.WikipediaSourceSelectionTests.test_english_source_accepts_prepared_previous_second_round_argument test_fetch_polls.WikipediaSourceSelectionTests.test_french_phase4a_mode_refuses_tracked_output_destinations test_fetch_polls.WikipediaSourceSelectionTests.test_french_source_requires_both_previous_corpora test_fetch_polls.WikipediaSourceSelectionTests.test_workflow_official_wave_validation_excludes_fr_t1r45_only_from_evidence test_poll_migration.FrozenFixtureTests test_poll_migration.FactualIdentityTests test_poll_migration.RegistryValidationTests test_poll_migration.ReviewedDecisionTests test_poll_migration.CutoverRehearsalTests.test_cutover_keeps_the_scheduled_source_and_integration_boundary_explicit test_poll_second_round_evidence_drift.py test_post_audit_first_round_corrections.py test_frontend_facts.py test_publication_manifest.PublicationManifestTests.test_poll_coverage_warns_only_for_unresolved_relevant_notices
# 213 tests, OK (176.520 s)
```

The regressions reject sample near-matches 1526/1528, mutated scores or candidate membership, wrong revisions/locators/URLs, unknown same-anchor rows, duplicated identities, changed withheld evidence and malformed registry fields. Canonical Ruffin omission fails. Historical replay, repeated reconciliation and full fetch integration preserve the exact canonical events without duplicates. Existing Philippe–Mélenchon heading-order, colspan/source-drift and second-round evidence regressions pass.

The live CLI was the workflow's exact `python fetch_polls.py --wikipedia-source french --previous-first-round polls.json --previous-second-round second_round_polls.json --poll-wave-overrides poll_wave_overrides.json --output <TEMP>/polls.json --second-round-output <TEMP>/second_round_polls.json --closest-runoff-output <TEMP>/closest_tested_runoff.json --commission-registry commission_notice_registry.json --commission-registry-output <TEMP>/commission_notice_registry.json` command. It exited 0. The complete workflow validation/staging Python block was extracted verbatim, with only `/tmp/` relocated to the Windows temporary directory and imports pointed to this checkout, and ran against isolated copies rather than tracked publication outputs. It exited 0. `git diff --check` passes.
