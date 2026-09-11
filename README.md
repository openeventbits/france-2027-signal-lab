# France 2027 Signal Lab

**English** · [Français](README.fr.md)

**A source-linked election-monitoring terminal for France's 2027 presidential race.**

**France 2027 Signal Lab (FR27)** is an independent, bilingual, continuously updated election-monitoring system. It brings published polling, candidate activity, media coverage, campaign agenda signals, policy issues, campaign events, fact-checking, significant legal developments, and second-round polling into one inspectable interface.

FR27 is built around a practical question: **what changed in the race, and what evidence supports it?**

Rather than collapse different signals into a polling average, proprietary candidate score, forecast, probability of victory, or voting recommendation, FR27 preserves the structure, context, and provenance needed to inspect the evidence itself.

**Live product:** https://france2027.app/<br>
**English interface:** https://france2027.app/?lang=en<br>
**Repository:** https://github.com/openeventbits/france-2027-signal-lab

![Race at a Glance — France 2027 Signal Lab](docs/assets/readme-race-at-a-glance-en.jpg)

*Race at a Glance presents published first-round poll events individually, with their sources, fieldwork dates, tested candidate configurations, and comparison context.*

## Why FR27 exists

A presidential campaign produces evidence on different timelines and in different formats: poll releases, candidate announcements, campaign appearances, media coverage, policy debates, fact-checks, legal developments, schedule changes, and second-round hypotheses.

Those signals are easy to encounter separately and much harder to monitor together without losing context. FR27 turns that fragmented information environment into a structured system designed for repeat use.

A reader can use FR27 to see what changed since the last visit; determine whether poll observations are genuinely comparable; follow candidate visibility, attention, and scrutiny; inspect campaign and policy themes; see which publishers are shaping the measured media corpus; check upcoming events and schedule changes; review tested runoff evidence; and trace displayed signals back toward their source material.

## What FR27 monitors

| Surface | What it exposes |
| --- | --- |
| **What Changed** | A source-linked ledger of material developments across campaign activity, polling, runoff evidence, fact-checks, and significant legal or procedural changes. |
| **Race at a Glance** | Published first-round poll events with fieldwork dates, source links, complete candidate configurations, and configuration-aware comparison context. |
| **Media Pulse** | Candidate visibility, publishers, topics, activity, and coverage shifts inside the accepted FR27 election-coverage corpus. |
| **Candidates** | Candidate-level polling evidence, Wikipedia attention, media visibility, agenda signals, scrutiny, and source-linked dossiers. |
| **Campaign Agenda** | Campaign-process and political-strategy themes, their persistence and movement, and the evidence behind them. |
| **Policy Issues** | Substantive policy-topic activity, candidate associations, recent evidence, and issue movement within the monitored corpus. |
| **Campaign Events** | Upcoming events, structured event dossiers, source evidence, time precision, status, and schedule-change history. |
| **Runoff** | Published second-round polling, tested candidate pairings, observed margins, and comparable matchup history. |
| **Evidence tools** | Polling Evidence, Election Coverage Reader, Coverage Analysis, Signal Desk, and Source Network provide deeper inspection of evidence and collection state. |

The French and English interfaces use the same underlying publication state rather than separate analytical datasets.

## Candidate-level evidence

The **Candidates** workspace brings several independent evidence streams together around one political actor without turning them into a composite score. Depending on the available evidence, a candidate view can combine first-round poll testing, French-language Wikipedia attention, media visibility, campaign-agenda signals, fact-checking evidence, and a source-linked dossier.

![Candidates workspace — France 2027 Signal Lab](docs/assets/candidate-workspace.jpg)

The distinction between these measures is deliberate. Wikipedia attention is not electoral support. Media visibility is not voting intention. Poll evidence is not a prediction. FR27 lets the signals be read together while keeping their meanings separate.

## The media environment as a measured corpus

**Media Pulse** tracks activity inside the accepted FR27 election-coverage corpus: candidate visibility, topic activity, publisher contribution, recent coverage, and shifts between measured periods.

![Media Pulse — France 2027 Signal Lab](docs/assets/readme-media-pulse-en.jpg)

These are corpus measures, not claims about all French media or public opinion. Publisher and source-network context remains visible so aggregate signals can be interpreted against the collection universe that produced them.

## The substance of the campaign

The **Policy Issues** workspace follows substantive policy-topic evidence in accepted election coverage. It separates issue prominence, issue evolution, candidate-topic associations, and the source-linked material behind those aggregate signals.

![Policy Issues workspace — France 2027 Signal Lab](docs/assets/policy-issues-workspace.jpg)

A rise in observed issue activity means that a topic has become more prominent in the measured corpus. It does not mean voters have become more concerned about it, and a candidate-topic association does not imply endorsement, ownership, or ideological position.

FR27 separately tracks **Campaign Agenda** themes such as candidacies, endorsements, primaries, party strategy, campaign rules, political positioning, legal eligibility, and race narratives.

## Forward monitoring: campaign events

The **Campaign Events** workspace organizes source-supported scheduling evidence into a common calendar. It covers qualifying activity such as meetings, rallies, visits, debates, campaign launches, scheduled media appearances, press events, conventions, and relevant institutional milestones.

![Campaign Events workspace — France 2027 Signal Lab](docs/assets/campaign-events-workspace.jpg)

Event records can retain participants, type, date, time precision, location, organizer, source provenance, verification state, and status history. **Schedule Watch** records validated additions, confirmations, postponements, cancellations, and other meaningful changes.

Ambiguous scheduling information is not silently promoted into a confirmed event, and missing time precision is not invented.

## Research design

FR27's methodology is built around a few hard constraints.

**Poll events are atomic.** A first-round poll retains its pollster, fieldwork dates, round, hypothesis, complete candidate configuration, reported values, and source provenance.

**Configurations matter.** Poll observations are treated as comparable only when their scenario structure supports comparison. Incompatible candidate configurations are not silently merged into one trend.

**Missing evidence stays missing.** Unavailable, partial, ambiguous, or unresolved information is not converted into a false zero, estimate, or apparently complete result.

**Corpus-based measures are labelled as corpus-based.** Media visibility and agenda measures describe activity inside the accepted FR27 source corpus. Wikipedia Attention measures views of French-language Wikipedia articles; it is not a sentiment, approval, support, or voting-intention measure.

**Runoff evidence stays empirical.** FR27 distinguishes pairings that pollsters have actually tested from pairings that have not been tested. It does not manufacture second-round results for hypothetical combinations.

**No synthetic race score.** FR27 publishes no house polling average, forecast, win probability, composite momentum score, ideological score, sentiment score, or voting advice. The absence of a prediction layer is a design choice: the product is intended to make the underlying evidence easier to inspect, not to replace it with a proprietary answer.

When evidence cannot be parsed, reconciled, classified, dated, or attributed with sufficient confidence, FR27 prefers an explicit unresolved or unavailable state over false certainty.

Detailed definitions and limitations are documented in [`docs/METHODOLOGY.md`](docs/METHODOLOGY.md).

## From source to signal

FR27 is designed so that a derived signal does not erase the evidence chain that produced it.

```text
Public and first-party sources
        ↓
Collection and source-specific parsing
        ↓
Normalization, classification and deterministic identity
        ↓
Executable data contracts and validation
        ↓
Versioned publication artifacts
        ↓
Derived histories and candidate / race signals
        ↓
Publication manifest and integration checks
        ↓
Public dashboard
```

A published poll remains third-party polling evidence. A media-visibility share remains a derived measure over an accepted coverage corpus. A fact-check rating remains the publisher's judgment. A campaign-event record retains its source and evidence status. FR27 adds structure, comparability, provenance, and derived organization without changing the substantive meaning of the underlying evidence.

See [`docs/DATA_AND_PROVENANCE.md`](docs/DATA_AND_PROVENANCE.md) for publication lanes, source classes, freshness, provenance, and evidence boundaries.

## Automated publication, inspectable output

The public interface is deliberately static and inspectable, but the system behind it is not a hand-maintained webpage.

Python collectors and builders ingest, normalize, classify, validate, and derive publication data. Dedicated GitHub Actions workflows refresh major live evidence lanes including election news, polling, candidate attention, candidacy status, and claims. Other controlled datasets are rebuilt and validated from their authoritative inputs as their evidence changes.

Production updates are designed to fail closed: candidate output is validated before promotion, dependent artifacts are rebuilt in a controlled order, publication state is checked through `publication_manifest.json`, source health is tracked separately from political evidence, and the last valid published state can be preserved when a replacement fails its contract.

The media collection architecture uses a broad configured network of publisher routes, direct feeds, discovery paths, and other public sources. Current source-network counts, lane freshness, validation state, warnings, and publication metadata are exposed through the publication manifest and the **Source Network** interface rather than frozen into promotional numbers here.

Implementation details are documented in [`docs/ARCHITECTURE.md`](docs/ARCHITECTURE.md) and [`docs/OPERATIONS.md`](docs/OPERATIONS.md).

## Documentation

- [`docs/PRODUCT_GUIDE.md`](docs/PRODUCT_GUIDE.md) — product map and guidance for reading the dashboard.
- [`docs/METHODOLOGY.md`](docs/METHODOLOGY.md) — research scope, measurement semantics, classifications, comparability, and limitations.
- [`docs/DATA_AND_PROVENANCE.md`](docs/DATA_AND_PROVENANCE.md) — publication lanes, source provenance, freshness, and evidence boundaries.
- [`docs/ARCHITECTURE.md`](docs/ARCHITECTURE.md) — collectors, builders, contracts, artifacts, frontend integration, and publication architecture.
- [`docs/OPERATIONS.md`](docs/OPERATIONS.md) — production updates, validation, failure handling, publication integrity, and reproducibility.
- [`CONTRACT.md`](CONTRACT.md) — non-negotiable data and repository invariants.

## Independence

France 2027 Signal Lab is independently developed. It is not affiliated with, endorsed by, or operated on behalf of any candidate, political party, pollster, publisher, public authority, or other organization represented in its data.

FR27 tracks a developing election. Candidate status, source coverage, datasets, classifications, interfaces, and production methods may evolve as new evidence becomes available.

## Licensing and reuse

The repository is publicly accessible and **source-available**, but its software is not licensed as OSI open-source software.

Original FR27 software is licensed under the **PolyForm Noncommercial License 1.0.0**. Protected original non-software material is licensed under **Creative Commons Attribution-NonCommercial 4.0 International (CC BY-NC 4.0)** unless otherwise indicated. Third-party material remains governed by the rights, licences, source terms, and legal rules applicable to that material.

FR27 does not claim exclusive rights in independently obtainable facts merely because they appear in the project.

See [`LICENSE`](LICENSE), [`NOTICE`](NOTICE), [`CONTENT_LICENSE.md`](CONTENT_LICENSE.md), and [`THIRD_PARTY_NOTICES.md`](THIRD_PARTY_NOTICES.md) for the canonical licensing framework.

## Contributions and contact

Bug reports, factual or source corrections, reproducibility issues, and documentation corrections are welcome. FR27 does not currently accept unsolicited substantive external code or other copyrightable contributions. See [`CONTRIBUTING.md`](CONTRIBUTING.md).

For permissions or commercial licensing inquiries: **contact@france2027.app**
