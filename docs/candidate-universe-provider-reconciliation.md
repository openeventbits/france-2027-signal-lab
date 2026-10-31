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
