# Historical polling scope review — 2026-10-28

The supplied source-reviewed handoff was checked against freshly fetched
`origin/main` at `e5a912ad72d1d814b591caaff27f1d1d9c19e951`. There were no intervening
commits at the first synchronization. The six exclusions are enumerated, with full
observation digests and primary evidence locators, in `poll_election_scope.json`.
The original source URLs remain in `polls.json`; HTTPS evidence links in the sidecar
do not rewrite those URLs.

The handoff shortened the October 2023 Cluster17 ID incorrectly. The actual immutable
ID is `72a2da9cd1969479695b8f09c62f4ea836a77e07a60e07c9fe7dc02eccda5e75`.
It is the unique corpus observation with the specified institute, fieldwork dates
and original source URL. The original [report](https://cluster17.com/wp-content/uploads/2023/10/1er-tour-de-la-presidentielle.pdf)
explicitly describes the same 2022 political offering on PDF page 4 and repeats the
2022 first-round question on page 5. No source observation or ID was repaired.

## Remaining 23 early scenarios

This audit covers every other observation with fieldwork before 2024 at the review
base. The date selects an audit inventory only; it is never an exclusion criterion.
The 23 records remain included and `not_yet_reviewed` in the sidecar projection.
No additional exclusions or affirmative scenario classifications are made in PR 1.

| Institute / fieldwork | Records | Primary source inspection and disposition |
| --- | ---: | --- |
| Ifop, 2023-03-30–31 | 5 | [Commission notice 9686](https://www.commission-des-sondages.fr/notices/files/notices/2023/avril/9686-pres-ifop-7-04-fig-mag-sud-radio.pdf), questionnaire and first-round tables, PDF pages 4–13. Five alternative-offering hypotheses accompany the explicitly retrospective offering on page 8. Their questions use a next-Sunday framing; do not extrapolate the retrospective label to those alternatives. Keep them included and unclassified. |
| Harris Interactive, 2023-04-06–07 | 4 | [Institute report](https://harris-interactive.fr/wp-content/uploads/sites/6/2023/04/Rapport-Harris-IV-Presidentielle-2027-Challenges-avril-2023.pdf), title, methodology on page 3, and first-round summary table on page 8 explicitly concern 2027. The 2022 results on page 6 are contextual recall, not the four tested scenarios. No retrospective exclusion is supported. Keep the four records; defer affirmative scenario entries to a separate finite review. |
| OpinionWay, 2023-04-12–13 | 1 | [Commission notice 9689](https://www.commission-des-sondages.fr/notices/files/notices/2023/avril/9689-pres-ow-le-figaro-magazine.pdf), PDF page 5 question uses next-Sunday framing. References to 2022 on page 3 describe weighting. No explicit 2027 label or repeat-2022 instruction was found in the question. Keep included and unclassified; absence of Macron is not evidence of scope. |
| Harris Interactive, 2023-09-01–04 | 8 | [Institute report](https://harris-interactive.fr/wp-content/uploads/sites/6/2023/09/Rapport-Toluna-Harris-IV-Presidentielle-2027-Challenges-septembre-2023.pdf), title and methodology page 3 explicitly concern 2027; first-round tables follow the context section. April results are historical reminders. No retrospective exclusion is supported. Keep all eight; defer affirmative scenario entries to a separate finite review. |
| Ifop, 2023-10-24–25 | 5 | The original [institute URL](https://www.ifop.com/wp-content/uploads/2023/10/119940-Rapport.pdf) returned no readable report during this audit. Scope cannot be established from the URL, date or candidate lineup. Keep all five included and unclassified pending a retrievable primary question. |

The six source-confirmed retrospective classifications can be implemented without
guessing about these unresolved questions. Inclusion means only that no reviewed
exclusion applies. The default view does not claim that all remaining 343 scenarios
were individually verified as 2027 election questions.

## Preservation and count semantics

All 349 numerical observations and 83 original waves remain in the explorer and
source-page inventory. Every original `#scenario-N` anchor remains in original order.
The default view excludes six scenarios, removing five wholly retrospective waves
and retaining five scenarios of the mixed Ifop wave. It therefore has 343 scenarios
and 78 waves. The three people present only in the retrospective archive are
Emmanuel Macron, Anne Hidalgo and Valérie Pécresse: 47 archival tested people become
44 in default metrics. All 11 institutes remain. The start of the default fieldwork
period becomes 2023-03-30; the archive still starts on 2022-10-25.

`python -B poll_scope.py --check` authenticates reviewed entries against the complete
current corpus and checks the generated browser projection. The read-only PR gate
also runs Python scope tests and actual FR/EN JavaScript regressions. Existing
historical preservation tests and production workflow contracts retain their assertions.
No production workflow is dispatched by this change.
