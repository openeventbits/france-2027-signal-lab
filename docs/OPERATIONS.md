# France 2027 Signal Lab — Operations

**France 2027 Signal Lab (FR27)** is an automated public-data product whose repository is also part of its publication mechanism.

This document describes the operating discipline used to change, validate, refresh, and publish FR27 safely.

It is intended for maintainers working on production code, data contracts, workflows, generated artifacts, and frontend behavior.

For system structure, see [`ARCHITECTURE.md`](ARCHITECTURE.md). For research semantics, see [`METHODOLOGY.md`](METHODOLOGY.md).

## Operating principle

The primary operational rule is:

> Build candidate state, validate it, rebuild dependent state, validate again, construct the publication manifest, restrict the publication scope, and only then promote.

A successful fetch is not a successful publication.

A successful parser run is not a successful publication.

A file existing on disk is not proof that it is valid for the public product.

Production success requires the resulting publication state to remain internally coherent.

## Change classification

Before changing a contract, validator, test, writer, fixture, or production assumption, classify what kind of assertion is being modified.

FR27 uses four practical classes.

### A — Frozen historical

These assertions protect evidence or migration state that should no longer change during normal production.

Examples include:

- reviewed historical poll migrations;
- fixed historical source snapshots;
- known historical identifiers;
- exact historical fixtures; and
- previously reviewed migration decisions.

Appropriate validation can include exact values or exact-byte fixtures.

Current production changes are not a reason to rewrite frozen historical expectations.

### B — Semantic or business-rule

These assertions protect the meaning of the product.

Examples include:

- poll comparability;
- candidate status projection;
- missing-versus-zero behavior;
- topic classification;
- event evidence rules;
- candidate relationship rules; and
- visibility denominator semantics.

These rules should normally be tested with focused synthetic fixtures.

A semantic test should demonstrate the intended rule without depending unnecessarily on today's production counts.

### C — Dynamic current-production

These assertions apply to data that legitimately changes over time.

Examples include:

- current candidate counts;
- current news volume;
- current source-network size;
- current event inventory;
- current poll inventory; and
- current fact-check counts.

Dynamic production should normally be validated through structural and relational invariants rather than frozen snapshot totals.

Examples include:

- identifiers are unique;
- required fields are valid;
- candidate projections agree;
- shares agree with denominators;
- dates form the required sequence;
- related artifacts reconcile; and
- manifest hashes agree with publication bytes.

### D — Workflow safety

These assertions protect the publication process itself.

Examples include:

- shared writer concurrency;
- temporary-build behavior;
- validation-before-promotion;
- exact generated-file scope;
- exact staged scope;
- post-rebase rebuilding;
- publication-manifest rebuilding; and
- deployment or publication parity.

Workflow-safety assertions should not be weakened merely to make a failing run green.

## One bounded change at a time

Production work should be narrow.

Before implementation, define:

- the user or operational problem;
- the evidence or source involved;
- the minimum required implementation;
- the semantic rule affected;
- the files expected to change;
- the tests expected to prove the change; and
- the production writer, if any, affected by it.

Avoid opening several unrelated architecture, source, UI, and pipeline changes in one branch.

A bounded vertical slice is easier to review, validate, publish, and recover.

## Manual-first production changes

When introducing or materially changing a production pipeline, prefer proving the behavior manually before relying on its scheduled execution.

A safe sequence is:

1. establish the semantic contract;
2. test against controlled inputs;
3. run the relevant builder or collector manually;
4. inspect candidate output;
5. validate the exact output;
6. verify derived dependencies;
7. verify repository scope;
8. verify the workflow contract; and
9. only then rely on scheduled production execution.

A schedule should automate an already-understood process rather than act as the first integration test.

## Production workflows

FR27 currently has automated production writers for areas including:

- Candidate Attention;
- Candidate Universe;
- Claims Under Scrutiny;
- Election News;
- Polling and runoff-related polling artifacts.

Writer workflows can be triggered on schedules and manually.

Campaign Events currently has a dedicated validation workflow rather than a scheduled production writer.

That workflow rebuilds the campaign-event artifact from authoritative inputs, compares the result with the tracked publication, verifies the publication manifest, and confirms that validation itself leaves the repository unchanged.

Repository-level dashboard validation is separate from both categories.

## Shared writer concurrency

Production writer workflows use the shared concurrency group:

    production-data-update

Cancellation is disabled.

This serializes writers that could otherwise modify related repository publication state concurrently.

The shared boundary matters because a writer can affect more than its obvious primary artifact.

A writer may also need to update or verify:

- derived candidate data;
- Recent Changes;
- source health;
- related poll artifacts;
- the publication manifest; and
- other explicitly declared dependent outputs.

A manually dispatched writer is still a production writer and should remain inside the same safety boundary.

## Writer transaction model

The target production pattern is:

    Current valid repository state
              |
              v
       Obtain source evidence
              |
              v
       Build temporary output
              |
              v
       Validate candidate output
              |
              v
       Rebuild dependencies
              |
              v
       Validate relationships
              |
              v
       Build publication manifest
              |
              v
       Verify file scope
              |
              v
       Stage exact files
              |
              v
       Reconcile moving main
              |
              v
       Rebuild / revalidate if needed
              |
              v
            Publish

If a required step fails, promotion stops.

The goal is transaction-like publication even though repository files are the publication medium.

## Temporary builds

Live-source output should be constructed outside the tracked production path when practical.

Temporary files can be used for:

- source inventories;
- candidate public artifacts;
- source-health candidates;
- derived histories;
- Recent Changes candidates; and
- other generated outputs.

The tracked production file should not be overwritten merely because collection completed.

Temporary output must first satisfy its own contract and any relevant relational checks.

## Validate before promotion

Validation should occur at the closest useful boundary.

Examples include:

- validate source response structure before transformation;
- validate a poll event before adding it to a published corpus;
- validate a candidate artifact against the canonical candidate universe;
- validate shares against denominators;
- validate campaign events before promotion;
- validate source-health state before replacing the tracked file; and
- validate the publication manifest after dependent files have been rebuilt.

A later frontend test should not be the first place a malformed data artifact is detected.

## Derived-state rebuild order

When an upstream public artifact changes, identify every derived artifact whose meaning depends on it.

The dependency order should be explicit.

Conceptually:

    accepted upstream evidence
        -> dependent analytical artifacts
        -> publication manifest

The manifest comes last because it describes the final publication state.

Building the manifest before rebuilding dependencies can create a valid-looking manifest for stale derived data.

## Publication manifest

`publication_manifest.json` is part of the production transaction.

After relevant public artifacts are finalized, rebuild the manifest and validate it.

Operational checks can include:

- lane availability;
- lane validity;
- artifact hash;
- schema version;
- timestamp state;
- related-file hashes;
- warnings;
- record relationships;
- source-network summaries; and
- snapshot identity.

The manifest should describe the bytes that are actually intended for publication.

A stale manifest is a publication failure even when the changed primary artifact is itself valid.

## No-op behavior

A scheduled writer should avoid unnecessary repository churn.

If the semantic public state has not changed, a writer should preserve tracked output where its contract supports doing so.

Volatile metadata such as generation or request timing should not automatically force a new public commit when the substantive data is unchanged.

No-op handling reduces:

- meaningless commits;
- unnecessary deployments;
- manifest churn;
- merge pressure between production writers; and
- difficulty auditing genuine changes.

The exact no-op rule belongs to the relevant writer contract.

## Exact generated-file scope

Before committing a production update, inspect the complete repository status.

A writer should have an explicit allowlist of files it is permitted to modify.

Unexpected files are a failure condition.

Do not broadly stage the repository with commands that can accidentally include unrelated modifications.

The production sequence should prefer explicitly named files.

For example:

    git add -- expected-file-1 expected-file-2

The exact set depends on the writer.

A scope check should occur before staging and again when useful after rebasing or rebuilding.

## Exact staged scope

Generated-file scope and staged-file scope are separate checks.

After staging, inspect the index and verify that every staged path belongs to the writer's allowlist.

A valid worktree is not sufficient if the wrong files have been staged.

If unexpected files appear in the index, stop rather than committing around the problem.

## Moving `main`

FR27 production writers share a repository with other automated writers.

`main` can therefore advance while a workflow is running.

A safe writer should not assume that the checkout from the beginning of the job remains the current remote publication base at commit time.

The operational pattern is:

1. build and validate candidate state;
2. create the controlled publication commit;
3. fetch current `origin/main`;
4. reconcile with the newer remote state using the writer's safe strategy;
5. rebuild any outputs whose inputs may have changed;
6. rebuild and check the publication manifest;
7. recheck allowed file scope; and
8. only then publish.

A rebase is not merely a Git housekeeping step.

If the base changed, derived artifacts may need to be recalculated against that newer repository state.

## Post-rebase validation

After reconciling with a newer `main`, do not blindly push the previously constructed bytes.

Re-evaluate the assumptions affected by the rebase.

Depending on the writer, this can include:

- rebuilding the primary candidate artifact;
- validating it against the current candidate registry;
- rebuilding derived data;
- rebuilding the manifest;
- checking whether semantic content still differs;
- checking file scope again; and
- amending the publication commit when the final valid bytes changed.

This protects against publishing a commit that was valid against an obsolete base but inconsistent with the current repository.

## Last-good preservation

A temporary external failure should not automatically replace valid public state with invalid or empty output.

External sources can:

- time out;
- rate-limit;
- return malformed data;
- change markup or schema;
- temporarily disappear;
- return incomplete responses; or
- provide evidence that cannot yet be reconciled.

Where a lane's design supports last-good preservation, retain the previous valid public artifact when a candidate replacement fails its contract.

Expose the operational problem separately through:

- source-health state;
- freshness metadata;
- warnings;
- failed workflow status; or
- other explicit operational signals.

Last-good preservation is not permission to conceal stale data.

Freshness and validity are different states.

## Source-health operations

`source_health.json` records persistent media-route operational state.

When investigating a media collection problem, distinguish at least:

- successful route with accepted yield;
- successful route with zero accepted yield;
- transient failure;
- repeated failure;
- route not due;
- route never attempted;
- disabled route; and
- removed route.

A source returning no qualifying election coverage is not automatically broken.

Conversely, a large public news corpus does not prove that all configured routes are healthy.

Source health should be inspected separately from corpus volume.

## External-source failure

When a live source fails, first determine whether the failure is:

- network or availability related;
- rate limiting;
- source-format change;
- parser regression;
- credential or permission failure;
- source-policy mismatch; or
- valid absence of new evidence.

Do not immediately modify research semantics to compensate for an operational source problem.

Retry and fallback behavior should remain bounded and deterministic.

## HTTP failure handling

Network-facing code should fail predictably.

Appropriate controls can include:

- request timeout;
- bounded retries;
- exponential or controlled backoff;
- retry-instruction handling;
- response-size limits;
- compressed-response handling;
- conditional requests;
- malformed-response rejection; and
- explicit transient-failure state.

A network retry should not become an unbounded workflow hang.

A large or malformed response should not be accepted merely because the server returned HTTP success.

## Candidate-universe changes

The candidate registry is a high-impact upstream dependency.

A legitimate candidate-universe change can affect:

- active candidate projections;
- Candidate Attention;
- candidate histories;
- claims queries;
- candidate synthesis;
- frontend candidate surfaces; and
- the publication manifest.

Do not fix downstream parity failures by independently modifying downstream candidate membership.

First verify the canonical candidacy-status change and then rebuild or reconcile dependent artifacts according to their contracts.

## Polling production

Polling writers must preserve atomic poll-event structure.

Operational polling updates should verify:

- source identity;
- fieldwork dates;
- round;
- hypothesis;
- candidate results;
- deterministic event identity;
- scenario identity;
- completeness or partial state;
- Commission notice coverage; and
- runoff-related dependencies where applicable.

Do not repair a current polling failure by weakening historical migration fixtures or by combining incompatible hypotheses.

Unresolved relevant Commission notice coverage should remain visible as a warning until it is deterministically resolved.

## Election-news production

Election News has a broad dependency surface.

A news refresh can affect:

- the rolling news inventory;
- accepted news publication;
- candidate visibility;
- candidate visibility history;
- campaign agenda;
- candidate agenda history;
- Recent Changes;
- source health;
- source icons; and
- the publication manifest.

For that reason, a news writer must treat its output as a coordinated publication slice rather than as a single JSON file.

Temporary builds and dependent validation are especially important in this lane.

## Source icons

Source-identification icons are operationally separate from the substantive rights governing their use.

When source-icon retrieval is part of a production workflow:

- keep icon changes inside the writer's explicit allowed scope;
- do not let icon failure silently corrupt unrelated analytical data;
- preserve source-to-icon mapping deterministically where possible; and
- treat provenance and rights review separately from collection mechanics.

The applicable third-party rights framework belongs in `THIRD_PARTY_NOTICES.md`, not in workflow logic.

## Campaign Events validation

Campaign Events currently uses a dedicated validation workflow.

Its role includes verifying that:

- authoritative campaign-event inputs rebuild the tracked artifact;
- the tracked artifact is synchronized with those inputs;
- the publication manifest is synchronized;
- Campaign Events contract tests pass; and
- validation itself does not modify repository state.

This is different from a scheduled live-source production writer.

A future campaign-event writer should not be assumed to exist merely because the validation workflow has an `update-` filename.

## Repository-level dashboard validation

`.github/workflows/validate-dashboard.yml` is a read-only integration gate for pull requests and manual runs.

Its current smoke-test surface covers areas including:

- publication manifest;
- frontend factual contracts;
- candidate signals frontend;
- final dashboard shell;
- agenda frontend hardening;
- Media Pulse workflow contract; and
- Recent Changes.

This workflow complements component tests.

It should not be treated as proof that every source-specific production path has been exercised.

## Test selection

Run tests appropriate to the changed contract.

Do not automatically run only the smallest test that happens to pass.

At minimum, consider:

- direct unit or contract tests;
- builder tests;
- related cross-artifact tests;
- workflow contract tests;
- publication-manifest tests; and
- frontend integration tests where public meaning or rendering is affected.

The test scope should follow the dependency surface of the change.

## Regression tests

A production incident should normally result in a regression test when the failure exposes a missing contract or unsafe assumption.

A good regression test reproduces the underlying failure mode.

Avoid tests that simply freeze the current production snapshot unless that snapshot is genuinely historical.

Examples of useful regression targets include:

- malformed source response;
- duplicate identity;
- stale candidate projection;
- ambiguous reconciliation;
- unexpected writer file scope;
- manifest mismatch;
- missing denominator;
- invalid timestamp; and
- parser behavior that previously caused the incident.

## Do not weaken contracts to clear a failure

When production fails, do not first ask:

> Which assertion can be removed?

Ask:

> Which contract is the failure telling us is inconsistent with reality?

Possible outcomes include:

- the external source changed;
- the parser is wrong;
- the semantic rule is wrong;
- the fixture is stale;
- the test is testing the wrong class of assertion;
- the current production artifact is invalid; or
- the workflow is unsafe.

Change the correct layer.

A green workflow obtained by weakening the wrong invariant is not a successful repair.

## Incident classification

When a production run fails, classify the failure before editing code.

Useful incident classes include:

- **source failure** — upstream unavailable, malformed, or rate-limited;
- **parser failure** — source exists but extraction no longer matches it;
- **semantic failure** — extracted evidence conflicts with a research rule;
- **contract failure** — artifact violates structural or relational invariants;
- **dependency failure** — derived artifacts no longer agree;
- **workflow failure** — staging, concurrency, rebase, or publication logic failed;
- **deployment failure** — repository state is valid but the live publication is not; and
- **expected no-data condition** — no new qualifying evidence exists.

Classification helps prevent fixing the wrong component.

## Incident response sequence

A practical incident sequence is:

1. identify the first failing boundary;
2. inspect the exact source or artifact involved;
3. classify the failure;
4. determine whether current public state remains valid;
5. preserve last-good state where applicable;
6. reproduce the failure locally or manually;
7. correct the responsible contract, parser, transformation, or workflow;
8. add or update a focused regression test;
9. run the relevant component and integration tests;
10. prove manual production behavior;
11. publish through the normal bounded writer path; and
12. require scheduled production proof when the incident affected a scheduled writer.

Do not skip from a failing scheduled run directly to an unreviewed production patch.

## Scheduled production proof

A manual workflow success is useful but does not always prove the scheduled path.

If an incident specifically affected scheduled behavior, require a subsequent scheduled run to demonstrate recovery.

This is especially important when the difference involves:

- event context;
- schedule-specific conditions;
- credentials;
- concurrency;
- time calculations;
- route scheduling;
- retry behavior; or
- code branches dependent on `workflow_dispatch` versus `schedule`.

The incident is not fully closed until the failing mode has been demonstrated to work.

## Manual versus scheduled runs

Manual dispatch is valuable for:

- controlled production proof;
- diagnosing a failed schedule;
- validating a repaired writer;
- exercising optional retry paths; and
- confirming live-source behavior before waiting for the next schedule.

Do not assume manual and scheduled executions are identical.

Workflow conditions can intentionally differ by event type or time.

When debugging, compare the actual execution path.

## Publication commit messages

Automated publication commits should be narrow and descriptive.

The commit should correspond to the writer's allowed publication scope.

Avoid combining unrelated maintenance edits with automated data publication.

This makes it possible to determine from repository history whether a commit represents:

- Candidate Attention refresh;
- candidate-universe change;
- claims refresh;
- news refresh;
- polling refresh; or
- another explicit publication operation.

## Working with a moving production branch

Human-maintained feature or documentation branches can become stale while automated writers advance `main`.

Before final integration:

- fetch `origin/main`;
- inspect commits added since the branch base;
- inspect files changed on `main`;
- determine whether there is semantic or file overlap;
- preserve local work before rebasing or fast-forwarding;
- synchronize using a safe strategy; and
- re-run relevant validation against the updated base.

A production-data-only advance may require no content changes to a documentation branch, but it still changes the base from which the final PR should be evaluated.

## Documentation-only work

Documentation should not accidentally stage or modify generated production data.

For a documentation branch:

- keep documentation work uncommitted until reviewed when desired;
- synchronize with moving `main` carefully;
- inspect overlap before restoring documentation work;
- avoid touching generated data merely to make the branch appear current; and
- perform final factual consistency checks against the base before merging.

Documentation describing dynamic counts should prefer contracts and meanings over frozen current totals.

## Publication and live verification

Repository publication and live deployment are related but separate checkpoints.

After a production or release change that affects the public dashboard, verify the applicable chain:

    expected repository files
        -> valid publication manifest
        -> committed publication state
        -> deployed static site
        -> public artifact / interface consistency

A green collector run alone is not enough.

For release or deployment work, verify that the live site reflects the intended repository state before considering the change complete.

## Rollback thinking

Because FR27 preserves public historical evidence and deterministic identifiers, rollback should be deliberate.

Before reverting a production change, determine whether the bad commit changed:

- only generated current data;
- a semantic contract;
- historical evidence;
- a migration registry;
- a workflow;
- frontend interpretation; or
- several of those at once.

Blindly reverting a data commit can also revert legitimate concurrent updates from another writer.

Prefer restoring a known-valid coherent publication state or correcting forward when that is safer.

## Secrets and credentials

Credentials used by production collectors belong in repository or platform secret storage.

Do not:

- commit API keys;
- print secrets into logs;
- embed credentials in public source configuration; or
- copy credentials into generated public JSON.

A secret-dependent source should fail safely when credentials are missing or rejected.

Public artifacts should remain credential-free.

## Local validation discipline

When working locally:

- verify the expected branch and repository path;
- inspect `git status` before changing files;
- understand which files are authoritative versus generated;
- use temporary outputs for destructive or live-source experiments;
- run focused tests before broad integration tests;
- inspect generated diffs;
- use `git diff --check` for tracked changes when appropriate; and
- do not commit or push until the bounded change has been reviewed.

On Windows, newline conversion warnings can occur because Git and the working tree may use different newline conventions.

Do not mistake a harmless newline warning for a semantic data change, but also do not ignore actual byte-contract requirements for frozen fixtures.

## Production checklist

Before considering a production change complete, answer all of the following:

- Is the affected assertion classified correctly?
- Is the semantic rule explicit?
- Are authoritative inputs identified?
- Was candidate output built away from tracked production state where appropriate?
- Did direct contract validation pass?
- Were dependent artifacts rebuilt?
- Did cross-artifact validation pass?
- Was the publication manifest rebuilt last?
- Does the manifest describe the intended bytes?
- Is generated-file scope exactly controlled?
- Is staged-file scope exactly controlled?
- Was moving `main` reconciled safely?
- Were post-rebase outputs revalidated where necessary?
- Are last-good semantics preserved?
- Did relevant unit, contract, workflow, and frontend tests pass?
- Was manual production behavior proven where required?
- If the incident was schedule-specific, did a scheduled run prove recovery?
- Does the deployed public product correspond to the intended publication state?

If any required answer is no, the operation is not complete.

## Related documentation

- [`PRODUCT_GUIDE.md`](PRODUCT_GUIDE.md) — how to read the public product.
- [`METHODOLOGY.md`](METHODOLOGY.md) — research semantics and evidence interpretation.
- [`DATA_AND_PROVENANCE.md`](DATA_AND_PROVENANCE.md) — datasets, provenance, timestamps, and source health.
- [`ARCHITECTURE.md`](ARCHITECTURE.md) — system structure and publication architecture.
- [`../CONTRACT.md`](../CONTRACT.md) — non-negotiable repository and data invariants.
- [`../README.md`](../README.md) — project overview.