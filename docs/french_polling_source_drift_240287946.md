# French polling presentation drift: revision 240287946

This report supersedes the earlier, incorrect source-omission conclusion. Villepin's values are explicitly present in `Autres`; their absence from parsed output was a parser defect, not deletion of source evidence.

## Scope and immutable inputs

Worktree: `C:\Users\Tanya\Documents\GitHub\france-2027-signal-lab-polls-source-drift`.
Branch: `codex/polls-french-source-drift-v1`. HEAD: `10ce165e1fcf483192f9e7dba1918366f58125fd`.
Reviewed frozen French revision: **240287946**, timestamp **2026-10-11T22:03:08Z**.
Fixture SHA-256: `957320e5b203d5f25e96a9be8b0918a8da17dd965057d9f8f15f111846b126e6`.

No tracked production corpus or discovery output is changed. No staging, commit, push, reset, clean, stash or rebase is performed. The primary checkout, notebooks, workflow orchestration and shrink guard are untouched.

## Structural ownership and root cause

The original `_preceding_heading()` searched only h2–h4. Both tables therefore inherited `Second semestre 2026`, triggering the existing one-table-per-context guard.

Both tables have this immediate logical heading ancestry:

- h2 `Sondages concernant le premier tour` → h3 `Année 2026` → h4 `Second semestre 2026` → h5 `Octobre-décembre 2026`: one table, four physical rows, **zero publishable poll observations**.
- h2 `Sondages concernant le premier tour` → h3 `Année 2026` → h4 `Second semestre 2026` → h5 `Juillet-septembre 2026`: one table, **86 observations and six rejected rows**.

The October table fails to provide ordinary poll metadata on its blank/status rows; the ordinary sample/date/source checks yield no observations. No sentence or person is hard-coded as a status exclusion.

The repaired nearest-heading search includes h5 and h6. Only recognized quarter periods under matching h4 semester and h3 year ancestry are accepted; an unrecognized h6 cannot be skipped to broaden ownership. Mixed parent/child ownership, duplicate tables in one leaf, nested tables, malformed ancestry and unrelated tables remain fail-closed. The existing narrowly reviewed `Autres` companion exclusion remains unchanged.

## Structured Autres contract

The original pandas representation kept only the first link, and numeric-prefix parsing kept only its score. The repair uses physical DOM cells aligned through the existing rowspan/colspan expansion. Each hr-delimited entry must consume the entire remaining text as one explicit score followed by one reviewed candidate name, with at most one candidate link agreeing with that name. Inline wrappers and reference markers do not create evidence.

Candidate identity still uses the finite reviewed normalization set. Entries preserve document order; factual keys remain order-independent. Missing scores/names, additional numbers, ambiguous links or pairings, repeated candidates, and dedicated-column plus Autres duplicates cannot publish. Censored/unnamed evidence retains ordinary row rejection semantics. Narrative is not candidate evidence. No revision or candidate name is special-cased in parsing.

Six previous fixtures retain exact row metadata, rejection records and second-round records, verified against pre-change SHA-256 fingerprints. Their accepted/rejected counts remain 191/8, 209/8, 218/8, 231/13, 256/14 and 256/14 respectively. Their explicit multi-entry maps now recover facts previously missed by the first-link parser. The two historical Cluster17/Elabe review records are kept byte-for-byte reproducible by the audit builder's explicit historical interpretation; runtime parsing does not discard those recovered entries.

## Reviewed facts and correction

| Pollster | Fieldwork | Source sample | Villepin | Primary evidence | Treatment |
|---|---|---:|---:|---|---|
| Ifop | 25–29 September 2026 | 1527 reported; reviewed 1393 registered | 2 | [Notice 10284, p.18](https://www.commission-des-sondages.fr/notices/files/notices/2026/septembre/10284-pres-barometre-election-presidentielle-v6-ifop-le-figaro-30-septembre.pdf) | Existing full canonical map and ID retained |
| YouGov | 17–21 September 2026 | 1103 reported | 2 | [Notice 10270, hypothesis 5, p.26](https://www.commission-des-sondages.fr/notices/files/notices/2026/septembre/10270-pres-iv-yougov-huffpost-23-septembre.pdf) | Explicit 13/14→16-candidate consolidation |
| Cluster17 | 31 August–1 September 2026 | 1711 reported | 3.5 | [Notice 10251, hypothesis 3, p.21](https://www.commission-des-sondages.fr/notices/files/notices/2026/septembre/10251-pres-iv-cluster-17-le-point-5-septembre.pdf) | Existing rounded canonical map and ID retained |

Unchanged Ifop ID: `7ae37b33f52f31df34aa2b1fd0e5a326fff1c7e6b8683255b30472d9fb44309a`.
Unchanged Cluster17 ID: `4810851ea958b928b63298fa94fb082afc6cc7d449b2aad41f023953bb1aac36`.

YouGov 14-candidate predecessor ID: `4708b7c647cfa31ad8c8db6a257450ebe22c8f1cbcc455e7a03d3e7d5d23523e`.
YouGov deterministic successor: `44a6411d5cbb73e264613fcd90f0857576049bd039fd189db6c10e5028eda108`.
The successor records `supersedes_event_ids` as the sorted list of both exact predecessor IDs. Both previous identities are absent from the temporary result; the scalar field is not used for this consolidation. Canonical lineup order is the retained 14-candidate order followed by Ruffin and Bertrand; incoming DOM order does not change this reviewed identity. The complete map totals 100%, versus the predecessors’ 97% and 95%.

The existing post-audit correction registry records the exact incoming factual key, complete canonical key, primary URL/page and explicit successor. Five unchanged sibling hypotheses are registered as exact retention decisions because the existing correction lane requires every row in a reviewed wave to have a decision. Explicit reviewed locator variants account for the added empty quarter table; they do not permit factual-key or URL drift. The existing Ifop correction's incoming map now includes the explicitly recovered Ruffin entry. Its canonical facts/ID are unchanged.

The migration rejects an unregistered expansion of a retained candidate map, unless an existing explicit migration review already authorizes that exact canonical key. Thus removing the YouGov correction cannot silently introduce the 16-candidate successor through ordinary discovery. Historical canonical materialization remains restricted to existing reviewed authorization, revision and provenance.

Raw frozen 240287946 parsing yields **256 first-round, 79 second-round and 13 rejected rows**. The repaired previous revision 240131611 and frozen revision 240287946 have identical accepted factual-key sets; the current table split/reordering changes locators and removes the previously rejected blank-inclusive row from the ordinary table. It adds **no genuinely new poll observation**. Temporary corpus reconciliation is **299→298 first-round**, **81→81 second-round**. Exactly the two reviewed YouGov predecessor IDs are replaced by one successor. All 297 unrelated first-round records and all 81 runoff records remain unchanged. Tracked production corpora retain their original 299/81 contents.

## Confirmed duplicate: older 13-candidate YouGov event

**Conclusive finding: this is the same hypothesis 5, truncated by the historical first-link parser. It is explicitly superseded together with the 14-candidate predecessor in temporary outputs. No tracked production corpus is changed at this checkpoint.**

Event ID: `07a06aee6b9812cfbd6e897ae5004c4ad268ef5cf29ce95c8c0ff2afed183a3a`.
Source provenance: [Commission notice 10270](https://www.commission-des-sondages.fr/notices/files/notices/2026/septembre/10270-pres-iv-yougov-huffpost-23-septembre.pdf), recorded `migration_source_locator` **FR-T0R11**. The event first appears in repository commit `fc857c764f6fd4be22875591a7d6cb9a6da7697a` (`Update polls data`, 2026-09-30T13:50:55Z), found by read-only Git history search. The introducing commit’s second-round source envelope records revision **239927833**, which was fetched once for both rounds. The stored event itself has no revision, commissioner or publication-date field; those absent event fields are not fabricated.

It records YouGov, 17–21 September 2026, n=1103, sample scope `reported`, first round. Reported total is **95%**, status **partial**, unreported share **5%**.

Its complete stored lineup, in stored order:

- Nathalie Arthaud: 1%
- Jean-Luc Mélenchon: 15%
- Fabien Roussel: 1%
- Marine Tondelier: 2%
- Raphaël Glucksmann: 5%
- Gabriel Attal: 8%
- Édouard Philippe: 10%
- Dominique de Villepin: 2%
- Bruno Retailleau: 7%
- Nicolas Dupont-Aignan: 2%
- Marine Le Pen: 33%
- Éric Zemmour: 5%
- François Hollande: 4%

Full exact factual key:

```json
{
  "round": "first_round",
  "pollster_identity": "yougov",
  "fieldwork_start": "2026-09-17",
  "fieldwork_end": "2026-09-21",
  "sample_size": 1103,
  "sample_scope": "reported",
  "candidates": [
    {
      "candidate_id": "bruno-retailleau",
      "score": "7"
    },
    {
      "candidate_id": "dominique-de-villepin",
      "score": "2"
    },
    {
      "candidate_id": "edouard-philippe",
      "score": "10"
    },
    {
      "candidate_id": "eric-zemmour",
      "score": "5"
    },
    {
      "candidate_id": "fabien-roussel",
      "score": "1"
    },
    {
      "candidate_id": "francois-hollande",
      "score": "4"
    },
    {
      "candidate_id": "gabriel-attal",
      "score": "8"
    },
    {
      "candidate_id": "jean-luc-melenchon",
      "score": "15"
    },
    {
      "candidate_id": "marine-le-pen",
      "score": "33"
    },
    {
      "candidate_id": "marine-tondelier",
      "score": "2"
    },
    {
      "candidate_id": "nathalie-arthaud",
      "score": "1"
    },
    {
      "candidate_id": "nicolas-dupont-aignan",
      "score": "2"
    },
    {
      "candidate_id": "raphael-glucksmann",
      "score": "5"
    }
  ]
}
```

Stored hypothesis:

`French source — Nathalie Arthaud, Jean-Luc Mélenchon, Fabien Roussel, Marine Tondelier, Raphaël Glucksmann, Gabriel Attal, Édouard Philippe, Dominique de Villepin, Bruno Retailleau, Nicolas Dupont-Aignan, Marine Le Pen, Éric Zemmour, François Hollande`

Stored scenario key: `02510fba657278699c2afbdcf51b7f9790c175b3fcb312dede4e047262329f5c`.

Its 13 candidate-score pairs are an exact subset of the reviewed 16-candidate successor. It lacks **David Lisnard 2%, François Ruffin 2%, and Xavier Bertrand 1%**. Read-only replay of the original parser at commit `fc857c764f6fd4be22875591a7d6cb9a6da7697a` against immutable revision **239927833** reproduced the entire stored event exactly. This is a parser-truncated representation of hypothesis 5, not a separate scenario.

At that revision, the first-round table belongs to h2 `Sondages concernant le premier tour` → h3 `Année 2026` → h4 `Second semestre 2026`. `FR-T0R11` is physical row 13 (zero-based), the sixth row of a six-row YouGov block, inheriting dates/sample/notice URL through rowspan. Twelve dedicated candidate columns contain the first twelve scores. Its `Autres` cell explicitly contains `4 Hollande<hr>2 Lisnard<hr>2 Ruffin<hr>1 Bertrand`, with a separate candidate link for each entry. Pandas flattened this to text `4 Hollande2 Lisnard2 Ruffin1 Bertrand` and the first Hollande link. Numeric-prefix parsing and first-link identity lookup kept only Hollande 4%.

The repaired parser recovers all 16 candidates at revision 239927833, exactly matching the weighted primary map. Notice 10270 p.15 explicitly asks hypothesis 5 with all sixteen candidates; p.26 reports their scores. The other five first-round questionnaire scenarios have 11, 11, 10, 9 and 11 candidates. None establishes this purported thirteen-candidate hypothesis. The downloaded PDF hash matches the recorded Commission registry hash.

There is no migration-registry materialization entry for this YouGov event. It entered through ordinary French-source discovery. The registry’s identically spelled `FR-T0R11` belongs to an Elabe row in the older audited revision; locators are revision-scoped. The 14-candidate representation first appears in commit `b2c93bac6904d7f562910402e7e82da2b3a95813` against revision **240063728**, at `FR-T0R21`. Its historical parser replay also reproduces the entire stored event exactly. Hollande then came from a regular candidate cell, and Lisnard was the first `Autres` entry, leaving Ruffin and Bertrand unread. The repaired map at that revision again exactly matches the same primary hypothesis. Candidate-set scenario keys and hypothesis-derived event IDs distinguished the two truncated outputs; additive retention preserved both.

## Explicit reviewed many-predecessor contract

The additive schema-1.0 action `consolidate_events` replaces scalar `previous_event_id`, `previous_hypothesis`, `old_factual_key` and `historical_source_revision` with a required `predecessors` collection of 2–8 exact reviewed records. Every predecessor records event ID, hypothesis, factual key, source URL, source revision, source locator, review reason, evidence URLs and official page. Shared incoming/canonical facts, canonical ordered candidates, deterministic successor ID, and reviewed source locator variants retain their existing contracts.

Both predecessors must be first-round strict candidate-score subsets of the canonical map with exactly matching pollster, fieldwork, sample size/scope and primary provenance. Each also passes the existing scalar supersession validator through a validation-only projection. IDs are unique across the entire correction registry; incoming factual keys and canonical targets remain unique, and identity chains remain forbidden. No similarity or position heuristic authorizes consolidation.

Application requires every declared predecessor, with exact factual key, hypothesis, URL and stored migration locator, and no successor. It validates all inputs before removing either record, constructs the complete canonical successor, records sorted plural `supersedes_event_ids`, and reports both removed IDs under the existing `superseded_event_ids` API. A repeat application requires only the exact canonical successor, the complete plural continuity list, and neither predecessor. Missing/unknown predecessors, mixed before/after states, changed facts/provenance, absent successors and malformed declarations fail closed. Legacy scalar one-to-one corrections retain their original behavior.

The production workflow remains unchanged. Its baseline is all 299 current publishable events, with zero rejected-wave exclusions. Its exact condition `len(fetched) < len(reviewed_current)` still rejects the reviewed 298-event temporary result with `refusing unreviewed dataset shrink: 299 expected publishable -> 298 events`. This checkpoint deliberately does not publish the one-time corpus migration or bypass that refusal.

## Validation

Final requested full suites: **231 passed** in 311.750s:

- `test_poll_migration.py`: **108**.
- `test_fetch_polls.py`: **45**.
- `test_post_audit_first_round_corrections.py`: **62**.
- `test_poll_second_round_evidence_drift.py`: **16**.

The exact production-contract command was extracted unchanged from `.github/workflows/update-polls.yml`: **275 passed** in 266.672s. Its original 242-test selection includes 33 added parser/correction regressions across this repair. The focused consolidation class independently passed **24 tests** in 16.553s. Existing Ifop one-to-one supersession and sample corrections continue to pass.

Full logs: `C:\Users\Tanya\AppData\Local\Temp\fr27-consolidation-full-obrj4uts\tests.log` and `C:\Users\Tanya\AppData\Local\Temp\fr27-consolidation-workflow-3esvmwam\tests.log`.

All temporary fetch and frozen reconciliation outputs are under `C:\Users\Tanya\AppData\Local\Temp\fr27-consolidation-live-ub090cyi`.

Frozen `240287946` production integration with read-only tracked previous corpora and no additional official inputs produced **298/81**. Reapplying to that corrected temporary corpus produced the same complete event records and byte-identical saved outputs. The exact first-round ID difference is two predecessors removed and one successor added; all **297 unrelated first-round records** and all **81 runoff records** are identical to the retained inputs. Contract counts are **287 complete, 11 partial, 0 invalid**. The correction report records exactly **one `consolidate_events`**, exactly the two reviewed superseded IDs, and no other first-round supersession. Ifop and Cluster17 remain identical whole records.

| Frozen temporary artifact | Repeat result | Raw SHA-256 |
|---|---|---|
| `frozen/polls.json` | Byte-identical to `frozen_repeat/polls.json` | `f9c53b6523c5eb4d6dbfe32ad3fa2292a0b09c4ae7b4fd14a6247dfe2c83412f` |
| `frozen/second_round_events.json` | Byte-identical to `frozen_repeat/second_round_events.json` | `f5caa7404eb54da2ef5478a772764651d07a8263f0050f1e35e3e336e70bf00b` |

The exact unchanged workflow shrink condition was executed against the 299-event tracked baseline and the actual 298-event frozen result. It raised the expected `refusing unreviewed dataset shrink: 299 expected publishable -> 298 events`. No validation/staging/publication workflow was executed.

### Live-source advance during this checkpoint

The two actual production French fetches used the workflow arguments, with all four output destinations redirected to `first/` and `repeat/`. The live source had advanced to **240294945** and contains five newly discovered Harris first-round observations for **5–8 October 2026**, sample **2004 / reported**, linked to [the Toluna/M6/RTL report](https://tolunacorporate.com/wp-content/uploads/2026/10/Rapport-Toluna-Barometre-Presidentielle-2027-Vague-7-M6-RTL-12-octobre-2026.pdf). Those rows were retained through ordinary discovery, not discarded to force a 298-event live count. Both live outputs are **303/81**: the frozen 298-event corrected corpus plus five new source observations. The two YouGov predecessors remain absent, the canonical successor appears once, and the same 297 retained first-round and 81 runoff records remain unchanged. Live contract counts are **292 complete, 11 partial, 0 invalid**.

The new Harris event IDs are `7d509c935fca987cfeb13a06132d9e23cd97ff2339f3ebba3c048b93a0dc4c06`, `a0670f44b3422b262d409b4e87a311b1a13e481433fb933b3c636a557934ccb9`, `003ea41284c91407011bf3d22784e12600f439baa1cb2600b354cbe5918769a1`, `ff997ba2744a25e14270f76945f0c766519f16bfd7b916c83f25287bc063cb91`, and `6e60fb9acfdb11ec72dddbe7f6e37dd88ba685fa7703e445d5cb30f16b2364a2`. Their complete source-parsed records are inspectable in the temporary live corpora; this checkpoint does not add new reviewed Harris correction records.

| Live artifact | Byte-identical | Semantic-identical | Stable semantic SHA-256 |
|---|---|---|---|
| `polls.json` | Yes | Yes | `0ae8ed7ed844a4e96aef909a2849c0c6c4416db5dbe228447416cdb0fde891ac` |
| `second_round_polls.json` | No: `generated_at` only | Yes | `c7159ad719659a7cf89f74136f82db53865249cdb72a343f9b05b4d3a7b1b2a9` |
| `closest_tested_runoff.json` | No: `generated_at` only | Yes | `8c12860b8421bb84679d907a1c8bf8df8c8456051ac006f39a4efeafd8190a14` |
| `commission_notice_registry.json` | Yes | Yes | `9e8126c32d297943c65ea81fcd4e8ef666f13eb7b7911b76dd91d3ff68b0c5f8` |

Semantic hashes use sorted compact JSON and the existing `semantic_runoff_payload` for runoff envelopes. Recursive raw JSON comparison confirms the only envelope difference is `/generated_at`. The first runner encountered a Windows log-decoding error after fetch output generation; reading the log with its encoding and the subsequent comparison verified the completed outputs. The repeat fetch returned exit 0, and all final comparison/frozen-replay assertions returned exit 0.

Because the new live rows raise the count to 303, the literal count guard would not reject that larger live result. This does not change its demonstrated refusal of the isolated 299→298 consolidation. No guard change, baseline mutation, count padding or bypass is part of the patch.

`git diff --check`: **passed (exit 0)**. Workflow, tracked polling outputs, Commission discovery output and overrides have no diff. No staging or Git-history operation was performed.

This checkpoint changes `post_audit_first_round_corrections.py`, `fr27_post_audit_first_round_corrections.json`, `test_post_audit_first_round_corrections.py`, this report, and `test_fixtures/fr27_polling/notice_10270_previous_events.json`. The earlier parser repair files remain in the same unstaged patch.

## Exact changed / supplied files

Tracked edits:

- `.gitattributes`: pin new evidence fixtures to LF.
- `poll_migration.py`: nearest leaf ownership, ancestry/multiplicity protections, reusable physical-cell grid, strict multi-entry Autres parser.
- `post_audit_first_round_corrections.py`: reviewed locator variants, complete incoming representations, bounded explicit predecessor collections and atomic/idempotent consolidation checks.
- `fr27_post_audit_first_round_corrections.json`: explicit YouGov complete-wave review, both exact predecessor keys/provenance and the two-predecessor→16 successor, existing Ifop incoming representation refresh and reviewed current locators.
- `rehearse_fr_poll_migration.py`: recovered reviewed canonical materialization and rejection of unregistered candidate-map expansion.
- `build_fr27_poll_migration_registry.py`: reproduce the immutable historical audit interpretation while validating recovered facts against its reviewed canonical evidence.
- `test_poll_migration.py`: structural, multi-entry, historical fingerprint, document-order and fail-closed regressions.
- `test_post_audit_first_round_corrections.py`: scope existing Ifop lane tests, complete YouGov primary/consolidation/drift/determinism/identity and unchanged shrink-guard regressions.

Untracked evidence/report files supplied with the patch:

- `test_fixtures/fr27_polling/fr_mediawiki_240287946.json`: pre-existing frozen source bytes unchanged; used as the regression fixture.
- `test_fixtures/fr27_polling/notice_10270_first_round.json`: independent weighted hypothesis-5 primary transcription and recorded PDF hash.
- `test_fixtures/fr27_polling/notice_10270_previous_events.json`: seven exact retained representations covering six hypotheses, including both truncated hypothesis-5 predecessors.
- `docs/french_polling_source_drift_240287946.md`: this corrected report replaces superseded forensic prose.

No edit to `fetch_polls.py`, second-round reconciliation logic, production polling JSON, Commission discovery registry, overrides, publication/routing/orchestration or shrink guard is needed.

Final Git status (all changes unstaged; staged diff empty):

```text
 M .gitattributes
 M build_fr27_poll_migration_registry.py
 M fr27_post_audit_first_round_corrections.json
 M poll_migration.py
 M post_audit_first_round_corrections.py
 M rehearse_fr_poll_migration.py
 M test_poll_migration.py
 M test_post_audit_first_round_corrections.py
?? docs/french_polling_source_drift_240287946.md
?? test_fixtures/fr27_polling/fr_mediawiki_240287946.json
?? test_fixtures/fr27_polling/notice_10270_first_round.json
?? test_fixtures/fr27_polling/notice_10270_previous_events.json
```

Final HEAD and branch remain exactly as specified above. Protected production-output, overrides and workflow diffs are empty.
