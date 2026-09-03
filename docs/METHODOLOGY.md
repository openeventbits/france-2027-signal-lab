# France 2027 Signal Lab — Methodology

**France 2027 Signal Lab (FR27)** is a descriptive election-monitoring and research project for the 2027 French presidential election.

This document explains what FR27 measures, how its principal evidence classes are constructed, and how those measures should be interpreted.

It is intended to document public meaning rather than every implementation detail.

For non-negotiable repository and data invariants, see [`../CONTRACT.md`](../CONTRACT.md).

## Methodological position

FR27 does not attempt to estimate the probability of an election outcome.

It keeps different forms of political evidence separate so that published polling, media visibility, candidate attention, campaign activity, policy-topic evidence, fact-checking, and other signals can be inspected without being collapsed into a proprietary composite score.

The central methodological principles are:

- preserve source provenance;
- distinguish observation from inference;
- retain missing and unresolved states;
- compare only sufficiently compatible evidence;
- avoid converting data absence into zero;
- distinguish political-event time from system-processing time;
- expose the corpus within which a metric was measured; and
- prefer under-inclusion to a misleading conclusion when evidence is ambiguous.

## Descriptive, not predictive

FR27 does not publish:

- polling averages;
- election forecasts;
- win probabilities;
- voting recommendations;
- ideological scores;
- sentiment scores as proxies for voting preference;
- synthetic candidate rankings; or
- a hidden composite measure of political momentum.

A user may inspect several signals together, but FR27 does not mathematically combine those signals into an electoral prediction.

## Evidence and provenance

A public metric should remain traceable, where practicable, to the evidence from which it was derived.

Depending on the dataset, provenance can include:

- source URL;
- publisher or source organization;
- publication date;
- fieldwork dates;
- event date;
- review date;
- candidate associations;
- topic associations;
- source revision information;
- first-seen or detection time;
- validation state; and
- generation time.

These timestamps are not interchangeable.

For example, the time FR27 first detects an article is not automatically the date on which the political development described by that article occurred.

## Candidate universe

`candidate_candidacy_status.json` is the canonical authority for candidate identity and candidacy status within FR27.

Candidate identity is separated from current monitoring status so that historical and inactive identities can remain stable even after a person leaves the active field.

The registry supports statuses including:

- `declared`;
- `party_selected`;
- `primary_contender`;
- `active_potential`;
- `conditional`;
- `ruled_out`;
- `withdrawn`; and
- `historical_poll_only`.

Those statuses map to public display tiers:

- **main**;
- **secondary**; or
- **hidden**.

The active monitoring field is the shared projection of candidates who are currently present in the source registry and whose display tier is `main` or `secondary`.

This active field is used by downstream systems such as candidate attention, claims collection, and other current-monitoring processes.

### Candidate status is not polling evidence

Candidate-universe membership does not determine whether polling evidence is accepted.

If a poll source cleanly reports a candidate, that result remains part of the poll event even if the candidate is not part of the current active monitoring field.

Candidate status and poll evidence therefore remain separate evidence classes.

### Candidate discovery

Candidate discovery may use multiple verified source classes.

First-party or authoritative evidence is preferred where available, while other attributable sources can provide fallback or corroboration.

Discovery does not automatically change downstream semantics.

Candidate identity, conservative status transitions, provenance, retained last-good records, and fail-closed handling of ambiguity remain required.

## First-round polling

FR27 treats a poll as an **event**, not as a collection of disconnected candidate scores.

A first-round poll event contains the pollster, fieldwork period, round, hypothesis, source URL, and the complete set of candidate results reported for that scenario.

### Deterministic identity

Each first-round event receives a deterministic identifier derived from stable event properties.

Rerunning ingestion against the same underlying event should therefore reproduce the same identity rather than create a duplicate observation.

Scenario identity is also deterministic.

This allows FR27 to determine whether two published observations represent the same candidate configuration.

### Scenario comparability

Two first-round poll events are considered comparable only when their scenario identity is compatible.

A change in candidate configuration creates a different scenario.

FR27 does not silently join two scenarios merely because:

- they were published by the same pollster;
- they were conducted close together in time; or
- they concern the same election.

When comparability is uncertain, FR27 treats the events as incompatible.

### Complete and partial scenarios

FR27 validates the total of the candidate scores reported by the source.

A scenario whose reported candidate results sum to approximately the complete published vote distribution is marked complete.

A clean but incomplete source scenario can remain published as **partial** evidence.

The missing share is not redistributed among the reported candidates.

FR27 does not normalize partial evidence into an invented 100-percent result.

### Missing polling values

Missing or unparseable values are not converted into zero.

Citation or footnote markers can be removed when they are separable from an otherwise unambiguous numeric value, but a value that cannot be parsed cleanly is omitted rather than guessed.

### No polling average

FR27 does not combine separate poll events into a polling average.

Where a trend is displayed, it is a history of sufficiently comparable published poll events.

Each poll remains a distinct observation.

## Commission des sondages notice coverage

FR27 separately tracks relevant notices from the French Commission des sondages.

A relevant notice can have one of three coverage states:

- **parsed** — a published poll event directly carries the official notice provenance;
- **reconciled** — an otherwise unparsed notice has one deterministic published-wave match; or
- **unresolved** — neither condition is satisfied or the match remains ambiguous.

Only unresolved relevant notices create poll-coverage warnings.

Reconciliation is conservative and depends on exact compatible evidence such as normalized pollster identity, fieldwork dates, and round.

Optional metadata may disambiguate otherwise exact candidates for reconciliation, but it does not create a match where the core evidence is incompatible.

## Second-round polling

Second-round polling is presented as **tested hypothetical evidence**.

It is not a forecast of which candidates will qualify for the second round.

FR27 does not assign a result to a pairing that has not actually been tested by a published poll.

Different candidate pairings remain different hypotheses.

Where the same matchup has been tested repeatedly under sufficiently comparable conditions, the dashboard can display a history of that matchup.

A latest margin is still a poll result, not a win probability.

## Election-news corpus

Media-derived FR27 metrics are based on a defined source and collection system.

The corpus is constructed from configured direct publisher routes, discovery routes, publisher-site routes, and associated source policy.

It should therefore be interpreted as the **accepted FR27 election-news corpus**, not as a census of all French political journalism.

### Election relevance

Collection alone does not make an item election evidence.

Items must satisfy relevance and scope rules before appearing in election-oriented outputs.

The scope logic seeks explicit evidence that a presidential story concerns the French 2027 race.

Generic presidential language without a French-election anchor is rejected rather than automatically admitted.

French-election anchors can include evidence such as:

- explicit reference to the French 2027 presidential election;
- recognized monitored candidates;
- French political formations;
- France-specific presidential-race terminology; or
- other deterministic French-election context.

### Candidate matching

Candidate associations are based on validated candidate identities and approved text matching.

Candidate matching is performed against supported textual locations such as the headline and summary.

Compact candidate labels and aliases are normalized only where the mapping has been reviewed as sufficiently unambiguous.

A surname or ambiguous token is not automatically accepted as a candidate association merely because it resembles a known political name.

## Candidate media visibility

Candidate visibility measures **share of candidate-linked records within a defined coverage lane**.

It does not measure:

- sentiment;
- approval;
- electoral support; or
- voting intention.

The principal visibility scopes are election and campaign coverage.

General visibility is retained as a separate secondary scope rather than being silently mixed into the election/campaign measure.

### Visibility history

The persistent visibility history uses exactly 29 complete UTC calendar days and excludes the current UTC day.

For each day, FR27 records:

- the number of accepted lane records;
- the number of publishers contributing to that lane;
- the number of candidate-linked records;
- the candidate's share of lane records; and
- the number of publishers in which the candidate appears.

If a lane contains no records for a day, the candidate share is `null`, not zero.

### Period comparison

Current and prior media periods are compared only when the corpus is sufficiently comparable.

The comparison contract considers structural evidence including:

- minimum record volume;
- minimum publisher count;
- publishers common to both periods;
- publisher overlap; and
- the ratio of record volumes between periods.

If those conditions are not satisfied, the comparison should not be represented as a normal comparable coverage shift.

## Campaign Agenda

Campaign Agenda describes the campaign-process and political-strategy themes observed in accepted election coverage.

The current canonical campaign taxonomy includes:

- **Legal cases & eligibility**;
- **Primaries & party strategy**;
- **Candidacies & endorsements**;
- **Rules, calendar & campaign mechanics**;
- **Positioning & political image**; and
- **Polling & race narratives**.

Campaign classification uses deterministic topic semantics defined by the production pipeline.

The campaign-agenda classifier assigns at most one canonical campaign topic when its deterministic rules match; an item can also remain unclassified. It does not use a generative interpretation of article meaning.

### What Campaign Agenda measures

Campaign Agenda measures observed topic occurrence in the accepted source corpus.

It does not measure:

- the private strategy of a candidate;
- candidate importance;
- voter concern;
- public support; or
- the normative importance of a topic.

Changes in campaign-topic counts therefore describe changes inside the measured coverage corpus.

## Policy Issues

Policy Issues tracks substantive policy-topic evidence in accepted election coverage.

Unlike the campaign taxonomy, policy classification can be multi-label when an item contains evidence for more than one canonical policy topic.

The policy taxonomy and subtopics are explicitly defined in the production code.

Examples of canonical policy families include areas such as:

- economy and public finances;
- work, purchasing power and pensions;
- immigration, identity and secularism;
- security and justice; and
- other substantive public-policy domains represented in the locked taxonomy.

The complete canonical taxonomy in the production pipeline is authoritative.

### Candidate-policy associations

A candidate-topic association means that accepted source evidence links a monitored candidate with a policy topic.

It does not by itself establish:

- endorsement of that policy;
- ownership of the issue;
- ideological position;
- priority assigned by the candidate; or
- voter association with that candidate.

## Candidate Agenda History

Candidate Agenda History creates a persistent time series from accepted election-news evidence.

Its source is the relevant-news publication corpus and validated candidate associations.

It retains daily policy and campaign-topic counts for each canonical candidate identity.

The measurement is descriptive and unweighted.

Each qualifying candidate-topic association contributes to the relevant count; FR27 does not apply a hidden importance weight based on publisher, candidate, or topic.

The persistent candidate profile uses policy evidence when at least three policy topics have non-zero cumulative counts; otherwise it falls back to the campaign-topic profile.

This rule is structural and should not be interpreted as a judgment that one kind of agenda is more important than the other.

## Candidate Attention

Candidate Attention uses French Wikipedia pageview data.

Its public interpretation is:

> French Wikipedia pageviews measure article-reading attention.

The source metric uses Wikimedia pageviews for the canonical French Wikipedia article associated with a monitored candidate.

The series uses daily observations and currently retains a 90-day measurement window.

### What Candidate Attention does not measure

Wikipedia pageviews are not:

- unique individuals;
- sentiment;
- approval;
- electoral support; or
- voting intention.

A rise can result from many causes, including campaign developments, controversy, media coverage, biographical curiosity, or unrelated public attention.

### Weekly comparison

The weekly comparison uses the latest seven complete UTC days against the preceding seven complete UTC days.

Where the previous period is zero, a percentage change is not invented.

### Article availability

A candidate without a qualifying personal French Wikipedia article is represented as unavailable for that measurement rather than being assigned zero pageviews.

Redirect behavior can also affect attribution of traffic to the canonical article, which is a limitation of the source metric.

## Claims Under Scrutiny

Claims Under Scrutiny collects professional fact-check reviews associated with the active candidate field.

The collector uses the canonical candidate registry to determine which candidates are queried.

Candidate-universe membership is therefore controlled by the shared registry rather than by the claims dataset itself.

### Review corpus

The public claims dataset uses a defined professional fact-check publisher policy and a rolling archive window.

The source system is queried for French-language fact-check evidence and then validated before publication.

The claims corpus should not be interpreted as a complete census of every fact-check published in France.

### Candidate relationships

FR27 distinguishes two candidate relationships:

- **by** — the monitored candidate is identified as the claimant; and
- **about** — the fact-check concerns the candidate but the candidate is not identified as the claimant.

Ambiguous relationships are not forced into one of those categories.

This distinction prevents a fact-check about a candidate from being incorrectly represented as a false or disputed statement made by that candidate.

### Ratings

FR27 preserves the rating supplied by the fact-check publisher.

It does not replace publisher judgments with an FR27 truth score.

## Campaign Events

Campaign Events is a structured evidence system for qualifying campaign activity and institutional election milestones.

The campaign event model separates:

- event identity;
- event type;
- participants;
- scheduled date or time;
- time precision;
- location;
- event status;
- evidence status;
- source provenance; and
- subsequent schedule changes.

### Event types

Qualifying campaign activity can include categories such as:

- rallies;
- public meetings;
- debates;
- candidate visits;
- campaign launches; and
- other significant campaign events.

The event system also supports defined institutional milestones connected to the presidential election calendar.

### Source classes

Campaign-event evidence can come from defined source classes such as:

- official structured sources;
- official unstructured sources;
- candidate first-party sources;
- party first-party sources;
- organizer first-party sources; and
- reliable media.

Source class is retained as part of provenance rather than discarded after extraction.

### Evidence types

Published event evidence distinguishes forms such as:

- explicit schedule evidence;
- explicit status updates; and
- official-rule derivation.

An event is not promoted merely because a plausible date can be inferred from weak or ambiguous material.

### Time precision

A known date and a known exact time are different evidence states.

If the source supports only a date, FR27 does not fabricate an hour.

Campaign-event datetimes use the `Europe/Paris` time zone and are validated against the applicable UTC offset.

### Event status

The structured event contract supports states including:

- scheduled;
- postponed;
- cancelled; and
- completed.

Evidence state is tracked separately from event status.

This allows the system to distinguish what is scheduled from how recently or confidently that schedule has been verified.

### Stable identity

Campaign events receive deterministic stable identifiers so that repeated collection of the same underlying event does not create a new public event merely because it was rediscovered.

## What Changed / Recent Changes

`recent_changes.json` is a derived ledger over existing FR27 public datasets and accepted election-news evidence.

It is not intended to duplicate the full news feed.

The current ledger uses a 14-day inclusive Paris-date window and retains every qualifying unique change in that period.

Allowed public categories include:

- campaign;
- polling;
- runoff;
- fact-check; and
- legal.

### Trusted change time

Each item separates several time concepts.

These can include:

- source publication time;
- official event date or time;
- fieldwork end;
- review publication;
- first-seen time;
- system detection time; and
- generation time.

Only a defined **trusted change time** controls public ordering and date grouping.

Detection and generation timestamps never become political-change dates merely because they are available.

### Trusted date kinds

Trusted change dates can derive from defined evidence classes such as:

- source publication;
- official event;
- first seen;
- fieldwork ended;
- review publication; and
- ruling or decision.

This prevents a later pipeline run from making an older political development appear newly occurred.

## Source health

Source-health data describes the collection system, not the political race.

A route can have states such as:

- healthy;
- healthy with zero accepted yield;
- transient failure;
- repeated failure;
- not due;
- never attempted;
- disabled; or
- removed.

These states help readers and operators understand the condition of the corpus.

They should not be interpreted as political signals.

For example, a reduction in coverage volume may reflect both genuine changes in publisher activity and changes in source availability. Source-health context therefore matters when interpreting media-derived metrics.

Detailed source and provenance architecture is documented in [`DATA_AND_PROVENANCE.md`](DATA_AND_PROVENANCE.md).

## Missing and zero

FR27 distinguishes several concepts that are often incorrectly collapsed:

- **zero** — a valid measured value of zero;
- **missing** — no usable value was supplied or observed;
- **unavailable** — the metric cannot be produced for the entity or source;
- **partial** — some valid evidence exists, but the source observation is incomplete;
- **unresolved** — relevant evidence exists but cannot be deterministically reconciled or classified; and
- **not tested** — the relevant polling hypothesis has not been observed in accepted evidence.

These states should not be substituted for one another.

## Time boundaries

Different FR27 datasets use time boundaries appropriate to their evidence source.

Examples include:

- UTC day boundaries for persistent media and Wikipedia series;
- `Europe/Paris` for campaign-event scheduling and Recent Changes date grouping;
- source fieldwork dates for polling; and
- publisher review dates for fact-check evidence.

The relevant dataset contract is authoritative when time semantics differ.

## Reading multiple signals

FR27 is designed to allow several evidence streams to be viewed together without implying that they measure the same latent quantity.

For example, the same candidate may simultaneously show:

- increasing Wikipedia attention;
- declining share of accepted election coverage;
- a new first-round poll test;
- new policy-topic associations; and
- additional scheduled campaign events.

Those are five separate observations.

FR27 does not convert them into a single score called momentum, viability, popularity, or electoral probability.

Any interpretation that combines them remains an analytical judgment by the reader rather than a hidden project model.

## Known limitations

FR27 inherits limitations from both its sources and its own defined corpus.

These include:

- external sources can become unavailable or change format;
- the configured media universe is not all French media;
- publisher output varies over time;
- automated relevance and topic classification can under-include valid material;
- candidate aliases can create ambiguity and are therefore treated conservatively;
- Wikipedia pageviews do not identify why an article was read;
- fact-check coverage depends on the monitored professional review corpus;
- polling hypotheses change as the candidate field develops;
- event schedules can change after publication;
- public-source data can contain delays or corrections; and
- new evidence can require a previously unresolved case to be reconciled later.

The methodological response to these limitations is generally to expose provenance, preserve explicit states, and fail closed rather than create an apparently complete but misleading dataset.

## Authority and change control

This document explains public methodology.

If this document, [`../CONTRACT.md`](../CONTRACT.md), and an executable production contract diverge, that divergence is a defect requiring review. Production behavior should not be reinterpreted as a methodological change merely because the current code implements it.

Methodological changes that alter the public meaning of a metric should be explicit and reviewable rather than silently introduced through presentation code.

## Related documentation

- [`PRODUCT_GUIDE.md`](PRODUCT_GUIDE.md) — how to read the dashboard.
- [`DATA_AND_PROVENANCE.md`](DATA_AND_PROVENANCE.md) — datasets, sources, provenance, freshness, and source boundaries.
- [`ARCHITECTURE.md`](ARCHITECTURE.md) — system architecture and publication design.
- [`OPERATIONS.md`](OPERATIONS.md) — production validation and publication.
- [`../CONTRACT.md`](../CONTRACT.md) — non-negotiable repository and data invariants.
- [`../README.md`](../README.md) — project overview.