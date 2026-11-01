# Candidate Universe provider roster reconciliation

## Failure and exact source

[Run 41043072696](https://github.com/openeventbits/france-2027-signal-lab/actions/runs/41043072696)
failed at manifest construction after promoting [Wikipedia revision **240829045**](https://fr.wikipedia.org/w/index.php?oldid=240829045),
dated **2026-10-29T14:15:52Z**, from registry revision **240468913**.
The previous registry is identical as JSON at the failed run's head
`aba9ef36855e5717dd5fd7ab31a0565362e976bc` and initial repair main
`68ad12fa4afb9411bf44f25cd560d9cb8fc58549`.

The exact transition has 77 identities:

- Added: **Gérard Larcher**, `gerard-larcher`, Wikipedia page ID `88444`,
  `ruled_out`, hidden. He has no reviewed mapping in any provider lane.
- Retained: all 76 existing candidate IDs; no removals or renames.
- Status only: `gabriel-attal` and `bruno-retailleau` change from `declared`
  to `primary_contender`; their IDs, article identities and main tiers remain.
- Proposed registry minus published Bluesky snapshot: `{gerard-larcher}`.
  Published Bluesky snapshot minus proposed registry: the empty set.

The workflow rebuilt its existing derived artifacts but did not extend stored
provider rosters. `validate_candidate_bluesky` correctly rejected 76 versus 77.
Inspection demonstrated the same dependency in YouTube and in all three provider
history validators, including Polymarket. Fixing Bluesky alone merely exposes the
next manifest failure. Attention, news and claims use their existing lifecycle and
active-field contracts; no extra refresh or contract change is needed.

## Chosen transaction

`reconcile_candidate_provider_rosters.py` reconciles only the three stored provider
snapshots and their histories. It does not call a provider or advance any clock.

1. Pin all inputs, including the previous and expected registry and the previous
   manifest. Authenticate previous registry, snapshots, histories and reviewed
   mappings against published manifest hashes, using the manifest's CRLF policy.
2. Validate previous publications against the previous complete registry. Reject
   missing/duplicate IDs, invalid evidence, source rollback, historical candidate
   removal and changes to retained Wikipedia article identity.
3. Copy every existing provider and history row exactly. For a newly added,
   **unmapped** candidate, add the provider's existing null unavailable row and a
   null identity history row with no points. Preserve all envelope clocks and
   every historical point. Revalidate exact coverage against the new registry.
4. Recheck all pinned input bytes, then write the prepared six-artifact bundle.
   Complete manifest validation and exact generated-file scope checks precede
   the workflow's single complete publication commit and non-forcing push.
5. After fetch/rebase, use `origin/main`'s registry, mappings, manifest, snapshots
   and histories as the evidence baseline. Reconcile and rebuild the manifest
   again. A changed target registry, newer source rollback, changed mapping or
   rebase conflict fails closed. A concurrent push makes the normal push fail.

A same-run authoritative refresh would also be valid if every provider collection
and identity check succeeded. It would replace existing counts and clocks, add
network failure dependencies and require YouTube's collection credentials in this
workflow. No new provider evidence is needed for a candidate with no reviewed
mapping. Roster reconciliation is the smaller operation and preserves the last
genuine collection times. The timestamp describes retained provider evidence;
inserting a null row does not claim that a new candidate was observed then.

A newly mapped candidate requires an actual collection and identity review.
Reconciliation cannot supply missing mapped evidence or authorize a new DID,
handle review or verification URL. Existing explicit opt-out/account-unavailable
rows remain unavailable, with their old historical points intact. Existing
collectors still fail on inaccessible mapped accounts and handle/DID mismatches.
History validators are unchanged: they accept the complete reconciled roster and
continue rejecting unauthorized provider identities.

Git is the publication boundary: a write or validation failure can leave temporary
runner files, but cannot publish a partial bundle. No production data is regenerated
in the repair PR; the complete 77-candidate transition is exercised in temporary
copies and disposable local Git remotes. Polling data, source reviews, Commission
evidence, warnings, baselines and provider identity mappings are unchanged.

## Deterministic evidence and tests

Fixtures in `test_fixtures/candidate_universe/` retain:

- `previous_registry_240468913.json`: exact Git blob from initial repair main;
  also the failed run's pre-change registry.
- `wikipedia_240829045.json.gz`: raw MediaWiki JSON responses, keyed by the exact
  collector request parameters. The main metadata query was pinned to revision
  240829045; the supplemental Socialist primary query was bounded to the failure
  time and resolved revision **240743501**, dated **2026-10-26T17:56:38Z**. Exact
  `oldid` parse responses and linked-article resolution responses are retained.
  Retrieval used the existing collector and official French Wikipedia API.
- `provider_evidence_68ad12f.json.gz`: published provider snapshots, histories,
  mappings, manifest, registry and curated candidacy sources from initial repair
  main. These are stored observations, not invented live provider responses.

`test_candidate_provider_rosters` replays those sources offline, reproduces the
original manifest exception, validates the repaired complete manifest, and checks
all preserved rows/clocks, unavailable semantics, rejected identities, roster
errors, source races and the exact output scope. The actual workflow shell bodies
also run against local bare Git remotes: an independent main advance must rebase,
regenerate and push a coherent bundle; invalid retained evidence must produce no
commit or push. Both PR validation and the Candidate Universe preflight run these
regressions. No test contacts Wikipedia, Bluesky, YouTube, Polymarket or GitHub.

## Historical replay isolation repair (1 November 2026)

[Run 41300496226](https://github.com/openeventbits/france-2027-signal-lab/actions/runs/41300496226)
failed two of 613 preflight tests before collection. Both failures reproduce on
`54404202ecf799e5b8fc73e4e4d3f1e34fc6efc3`. The test setup combined a partial
historical provider bundle with current publication data:

| Boundary | Previously retained | Previously read from the current checkout |
| --- | --- | --- |
| Source transition | Previous registry, curated sources, exact Wikipedia responses | None |
| Direct manifest replay | Registry, original manifest, three provider snapshots, three histories, three mappings | Missing manifest lane files and Campaign Events inputs; module-relative polling and news configuration |
| Disposable Git workflow | The same partial bundle overlaid onto a current checkout | All other tracked publication data, including Candidate Attention |

The original manifest records Attention SHA-256
`f3ecf8b2759377f44021aba7953deeb848d49aac81979ca39dc69392ef8b4414`.
Its candidate universe references revision **240468913**, timestamp
**2026-10-17T21:42:44Z**, and `status_as_of=2026-10-17`. At audited main, current
Attention instead hashes to
`1643010e69f9321e02a7cc36f0f5ef842757ad11eb83a8dfff8f0d6e7424fe23`, references
revision **240866042**, timestamp **2026-10-30T19:57:12Z**, and has
`status_as_of=2026-10-30`. The historical target is **240829045**; the production
Attention input is newer than that registry. Manifest parity correctly rejects
this mixture before reaching the intended Bluesky roster error.

The audit also found changed candidate agenda/visibility histories, signals,
news, claims, recent changes, source health, runoff and Commission registry
artifacts. Keeping only Attention historical would leave these moving inputs in
the replay. Poll scope and study bindings also load relative to Python modules,
and the news validator imports three configuration files relative to its module.

`publication_inputs_68ad12f.json.gz` now supplements the unchanged original bundle
with these exact Git blobs from **68ad12fa4afb9411bf44f25cd560d9cb8fc58549**:

- All remaining manifest inputs: Attention, Campaign Events, Candidate Signals,
  Candidate Agenda History, Candidate Visibility History, news, claims, polls,
  Commission registry, second-round polls, closest tested runoff, recent changes
  and source health.
- Campaign Events dependencies: institutional seeds, source registry, manual
  events and manual updates; campaign occurrences used by the Recent Changes validator.
- Module-relative dependencies: election scope, study bindings, news sources,
  discovery queries and publisher policy.
- Semantic navigation dependencies: route registry, issue/agenda/poll page
  manifests and poll explorer.

That is the existing baseline commit (committed 31 October), retaining the
original Attention publication generated on **30 October**. No source was
replaced with a newer publication or a synthetic observation. The archive uses
sorted JSON keys and gzip `mtime=0`; each value preserves its original UTF-8 Git
blob bytes exactly.

`historical_publication_68ad12f.json` records the baseline commit and every
retained file's Git blob ID, SHA-256 and byte length, plus digests for both
archives and the original Wikipedia/previous-registry fixtures. The test pins the
inventory digest, authenticates all containers and members, validates the original
manifest, then compares every published lane and related-file digest with the
retained source. Auxiliary configuration without a manifest record is bound to
its Git blob and SHA-256. Tracked JSON fixture CRLF is normalized; archive bytes
and decoded Git source bytes remain exact. Missing, changed or inconsistent
required evidence fails before replay, without falling back to production.

Both replay paths install the same authenticated complete publication. Direct
builders and manifest validation execute current Python copied beside historical
data, so their module-relative reads cannot escape into current production.
The disposable checkout copies current code/templates and excludes root JSON
publication data before installing the baseline. Future missing dependencies
therefore fail closed. The current workflow itself is unchanged.

Regression coverage retains the exact 76-to-77 transition, original Bluesky
failure, successful six-artifact reconciliation, unchanged observations/clocks,
invalid-provider no-commit/no-push behavior and real post-rebase ancestry. Added
cases reject inconsistent historical Attention, altered archives/inventory/member
bytes, and missing containers or Attention members. The production-refresh
regression forbids any current JSON copy during a complete direct replay and
checks retained Attention, news, claims, recent changes and polling configuration
bytes after successful reconciliation.


## Completed-primary source layout (1 November, run 41326120055)

[Run 41326120055](https://github.com/openeventbits/france-2027-signal-lab/actions/runs/41326120055)
ran on `c35ba9886943f6e143c89f20450442e58c36332b` and passed all 618 production
preflight tests. Live collection then failed on Wikipedia revision **240912833**,
dated **2026-11-01T12:13:58Z**, because the required primary-contender heading was
absent. The publication stopped before registry promotion, commit or push.

The source replaced the contender section with an **Élection primaire** section, a **Primaire socialiste**
subsection and a table captioned **Résultats définitifs validés par la Haute
Autorité**. This is a completed-primary results
table, with candidate/party/first-round headers followed by votes/percentage
headers, and includes turnout and totals. Treating it as another candidate table
would parse historical results or summary rows as current candidacy evidence.

The collector now recognizes only that exact section/subsection/caption/header
layout as a replacement for the absent primary-contender category. It does not
extract any results-table row, infer a candidate status from votes, or make
other candidate categories optional. Missing, renamed, unscoped, incomplete or
duplicate replacement layouts remain rejected. Supplemental-source extraction,
identity reconciliation and curated first-party lifecycle evidence are unchanged.

`wikipedia_240912833.json.gz` retains six actual MediaWiki responses: metadata
and exact-oldid HTML for both configured pages, plus linked-article resolution.
Metadata requests were bounded to the failed collection cutoff,
**2026-11-01T16:33:01Z**; each record retains both collector parameters and actual
bounded request parameters. The archive has sorted JSON keys and gzip `mtime=0`,
and SHA-256
`c26b4afb2d746fc256523335dc060046be3d48dbad0bed38c52ce317ad74470e`.
The archive also retains the registry, curated sources and original publication
manifest from the immutable run commit above, with their Git blob IDs. The test
verifies these IDs and registry-to-manifest hash parity. Its baseline requires no
Git history or subsequently refreshed production inputs, so the exact-source
regression also runs in the PR workflow's shallow checkout.

The main page yields 71 candidacy records; supplemental reconciliation yields
75 extracted records and preserves all 77 registry identities, with no additions.
Existing party-selected and primary-eliminated lifecycle statuses remain intact.
Attal and Retailleau are now in the declared section of this exact upstream
revision; their source-derived status follows that section. Tests cover the
full pinned replay, results exclusion, every other required category, unknown
headings, malformed results markers, misplaced or duplicate results, and unchanged
last-good output when collection fails. Production datasets and workflows are
not changed by this repair.
