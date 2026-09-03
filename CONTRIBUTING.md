# Contributing to France 2027 Signal Lab

Thank you for your interest in **France 2027 Signal Lab (FR27)**.

FR27 is publicly accessible and source-available, but it is not currently operated as an open-contribution software project.

The repository is maintained under a deliberately controlled contribution model in order to preserve methodological consistency, provenance, production safety, and a clear rights chain.

## What is welcome

Reports and corrections are welcome, especially when they concern:

- factual errors;
- broken or incorrect source links;
- missing source provenance;
- polling-source discrepancies;
- candidate-status discrepancies;
- campaign-event evidence;
- incorrect or ambiguous interface wording;
- accessibility problems;
- reproducible software defects;
- production or data-quality problems; and
- documentation errors.

When reporting a factual or data issue, please include the strongest available source.

Primary, official, or first-party evidence is especially useful where appropriate.

## Issues

Opening a GitHub issue is the preferred way to report a problem that can safely be discussed publicly.

A useful report should identify:

- the affected dashboard area or file;
- what appears to be wrong;
- what you expected instead;
- a source or reproduction path where relevant; and
- the date on which you observed the problem.

Please distinguish factual corrections from suggestions for new features.

FR27 intentionally favors completion, clarity, and maintenance discipline over continuous feature expansion.

## Pull requests

Please **do not submit substantive pull requests unless invited or unless the change has been discussed with the maintainer in advance**.

This includes substantial changes to:

- application code;
- data pipelines;
- data contracts;
- automated workflows;
- research methodology;
- candidate classification;
- polling logic;
- event logic;
- media classification;
- generated datasets;
- interface architecture; and
- licensing or legal files.

Unsolicited substantive pull requests may be closed without review.

This policy is not a judgment on the quality of external work. It exists to keep production responsibility, methodology, and rights ownership clear.

## Small corrections and suggestions

For small corrections, opening an issue is preferred to submitting a pull request.

Examples include:

- an obvious typo;
- a broken internal documentation link;
- a clearly incorrect factual label supported by an authoritative source; or
- another narrowly bounded correction that does not change methodology, architecture, or licensing.

The maintainer may implement a reported correction independently.

External pull-request content is not incorporated merely because the proposed change is small. If the maintainer wishes to incorporate copyrightable material from an external contribution, the contribution must be invited and the applicable rights terms must be agreed before incorporation.

## Do not submit third-party material without permission

Do not submit material merely because it is publicly viewable elsewhere.

In particular, do not contribute:

- copied articles or substantial article text;
- photographs;
- logos or icons;
- proprietary datasets;
- paywalled material;
- copyrighted reports;
- source code from incompatible projects; or
- other third-party material unless you have the legal right to provide it for the intended use.

A URL identifying a source is generally preferable to copying the source material into the repository.

## Data and factual contributions

Facts themselves may be independently obtainable, but FR27 still requires traceable evidence for factual changes.

A proposed factual correction should therefore identify:

- the fact being corrected;
- the relevant candidate, poll, event, claim, or source where applicable;
- the supporting URL or public record;
- the date or time context where relevant; and
- why the current FR27 representation appears incorrect.

Do not infer missing values.

Do not convert uncertainty into precision that the source does not provide.

## Methodological changes

Methodological changes require explicit review before implementation.

Examples include changes to:

- candidate inclusion or status rules;
- poll comparability;
- missing-value treatment;
- campaign-topic classification;
- policy-topic classification;
- candidate-media associations;
- runoff interpretation;
- event-evidence rules;
- Wikipedia-attention semantics;
- fact-check associations; or
- Recent Changes eligibility.

A methodological change should explain the rule first.

Code should implement an agreed semantic decision rather than define the methodology accidentally.

See [`docs/METHODOLOGY.md`](docs/METHODOLOGY.md) and [`CONTRACT.md`](CONTRACT.md).

## Production and workflow changes

Production changes must follow the safety discipline documented in [`docs/OPERATIONS.md`](docs/OPERATIONS.md).

In particular, changes should preserve:

- bounded scope;
- appropriate assertion classification;
- deterministic contracts where applicable;
- validation before promotion;
- last-good behavior where applicable;
- exact generated-file scope;
- exact staged scope;
- publication-manifest integrity; and
- safe interaction with other production writers.

Do not weaken a contract merely to make a failing workflow pass.

## Generated files

Some repository files are generated from authoritative inputs or external evidence.

Do not manually edit a generated artifact when the correct fix belongs in:

- an authoritative input;
- a source registry;
- a parser;
- a normalization rule;
- a contract;
- a builder; or
- a production workflow.

A manual edit that will simply be overwritten by the next production run is not a durable correction.

## Tests

A change that affects behavior should normally include or update the test that protects that behavior.

Use the testing strategy appropriate to the assertion:

- frozen historical evidence can use frozen fixtures;
- semantic rules should prefer focused synthetic fixtures;
- dynamic current-production should use structural and relational invariants; and
- workflow-safety behavior should test the publication mechanism itself.

See [`docs/OPERATIONS.md`](docs/OPERATIONS.md).

## AI-generated contributions

The use of AI tools does not remove the contributor's responsibility for a submission.

Do not submit generated code, text, data, classifications, citations, or legal wording that you have not reviewed and cannot substantiate.

Any proposed contribution must satisfy the same evidence, provenance, rights, and correctness requirements regardless of how it was produced.

## Rights and licensing

The repository's public availability does not mean that all material is available for unrestricted reuse.

Before proposing a contribution, review:

- [`LICENSE`](LICENSE);
- [`NOTICE`](NOTICE);
- [`CONTENT_LICENSE.md`](CONTENT_LICENSE.md); and
- [`THIRD_PARTY_NOTICES.md`](THIRD_PARTY_NOTICES.md).

Third-party material retains its own applicable rights.

Submitting an issue, correction, suggestion, source reference, or unsolicited pull request does not by itself transfer copyright or other ownership rights to FR27.

FR27 does not intend to rely on an implied licence from unsolicited contribution material. If the maintainer invites a copyrightable contribution for incorporation into the repository, the applicable contribution and rights terms must be agreed expressly before that material is incorporated.

Because FR27 does not currently solicit substantive external contributions, contributors should not assume that a submitted pull request will be incorporated into the project.

## Security or sensitive reports

Do not post secrets, credentials, personal data, or other sensitive material in a public issue.

For a report that should not be public, contact:

`contact@france2027.app`

## Maintainer discretion

The maintainer may decline, defer, modify, or independently implement a suggested change.

A suggestion or pull request does not create an obligation to merge, publish, or preserve the proposed implementation.

This controlled contribution model may be revised in the future if the project's governance changes.