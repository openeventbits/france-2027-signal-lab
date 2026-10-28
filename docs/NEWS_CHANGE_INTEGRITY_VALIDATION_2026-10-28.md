# FR27 News Change Integrity — validation, 28 October 2026

Base: `e8edae81b1090a38f4c75b9992d94899ff1b9146` (fresh isolated worktree).
The first fetch matched the handoff's reviewed base exactly, with no intervening commits.
The final pre-commit/pre-push fetch still matched this exact SHA; no rebase or input rebuild was needed.

## Evidence and root causes

- `campaign-c491c4023d07b5c39aee`: [TF1's original article](https://www.tf1info.fr/politique/elections/presidentielle/presidentielles-2017-nicolas-dupont-aignan-devoile-son-programme-2024438.html) reports the 2017 presidential campaign. Live publisher JSON-LD identifies original publication as `2017-02-01T21:06:16.029+01:00`. The handoff/search-cached publisher extract reports an update on 24 September 2026; live JSON-LD currently repeats the original date for `dateModified`. An [exact-headline Google News RSS query](https://news.google.com/rss/search?q=%22Pr%C3%A9sidentielles+2017%22+%22Nicolas+Dupont-Aignan+d%C3%A9voile+son+programme%22&hl=fr&gl=FR&ceid=FR%3Afr) returned the identical stored article URL/GUID with `pubDate` of `Sat, 24 Oct 2026 06:00:57 GMT`. `parse_feed` selects that field, explaining the ledger's exact timestamp. Why Google chose that date remains unknown; it is not established as a consequence of the publisher update. The old ledger classified `dévoile son programme` plus presidential context without checking the explicit historical race label.
- `campaign-27cf429402355764ab69`: [Le Média's publisher page](https://www.lemediatv.fr/emissions/2026/palestine-fascisme-soutien-a-lfi-habibitch-une-artiste-qui-refuse-de-se-taire-6CTF8SDOT6aJ5YUxnz26IQ) describes a long-form artist interview and political engagement. The shared ingestion classifier recognizes the topical noun phrase `soutien à LFI`; the old ledger promoted every matched support term without requiring a material electoral action. No new presidential endorsement, selection or campaign-status action is established by the headline.

The fix stays at ledger promotion. A leading prior presidential-election heading blocks historical campaign reports; a year elsewhere does not. Current legal/procedural outcomes remain eligible. Party-only support needs an action and headline electoral meaning, formal announcement, rallying or voting call. A topical support noun cannot be rescued by RSS summaries or upstream election flags. Candidate-bound endorsements and support committees retain their existing behavior. No name-specific exclusion, finite source exception, date rewrite or shared ingestion-policy change is introduced.

## Exact fixed-clock effects

Clock: `2026-10-28T16:23:06.102187Z`; Paris window: 15–28 October 2026.
The baseline builder loaded from the base Git blob reproduces the committed ledger exactly before modification.

| Ledger category | Before | After |
| --- | ---: | ---: |
| Total | 53 | 51 |
| Campaign | 41 | 39 |
| Legal | 2 | 2 |
| Polling | 10 | 10 |
| Fact-check | 0 | 0 |
| Runoff | 0 | 0 |

Exactly the two IDs above are removed. No IDs are added. All 51 retained item objects are equal in full, including stable IDs, trusted/publication/event/detection/generation dates, candidate associations, primary sources and supporting sources. All other ledger metadata stays equal except counts and omission diagnostics. Campaign-launch aggregation is untouched.

Three CLI builds with identical inputs/clock—two using the original prior ledger and one replay using corrected prior state—produce identical bytes (SHA-256 `805d710dea4d35e204521544820284b149f2fcb44104be7e1ddda40560c1a171`). Both omissions persist on replay. The existing news workflow runs the same builder and now runs the new regression module.

## Preservation and dependencies

- `news_wire.json`: unchanged, 2,029 election-news items, 46 notable developments, 2,498 relevant-news items and 3,664 candidate-watch items; 18 source routes. The TF1 source row remains in notable developments and candidate watch; the Le Média row remains in notable developments.
- `news_inventory.json`: all 23,220 records retained. `news_corpus_ledger.json`: 7,062 accepted election-news IDs, 11,593 candidate-watch IDs and 133 accepted publishers unchanged.
- Git-blob equality verifies source news/inventory/corpus ledger, source registry, publisher policy, candidate signals, candidate visibility/agenda histories, campaign events and source health. All other upstream files are outside the exact changed-file allowlist. Coverage, media attention and agenda evidence remain unchanged.
- Rebuilding all candidate dossiers changes only Nicolas Dupont-Aignan's data and FR/EN HTML: his ledger projection falls from two items to one, retaining the valid legal development. His news/coverage/agenda evidence and all other JSON fields remain equal. All other candidate dossiers/hubs remain current and unchanged.
- FR/EN root entrypoints rebuilt with the existing search builder: only the static What Changed total changes from 53 to 51 in each language.
- Publication manifest rebuilt last at its existing `published_at` (`2026-10-28T17:18:34Z`): only the recent-changes lane hash and derived snapshot ID change. Other lanes remain equal. The existing five unresolved polling-notice warnings remain unchanged.

## Changed files

- `generate_recent_changes.py`: historical heading and party-support promotion boundaries.
- `test_news_change_integrity.py`: frozen incident rows; hostile flags/summaries; historical-heading variants; fresh 2027 references to 2017; party/candidate endorsement, legal/procedural positives; full-object preservation and deterministic replay.
- `.github/workflows/validate-dashboard.yml`, `.github/workflows/update-news-wire.yml`: run the added regression module alongside existing checks.
- `docs/METHODOLOGY.md`: explain the promotion boundary.
- `recent_changes.json`: exactly two removals and derived counts/diagnostics.
- `candidates/nicolas-dupont-aignan/data.json`, `candidates/nicolas-dupont-aignan/index.html`, `en/candidates/nicolas-dupont-aignan/index.html`: remove only the false ledger projection.
- `index.html`, `en/index.html`: static ledger total 53 → 51.
- `publication_manifest.json`: recent-changes hash and snapshot ID.
- This validation report.

## Validation

- Final complete union: **1,149 tests passed in 368.491 seconds**, across all 45 Python modules selected by the news and dashboard workflow test blocks, plus candidate-reference, What Changed localization and dashboard navigation. Existing shared support-classifier, publication, candidate-signals and writer-safety contracts remain enabled.
- Direct classifier checks: 51 tests passed, including all ten added regression methods. The baseline generator reproduced both incidents; the corrected builder removes both.
- The first full union exposed four stale-entrypoint checks (two assertion failures, two check-mode errors) because the static FR/EN total still read 53. The existing builder regenerated only those two labels; all 46 entrypoint/localization/navigation tests then passed, followed by the entire successful 1,149-test rerun. No assertion or frozen fixture was weakened.
- `python -B poll_scope.py --check`, `node test_poll_scope.js` and `node test_poll_source_projection.js` passed, preserving the existing PR gate.
- `python -B build_search_entrypoints.py --check`, `python -B build_candidate_reference.py --all-active --check`, and `python -B build_publication_manifest.py --check --published-at 2026-10-28T17:18:34Z` passed.
- Three CLI ledger regenerations were byte-identical; a further in-memory corrected-prior replay remained equal. Git-blob and full-object preservation comparisons passed. Staged-file scope and `git diff --check` passed.
- Final `origin/main` synchronization: `e8edae81b1090a38f4c75b9992d94899ff1b9146`, unchanged from the initial fetch.

No merge, deployment or manual production workflow has been run. GitHub's automatic PR validation is checked separately after the PR is opened.
