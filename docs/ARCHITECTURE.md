# France 2027 Signal Lab — Architecture

**France 2027 Signal Lab (FR27)** is implemented as a static public dashboard backed by versioned data artifacts, deterministic builders, executable data contracts, automated production workflows, and repository-based publication.

This document describes how those parts fit together.

It explains system structure rather than research meaning. For measurement semantics, see [`METHODOLOGY.md`](METHODOLOGY.md). For datasets and evidence provenance, see [`DATA_AND_PROVENANCE.md`](DATA_AND_PROVENANCE.md).

## Architectural goals

The architecture is designed around several constraints:

- the public product should remain inspectable;
- data transformations should be reproducible where their sources permit it;
- public artifacts should satisfy explicit contracts before promotion;
- current-data validation should test structure and relationships rather than depend on fragile snapshot counts;
- live-source failure should not unnecessarily destroy last-good public state;
- automated writers should not publish conflicting partial states;
- frontend behavior should consume explicit published semantics rather than independently recreate research rules; and
- historical evidence and deterministic identities should remain stable across routine updates.

FR27 therefore favors explicit files, contracts, and publication boundaries over an opaque service layer.

## System overview

At a high level, the production path is:

    External public sources
            |
            v
    Collectors / source-specific readers
            |
            v
    Normalization and deterministic classification
            |
            v
    Executable data contracts
            |
            v
    Generated JSON artifacts
            |
            v
    Dependent derived artifacts
            |
            v
    Publication manifest
            |
            v
    Integration and frontend checks
            |
            v
    Repository publication
            |
            v
    Static dashboard

There is no persistent application server required in the normal public read path.

The browser loads static frontend assets and published data files.

Dedicated GitHub Actions writer workflows refresh repository-published state, while repository validation runs separately.

## Repository layers

The repository can be understood as several interacting layers.

### Source and configuration layer

This layer defines where evidence can come from and which controlled inputs govern collection.

Examples include:

- media-source configuration;
- publisher policy;
- discovery queries;
- manual exclusions;
- candidate-status authority;
- Commission des sondages notice registries;
- campaign-event source definitions;
- migration registries; and
- reviewed configuration or exception files.

These files are production inputs.

They should not be confused with derived analytical outputs merely because both may be represented as JSON.

### Collection layer

Collectors obtain or read evidence from external sources.

Different evidence classes require different collection logic.

Examples include:

- polling ingestion;
- media-feed collection;
- Wikimedia pageview collection;
- professional fact-check collection;
- campaign-event discovery; and
- candidate-universe discovery.

Collectors are source-specific because external systems differ in structure, availability, timestamps, limits, and failure behavior.

### Normalization and classification layer

External representations are converted into stable FR27 structures.

This layer can perform tasks such as:

- text normalization;
- source URL normalization;
- candidate identity mapping;
- deterministic candidate matching;
- poll-hypothesis construction;
- topic classification;
- source-policy enforcement;
- event-type normalization;
- time normalization;
- duplicate detection; and
- deterministic identifier generation.

Normalization is intended to make evidence structurally usable without silently changing its substantive meaning.

### Contract layer

Executable contracts define the structure and invariants expected of important datasets.

Examples include contracts for:

- polling;
- candidate candidacy status;
- candidate attention;
- candidate visibility history;
- candidate agenda history;
- campaign events;
- claims publication;
- source health; and
- candidate signals.

These validators are not merely formatting checks.

They can enforce relational rules such as:

- deterministic identity;
- candidate-universe consistency;
- complete date sequences;
- valid denominators;
- deterministic ordering;
- allowed status values;
- source provenance requirements;
- exact schema fields;
- valid event-state relationships; and
- compatibility between related datasets.

The human-readable repository contract in [`../CONTRACT.md`](../CONTRACT.md) documents major non-negotiable invariants that span these executable components.

## Builders and transformations

Builders transform accepted inputs into public or supporting artifacts.

Representative build programs cover areas such as:

- campaign events;
- candidate agenda history;
- candidate attention;
- candidate signals;
- candidate visibility history;
- polling migration infrastructure;
- publication manifests; and
- Recent Changes.

A builder should not silently introduce new research semantics.

Where possible, a substantive rule should live in an explicit contract or controlled transformation that can be tested independently.

## Primary and derived artifacts

Some FR27 artifacts remain close to external observations. Others derive new structures from already accepted FR27 evidence.

For example:

    External poll source
        -> poll normalization
        -> polls.json

    Accepted election coverage
        -> candidate linkage and topic classification
        -> news_wire.json
        -> candidate_visibility_history.json
        -> candidate_agenda_history.json

    Candidate evidence lanes
        -> candidate_signals.json

    Published FR27 evidence
        -> recent_changes.json

Derived artifacts should retain enough provenance to identify their upstream evidence class.

The frontend should not need to reconstruct research rules from presentation state.

## Public data artifacts

The principal public publication lanes currently include:

| Lane | Public artifact |
| --- | --- |
| Campaign events | `campaign_events.json` |
| Candidacy status | `candidate_candidacy_status.json` |
| Candidate agenda history | `candidate_agenda_history.json` |
| Candidate attention | `candidate_attention.json` |
| Candidate signals | `candidate_signals.json` |
| Candidate visibility history | `candidate_visibility_history.json` |
| Claims | `claims_under_scrutiny.json` |
| News | `news_wire.json` |
| Polls | `polls.json` |
| Recent changes | `recent_changes.json` |
| Runoff | `second_round_polls.json` |
| Source health | `source_health.json` |

Some lanes also have related supporting files.

For example, polling publication is connected with `commission_notice_registry.json`, while runoff publication can include `closest_tested_runoff.json`.

The current `publication_manifest.json` is authoritative for the active publication inventory.

## Publication manifest

`build_publication_manifest.py` constructs `publication_manifest.json`.

The manifest is an integrity and publication-boundary artifact.

It records publication state separately from the substantive contents of individual lanes.

Depending on the lane, it can include:

- availability;
- validity;
- canonicalized byte size;
- SHA-256 identity;
- schema version;
- data-as-of information;
- timestamp status;
- generation time;
- warnings;
- record counts; and
- related-file metadata.

The manifest also records snapshot-level publication identity and can expose source-network and source-health summaries.

### Canonical publication bytes

The manifest normalizes repository newline forms when calculating publication-byte identity.

This reduces platform-specific newline differences between Windows and Unix-like environments from becoming accidental publication differences.

Hashes therefore correspond to canonicalized publication bytes rather than arbitrary local newline representation.

### Lane-specific validation

Manifest construction is not simply directory enumeration.

The builder integrates validation logic for multiple public artifact types.

A file can therefore exist on disk while failing the validation required for a valid publication lane.

Availability and validity are separate concepts.

### Publication snapshot

The manifest identifies the publication state after the relevant artifacts have been constructed.

This allows validation to compare the files expected by the public product with the files actually represented by the manifest.

A filename alone is not sufficient proof that an artifact belongs to the current publication state.

## Frontend architecture

The public interface is implemented using static HTML, CSS, JavaScript, images, and JSON data.

The frontend consumes repository-published artifacts rather than querying a private application database.

Major public surfaces include:

- What Changed;
- Race at a Glance;
- Media Pulse;
- Candidates;
- Agenda;
- Policy Issues;
- Campaign Events;
- Runoff;
- Polling Evidence;
- Signal Desk;
- Election Coverage Reader;
- Coverage Analysis; and
- Source Network.

Presentation logic should preserve the semantic boundaries established by the data layer.

For example, frontend code should not:

- convert missing evidence into zero;
- join incompatible polling scenarios;
- reinterpret Wikipedia attention as electoral support;
- turn an untested runoff pairing into polling evidence; or
- replace explicit unavailable or unresolved states with an apparently complete result.

## Frontend and integration contracts

The repository contains tests that validate important relationships between published data and the interface.

These tests help prevent presentation changes from silently changing public meaning.

Frontend-oriented validation covers areas such as:

- publication-manifest integration;
- factual labels and disclosures;
- candidate signals;
- dashboard shell behavior;
- agenda presentation;
- Media Pulse expectations;
- Recent Changes; and
- workspace-specific rendering.

Frontend tests complement data-contract tests.

They do not replace them.

## Production workflows

Dedicated GitHub Actions writer workflows perform scheduled and manual production updates.

Current automated production-writer areas include:

- candidate attention;
- candidate universe;
- claims under scrutiny;
- election news;
- polling.

Campaign events currently have a dedicated validation workflow rather than a scheduled production writer. That workflow rebuilds and verifies the campaign-event publication from its authoritative inputs without publishing a new data state.

Repository-level dashboard validation is handled separately and is not itself a production data lane.

Different evidence lanes have different source dependencies and update cadences.

The architecture does not assume that every publication lane updates at the same frequency.

## Shared production-writer concurrency

Production writer workflows use the shared concurrency group `production-data-update`, including when those workflows are manually dispatched.

Cancellation is disabled for these production jobs.

The purpose is to prevent overlapping production writers from independently modifying related publication state.

This matters because a workflow may affect:

- its primary dataset;
- one or more dependent artifacts;
- source-health state;
- Recent Changes;
- candidate synthesis; and
- the publication manifest.

Concurrent writers could otherwise each operate on different assumptions about repository state.

## Temporary build and promotion

For live-source writers, the production pattern is conceptually:

    Existing published state
             |
             v
       Fetch live sources
             |
             v
      Build candidate output
             |
             v
         Validate
          /   \
        pass   fail
         |      |
         v      v
    Rebuild     Preserve
    dependent   last-good
    artifacts   published state
         |
         v
      Validate
         |
         v
    Build manifest
         |
         v
       Promote

Collection completing successfully is not enough to make candidate output production state.

Validation precedes promotion.

The goal is to avoid replacing valid public state with malformed, partial, or relationally inconsistent output after a source or parser failure.

## Last-good preservation

Live external sources are inherently failure-prone.

They can:

- time out;
- return malformed responses;
- change format;
- rate-limit requests;
- remove content; or
- become temporarily unreachable.

The architecture distinguishes:

- failure to produce a new valid artifact; from
- invalidity of the currently published artifact.

Those are not the same condition.

Where the relevant writer supports last-good preservation, a failed refresh should not automatically destroy a previously valid public artifact.

Freshness, warnings, and source-health state can expose the operational problem separately.

## Derived rebuilds

An upstream change can require several dependent artifacts to be rebuilt.

The intended dependency direction is:

    Accepted upstream evidence
            |
            v
    Dependent derived artifacts
            |
            v
    Publication manifest

The manifest should be constructed after the artifacts it describes.

If an upstream file changes but the manifest still describes its earlier bytes, publication parity is broken even if the new artifact itself is structurally valid.

## Publication parity

Publication integrity requires agreement between the manifest and the public artifacts.

Relevant parity checks can include:

- expected file presence;
- artifact hashes;
- schema information;
- validation state;
- related-file identity;
- warnings; and
- frontend expectations.

A workflow should not be treated as fully successful merely because a collector produced JSON.

The resulting publication surface must remain internally coherent.

## Source-health architecture

Media collection maintains persistent route-health state.

`source_health.json` describes the collection system rather than the political race.

The source-health subsystem distinguishes route states such as:

- healthy;
- healthy with zero accepted yield;
- transient failure;
- repeated failure;
- not due;
- never attempted;
- disabled; and
- removed.

This persistent state means each scheduled run does not have to treat route behavior as if no prior history existed.

Source-health summaries can also feed the publication manifest and Source Network interface.

## HTTP collection boundary

External HTTP systems are treated as unreliable boundaries.

Collection infrastructure can include controls such as:

- request timeouts;
- retries;
- backoff;
- handling of retry instructions;
- compressed-response handling;
- response-size limits;
- conditional or not-modified responses; and
- explicit transient-failure handling.

These controls belong near the network boundary rather than being inconsistently recreated in downstream analytical builders.

## Deterministic identity

FR27 uses deterministic identity where stable public entities or observations must survive repeated builds.

Examples include:

- poll event IDs;
- poll scenario keys;
- campaign-event IDs;
- fact-check review IDs;
- Recent Changes IDs; and
- publication hashes.

The underlying identity inputs differ by domain.

The common architectural principle is that rerunning the same logical evidence should not create a new identity merely because the pipeline executed again.

## Candidate identity architecture

Candidate identity is centralized in `candidate_candidacy_status.json`.

Downstream systems consume shared projections from that authority rather than defining separate candidate universes.

This reduces several kinds of drift:

- inconsistent candidate spelling or identity;
- duplicate status logic;
- workspace-specific candidate membership;
- status inferred from polling prominence;
- status inferred from media prominence; and
- competing definitions of the active field.

Historical poll evidence can still contain candidates outside the current active monitoring projection because candidate status and polling evidence answer different questions.

## Validation classes

FR27 distinguishes several types of validation because different kinds of facts require different testing strategies.

### Frozen historical evidence

Historical migrations, fixed source snapshots, and known past evidence can support exact fixtures and exact-byte regression tests.

These inputs should remain stable unless the historical record itself is intentionally corrected.

### Semantic and business-rule validation

Research and business rules should use focused synthetic fixtures where possible.

A semantic test should demonstrate the rule it is designed to protect rather than accidentally depending on the current number of candidates, articles, poll events, or sources.

### Dynamic current-production validation

Current production data changes continuously.

It should normally be validated through structural and relational invariants rather than frozen snapshots.

Examples include:

- identifiers are unique;
- candidate projections agree;
- required dates are contiguous;
- shares agree with denominators;
- timestamps satisfy their contracts;
- related files reconcile;
- status values belong to allowed sets; and
- manifest hashes agree with current artifact bytes.

Current production counts should not become permanent expected values without a genuine historical reason.

### Workflow-safety validation

Some assertions protect the publication mechanism rather than the political semantics.

Examples include:

- writer concurrency;
- temporary-build behavior;
- validation-before-promotion;
- exact writer scope;
- derived rebuild ordering;
- manifest generation; and
- publication parity.

These tests protect the safety of production changes.

## Test suite

The repository contains a broad automated test suite covering data contracts, builders, production behavior, and frontend integration.

Tests are organized around the specific component or invariant they protect rather than around one monolithic application test.

This makes it possible to distinguish:

- source/parser failures;
- semantic-rule regressions;
- publication-integrity failures;
- frontend-contract regressions; and
- workflow-safety failures.

## Repository validation workflow

`.github/workflows/validate-dashboard.yml` provides repository-level validation for pull requests and manual runs.

It executes a focused integration surface across key dashboard and publication contracts.

This workflow complements the larger test suite.

It should be understood as an integration gate rather than the only location in which component behavior is tested.

## Failure model

The architecture favors **fail-closed** behavior.

A pipeline should prefer a visible missing, unresolved, unavailable, stale, or failed state over silently producing an apparently complete but unsupported result.

Potential failure boundaries include:

- source retrieval;
- parsing;
- candidate reconciliation;
- poll reconciliation;
- topic classification;
- schema validation;
- derived rebuilds;
- manifest construction;
- writer staging; and
- publication.

A failure at one boundary should not be hidden by later presentation code.

## Static deployment

The dashboard is currently served through GitHub Pages.

Because the public application is static, deployed state primarily consists of:

- frontend assets;
- published data artifacts; and
- the repository state from which the site is served.

There is no separate private production database required for normal dashboard reads.

This makes repository state unusually important: the repository is both implementation history and part of the public publication mechanism.

The project is expected to migrate its production identity to `france2027.app`; that domain transition does not require changing the fundamental static-publication model.

## Repository as an audit surface

A substantial part of FR27 is intentionally inspectable.

A researcher or developer can examine:

- source configuration;
- public data artifacts;
- deterministic builders;
- executable contracts;
- tests and fixtures;
- workflow definitions;
- publication hashes;
- source-health state; and
- frontend code.

Inspectability does not mean that third-party material acquires the same reuse rights as FR27-created code, structure, documentation, or other original material.

Provenance and rights remain separate concerns.

## Architecture boundaries

This document describes system structure.

It does not define:

- the legal rights governing reuse;
- the political meaning of a signal;
- whether an external claim is true;
- the substantive importance of a candidate or issue; or
- the complete historical rationale for every implementation decision.

Those questions belong respectively to the licensing documents, methodology, underlying sources, analytical interpretation, and repository history.

## Change discipline

Architecture changes should preserve existing semantic and publication contracts unless the purpose of the change is explicitly to revise one of those contracts.

A new feature should not automatically create:

- a new source pipeline;
- a second candidate authority;
- a parallel classification system;
- a new public schema;
- another production writer; or
- another derived artifact.

Where an existing contract, builder, or publication lane can be safely extended, reuse is preferable to unnecessary parallel infrastructure.

Changes to current production should be tested according to the type of invariant they modify rather than by broadly snapshotting volatile output.

## Related documentation

- [`PRODUCT_GUIDE.md`](PRODUCT_GUIDE.md) — public product behavior.
- [`METHODOLOGY.md`](METHODOLOGY.md) — research and measurement semantics.
- [`DATA_AND_PROVENANCE.md`](DATA_AND_PROVENANCE.md) — datasets, evidence sources, provenance, and freshness.
- [`OPERATIONS.md`](OPERATIONS.md) — production workflow and incident procedures.
- [`../CONTRACT.md`](../CONTRACT.md) — non-negotiable repository and data invariants.
- [`../README.md`](../README.md) — project overview.