# France 2027 Signal Lab — Data and Provenance

**France 2027 Signal Lab (FR27)** publishes a set of source-linked and derived data artifacts used by the public dashboard.

This document explains the public data model from a provenance perspective:

- which datasets form the principal publication surface;
- which evidence classes feed them;
- what provenance FR27 preserves;
- how freshness and timestamps should be interpreted;
- how source health affects media-derived evidence; and
- where the boundary lies between third-party source material and FR27-created structure.

It is not a licence document.

For reuse terms, see the repository licensing files. For measurement semantics, see [`METHODOLOGY.md`](METHODOLOGY.md).

## Provenance principle

FR27 is designed so that a derived signal does not erase the evidence chain from which it was produced.

Depending on the data class, that chain can include:

1. an external source or public record;
2. source-specific acquisition or collection;
3. normalization and validation;
4. candidate, event, poll, topic, or claim association;
5. a derived public artifact;
6. publication validation; and
7. the frontend representation.

Not every source supplies the same metadata.

FR27 therefore preserves source-specific provenance rather than forcing all evidence into a falsely uniform model.

## Public publication manifest

`publication_manifest.json` is the inventory of the principal public data lanes expected by the product.

Its role is operational and evidentiary.

For a lane, the manifest can record fields such as:

- artifact filename;
- availability;
- validation state;
- SHA-256 hash;
- schema version;
- data-as-of value;
- timestamp status;
- generation time;
- warnings;
- record counts; and
- references to related artifacts.

The manifest also carries a snapshot identity for the publication state as a whole.

The presence of an artifact in the manifest does not mean that every lane has identical semantics, update frequency, or timestamp precision.

### Integrity versus source credibility

A valid manifest entry means that the published artifact satisfies the checks represented by the FR27 publication process.

It does **not** mean that FR27 guarantees the truth of every statement contained in an external source.

These are different questions:

- **publication integrity** — did FR27 produce and validate the expected artifact?
- **source provenance** — where did the underlying evidence come from?
- **source credibility** — how should the underlying source itself be evaluated?

The manifest primarily addresses the first question while retaining metadata relevant to the second.

## Principal publication lanes

The current publication architecture contains the following principal lanes.

| Lane | Primary artifact | Role |
| --- | --- | --- |
| Campaign events | `campaign_events.json` | Structured campaign events, institutional milestones, event evidence, status, and provenance |
| Candidacy status | `candidate_candidacy_status.json` | Canonical candidate identities, candidacy status, display tier, and source provenance |
| Candidate agenda history | `candidate_agenda_history.json` | Persistent candidate-topic history derived from accepted election coverage |
| Candidate attention | `candidate_attention.json` | French Wikipedia article-reading attention for the active monitoring field |
| Candidate signals | `candidate_signals.json` | Candidate-level synthesis used by the Candidates workspace |
| Candidate visibility history | `candidate_visibility_history.json` | Persistent candidate coverage shares and lane denominators |
| Claims | `claims_under_scrutiny.json` | Professional fact-check reviews associated with monitored candidates |
| News | `news_wire.json` | Accepted election and campaign coverage plus derived coverage structures |
| Polls | `polls.json` | First-round published poll events |
| Recent changes | `recent_changes.json` | Derived ledger of recent material election changes |
| Runoff | `second_round_polls.json` | Published second-round polling hypotheses and results |
| Source health | `source_health.json` | Persistent operational state of media collection routes |

The exact manifest is authoritative for the current publication state.

Counts, hashes, timestamps, warnings, and source-network totals are dynamic and should be read from the live manifest rather than copied from this document.

## Candidacy status

`candidate_candidacy_status.json` is the canonical candidate identity and status registry.

It separates stable identity from current monitoring status.

Provenance associated with the registry can include:

- canonical source URL;
- source revision identifier;
- source revision timestamp;
- status-as-of date;
- candidate identity;
- candidacy status;
- display tier; and
- historical or retained identity information.

The current registry contract records provenance from a canonical French Wikipedia candidacy page and revision.

That source is evidence for the registry state; it is not transformed into a prediction about eventual ballot qualification.

Downstream datasets should consume the canonical registry or its shared active projection rather than independently inventing candidate membership.

## First-round polling

The principal first-round publication artifact is `polls.json`.

Polling provenance can include:

- pollster;
- source URL;
- fieldwork start and end dates;
- round;
- hypothesis;
- candidate configuration;
- reported candidate values;
- deterministic event identity;
- deterministic scenario identity; and
- completeness state.

The source poll remains the evidentiary basis of the observation.

FR27-created identifiers, normalized candidate names, scenario keys, validation states, and comparability relationships are derived metadata used to preserve structure and prevent incompatible observations from being merged.

### Commission notice provenance

Polling publication is supported by `commission_notice_registry.json`.

This registry records relevant Commission des sondages notice evidence and its relationship to published FR27 poll events.

A notice can be:

- directly parsed into an event;
- deterministically reconciled with one event; or
- unresolved.

Unresolved relevant notice coverage is surfaced as a publication warning rather than silently discarded.

The Commission registry is therefore provenance and coverage-control infrastructure, not an additional polling average or parallel forecast.

## Second-round polling

`second_round_polls.json` contains published second-round polling hypotheses.

Its provenance preserves the identity of the source polling evidence and the tested candidate pairing.

A related artifact, `closest_tested_runoff.json`, can provide a derived view over tested runoff evidence.

The distinction matters:

- the poll is third-party evidence;
- the pairing identity and comparable-history structure are FR27-derived organization;
- an untested hypothetical pairing is not converted into invented polling evidence.

## Election news and media coverage

`news_wire.json` is the principal public media artifact.

Its upstream collection system uses configured public routes including forms such as:

- direct publisher feeds;
- shared discovery routes; and
- publisher-site routes.

Publisher policy and route configuration determine which sources are eligible for collection.

Collection alone is not sufficient for inclusion.

Items pass through election-scope, source-policy, normalization, deduplication, candidate-matching, and classification logic before they contribute to relevant public outputs.

### Source-level provenance

Depending on the route and item, media provenance can include:

- publisher;
- feed or route;
- original or canonical URL;
- headline;
- available summary;
- publication time;
- first-seen time;
- last-seen time;
- candidate matches;
- relevance reason; and
- relevance terms.

FR27 may derive further structures such as candidate visibility, campaign topics, policy topics, publisher distribution, or story grouping from accepted records.

Those structures are FR27-created metadata over the source corpus.

### Third-party article boundary

A source-linked news record is not a republication of the complete underlying article.

FR27 can contain limited identifying and provenance material associated with an external source, such as a headline, publisher identity, source URL, publication metadata, or short source-derived text used by the evidence system.

The publisher's original page remains the place to inspect the underlying article.

The presence of third-party material in an FR27 dataset or interface does not convert that material into FR27-created content or determine its reuse rights. Rights treatment is documented separately in the repository licensing and third-party-notice files.

## Candidate visibility history

`candidate_visibility_history.json` persists candidate media visibility over complete UTC days.

Its provenance traces back to candidate-linked records in `news_wire.json`.

The artifact separately preserves lane denominators and candidate observations.

Relevant fields include concepts such as:

- calendar date;
- lane record count;
- lane publisher count;
- candidate record count;
- candidate publisher count; and
- candidate share of lane records.

The denominator is essential provenance for interpreting a share.

A candidate share without the corresponding corpus volume would conceal whether the underlying measurement was based on a broad or narrow observation set.

If the lane denominator is zero, the share is `null`.

It is not represented as a measured zero share.

## Candidate agenda history

`candidate_agenda_history.json` is a derived historical artifact.

Its primary upstream evidence is accepted relevant election coverage from `news_wire.json`.

It uses:

- validated candidate associations;
- canonical policy-topic classification;
- canonical campaign-topic classification; and
- stable candidate identities.

The resulting history is therefore not an independent source.

It is a reproducible transformation of accepted source-linked coverage.

A user evaluating a candidate-topic signal should ultimately be able to return toward the underlying coverage evidence rather than treating the derived count as primary evidence.

## Candidate attention

`candidate_attention.json` uses French Wikipedia and Wikimedia pageview data.

Its provenance can include:

- canonical candidate identity;
- associated French Wikipedia article;
- Wikimedia pageview observations;
- measurement dates;
- availability state; and
- generated comparison metrics.

A candidate can be present in the active monitoring field while the attention metric is unavailable.

That distinction is preserved explicitly.

The absence of a qualifying personal article does not become an artificial zero-attention observation.

## Candidate signals

`candidate_signals.json` is a derived candidate-level publication artifact used by the Candidates workspace.

It brings together already-defined evidence classes and candidate-level structures.

It should therefore be understood as a **synthesis artifact**, not as an independent primary source.

Its provenance depends on the upstream datasets represented in the candidate view.

Those can include evidence derived from:

- candidacy status;
- polling;
- candidate attention;
- candidate visibility;
- agenda history;
- claims under scrutiny; and
- related source-linked candidate evidence.

The synthesis layer does not change the methodological meaning of those underlying metrics.

For example, Wikipedia attention remains article-reading attention after it appears inside a candidate dossier.

## Claims Under Scrutiny

`claims_under_scrutiny.json` publishes professional fact-check evidence associated with monitored candidates.

Its collection process uses the shared active candidate projection from `candidate_candidacy_status.json`.

The source system queries French-language fact-check material and restricts accepted reviews according to the project's approved publisher policy.

Provenance can include:

- review URL;
- publisher;
- review date;
- claim text;
- claimant;
- publisher-supplied rating;
- candidate identity; and
- candidate relationship.

Candidate relationship is recorded as **by** or **about** when deterministically supported.

Ambiguous relationships are not silently converted into a public association.

The fact-check publisher's rating remains the publisher's judgment.

FR27 does not replace it with an internal truth score.

## Campaign events

`campaign_events.json` contains structured event and milestone evidence.

Campaign-event provenance is intentionally richer than a simple calendar entry.

It can retain:

- source URL;
- source class;
- evidence type;
- candidate or participants;
- event type;
- date;
- exact time when known;
- time precision;
- location;
- organizer;
- event status;
- evidence status; and
- schedule-update history.

### Event source classes

The event contract recognizes defined source classes including:

- official structured sources;
- official unstructured sources;
- candidate first-party sources;
- party first-party sources;
- organizer first-party sources; and
- reliable media.

Source class is provenance.

It does not disappear merely because several source classes can establish the same event.

### Event evidence classes

The event model distinguishes evidence such as:

- explicit schedule evidence;
- explicit status updates; and
- official-rule derivation.

This allows the public artifact to distinguish a directly scheduled campaign event from an institutional milestone derived from an official rule.

## Recent Changes

`recent_changes.json` is a derived ledger.

It does not have one independent upstream source.

Instead, it draws qualifying changes from existing FR27 publication artifacts and accepted election coverage.

Its provenance can therefore point back toward evidence classes such as:

- campaign developments;
- first-round polling;
- runoff polling;
- fact-check reviews; and
- material legal or procedural developments.

The ledger retains trusted change timing separately from detection and generation timing.

This is important provenance: a change does not become politically recent merely because the system rebuilt the ledger recently.

## Source health

`source_health.json` describes the state of media collection routes.

It is operational metadata rather than political evidence.

A route can have states including:

- healthy;
- healthy with zero accepted yield;
- transient failure;
- repeated failure;
- not due;
- never attempted;
- disabled; and
- removed.

The distinction between **healthy zero yield** and **failure** is important.

A successfully contacted source that happens to produce no accepted election material is not equivalent to a broken source.

Source-health history can retain recent attempt and outcome information so that route behavior remains inspectable across runs.

## Source Network

The dashboard's Source Network surface is derived from configured source policy, media routes, source-health state, and accepted corpus activity.

Metrics can describe concepts such as:

- approved publisher domains;
- configured media publishers;
- configured routes or feeds;
- routes due in a particular run;
- successful due routes;
- publishers contributing within a retained period; and
- publishers represented in accepted election coverage.

These totals are dynamic.

They describe the FR27 collection network at a particular publication state and should not be hard-coded into methodological documentation.

They also should not be interpreted as a claim that FR27 covers every French publisher.

## Supporting registries and inputs

Not every repository JSON file is an independent public measurement.

The repository also contains supporting material such as:

- source configuration;
- publisher policy;
- discovery-query configuration;
- manual exclusions;
- Commission notice reconciliation data;
- candidate identity and provenance information;
- event registries or source definitions;
- migration registries; and
- other controlled inputs needed to construct public artifacts.

These files can serve several roles:

- canonical authority;
- provenance registry;
- reviewed configuration;
- migration record;
- manual exception;
- operational state; or
- deterministic build input.

A supporting file should not be interpreted as a standalone public metric merely because it is version-controlled.

## Primary, derived, and operational data

A useful way to understand FR27 artifacts is to separate three roles.

### Source-linked evidence

These artifacts retain or organize observations grounded directly in external evidence.

Examples include published poll events, accepted source-linked news records, professional fact-check reviews, and campaign-event evidence.

FR27 still performs normalization and validation, but the underlying observation originates outside FR27.

### Derived analytical data

These artifacts are calculated from other accepted FR27 evidence.

Examples include:

- candidate visibility history;
- candidate agenda history;
- candidate signal synthesis;
- coverage summaries; and
- Recent Changes.

Their provenance must therefore include the upstream FR27 artifact or evidence class from which they were generated.

### Operational data

Operational artifacts describe whether the system itself is functioning and what has been published.

Examples include:

- `source_health.json`; and
- `publication_manifest.json`.

They are essential for transparency but should not be interpreted as political measurements.

## Timestamps and freshness

FR27 uses several kinds of time metadata.

They answer different questions.

### Source or evidence date

This is the date attached to the underlying evidence.

Examples include:

- poll fieldwork dates;
- article publication time;
- fact-check review date;
- campaign-event date; and
- official ruling or decision date.

### `data_as_of`

`data_as_of` describes the newest or controlling evidence date represented by a publication lane according to that lane's contract.

Its exact meaning can vary by dataset.

It should not automatically be interpreted as the time the file was generated.

### `generated_at`

`generated_at` records when a particular artifact was constructed.

A newly generated file can legitimately contain older underlying evidence.

### `published_at`

Where used, `published_at` identifies publication of a manifest or snapshot state.

It is publication metadata, not the event date of every observation contained in that snapshot.

### `last_success_at`

Where used, `last_success_at` records successful completion of the relevant derived publication process.

Again, this is operational time rather than political-event time.

### Timestamp status

A manifest lane can explicitly state whether the relevant data-as-of timestamp is known according to the manifest's current rules.

A lane whose timestamp status is unknown can still be available and valid.

Unknown timestamp status should not be silently replaced by a guessed date.

## Hashes and reproducibility

The publication manifest records SHA-256 hashes for principal artifacts and, where relevant, related files.

Hashes serve several purposes:

- detect unexpected content change;
- connect a manifest snapshot with exact artifact bytes;
- support publication-parity checks;
- make generated state more reproducible; and
- distinguish content identity from filename identity.

A hash does not make external evidence correct.

It establishes the identity of the artifact that FR27 actually published.

Some datasets can also expose semantic hashes where the contract distinguishes semantic content from other serialized metadata.

## Missing, unavailable, unresolved, and stale evidence

Provenance includes absence states.

FR27 does not treat all non-values alike.

Depending on the data class, an artifact can distinguish:

- a valid zero;
- missing evidence;
- unavailable measurement;
- partial evidence;
- unresolved reconciliation;
- stale evidence;
- past but unconfirmed evidence;
- not-tested polling hypotheses;
- source failure; and
- healthy source routes with zero accepted yield.

These distinctions are part of the public data model.

They should survive into derived data rather than being flattened into a generic zero or blank value.

## Last-good preservation

Some production lanes depend on live external sources that can fail temporarily.

A failed retrieval should not automatically replace a previously valid public artifact with broken or incomplete output.

FR27 production workflows therefore use validation and promotion boundaries designed to preserve last-good published state when a candidate replacement cannot satisfy its contract.

This creates another provenance distinction:

- **freshness** asks how recent the evidence is;
- **validity** asks whether the artifact satisfies its contract; and
- **availability** asks whether a usable published artifact exists.

Those states are related but not identical.

## Third-party and FR27-created material

FR27 datasets and interfaces can contain a mixture of:

- independently obtainable facts;
- third-party source identifiers and metadata;
- links to external material;
- limited source-derived text used for evidence identification;
- publisher, pollster, source, or other third-party identification marks and icons where present;
- FR27 normalization;
- FR27 classifications;
- FR27 associations;
- FR27 deterministic identifiers;
- FR27 provenance metadata;
- FR27 derived statistics; and
- FR27-created documentation and interface structure.

The presence of third-party material inside an FR27 artifact or interface does not transfer ownership of that material to FR27.

Likewise, FR27 does not claim exclusive rights over independently obtainable facts merely because it has collected, normalized, linked, classified, or displayed them.

Describing material here as third-party material does not itself determine the licence or legal basis governing its use. The repository licensing files and `THIRD_PARTY_NOTICES.md` document the applicable reuse framework and third-party boundaries.

## Provenance does not imply endorsement

A source appears in FR27 because it satisfies a defined evidentiary or collection role.

That does not mean FR27 endorses:

- the source organization;
- every claim in the source;
- the candidate or party referenced;
- a publisher's political framing;
- a fact-check subject;
- or the conclusions a user may draw from the evidence.

Source attribution exists to make evidence inspectable, not to confer endorsement.

## Dynamic data and documentation

FR27 is an active monitoring product.

The following are expected to change over time:

- artifact hashes;
- record counts;
- candidate counts and status;
- publication timestamps;
- source-network totals;
- source-health state;
- unresolved warnings;
- poll coverage;
- event inventory; and
- media-corpus composition.

This document therefore describes **contracts and meanings**, not a frozen numerical snapshot.

For current values, inspect the published artifacts and `publication_manifest.json`.

## Related documentation

- [`PRODUCT_GUIDE.md`](PRODUCT_GUIDE.md) — how to read the public dashboard.
- [`METHODOLOGY.md`](METHODOLOGY.md) — measurement semantics and limitations.
- [`ARCHITECTURE.md`](ARCHITECTURE.md) — builders, contracts, workflows, frontend, and publication architecture.
- [`OPERATIONS.md`](OPERATIONS.md) — production validation and publishing.
- [`../CONTRACT.md`](../CONTRACT.md) — non-negotiable data and repository invariants.
- [`../README.md`](../README.md) — project overview.