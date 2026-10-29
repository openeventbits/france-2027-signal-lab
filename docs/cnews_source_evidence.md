# Reviewed CNEWS source evidence

Notices 10319 and 10333 each publish one 13-candidate first-round table whose
`Publié` column contains strict `<1%` bounds. They are documentary tables, not
numerical polling observations. Their two numerical coverage gaps remain open.
The six existing runoff observations are separate and unchanged.

The reviewed Phase 2A/2B manifest supplies the candidate identities, literal
results, study identity and document references. This intake copies those rows
without numerical conversion. The original Commission PDFs were authenticated
against the manifest before preparation; no PDF, extraction program or external
cache path is shipped. Methodology and non-expression context reference pages
3–5 and 12 of those authenticated originals. The first-round expressed base for
10319 remains unverified; the 10333 base of 680 is distinct from its 731 certain
voters. The questionnaire's blank/invalid and abstention options are preserved
as contextual labels, without inventing candidate scores or numerical identities.

The institute browsing card's displayed period covers its combined numerical and
source-scenario entries. Numerical institute metrics, analytical periods and
candidate headline indicators continue to use numerical observations only.

## Review pins and boundaries

`poll_source_tables.json` extends the existing reviewed collection from three
tables to five. The individual records, hashes and numerical-page associations
for 10327, 10260 and unpublished 10264 remain unchanged. The explicit proposed
Phase 3A collection pin, subject to implementation review, is:

`2210c4943c4984099bf2c217433a8e4d4e0ed656052f5794c1c5c08c473c4737`

It replaces the three-record collection pin
`4ede22b9d7973257cedd2f76ff0edeb137ff43d8e67ca946800d7251d76eb526`.
The loader authenticates both collection and individual table hashes. No command
automatically updates a pin. New source-table IDs use the established
`fr27-source-table-v1:` prefix and a canonical SHA-256 envelope of notice ID,
PDF hash, page, published column, round and complete reviewed rows. These are
document identities, never event IDs. Existing source and historical event IDs
are not recomputed.

An operator can recheck the original bytes from an external evidence cache:

```sh
python -B poll_source_tables.py --evidence-dir /external/fr27-audit/evidence
```

The directory must contain original `10319.pdf` and `10333.pdf`. Missing files,
changed PDF bytes, changed reviewed rows or changed pins fail closed. This is
an explicit operator check, not an automatic fetch or extraction step. Ordinary
publication consumes authenticated, reviewed transcriptions without depending
on a private evidence cache. CI uses controlled document fixtures for byte
authentication tests and does not require the external originals.

## Publication

The existing page builder generates the four routes:

- `/sondages/documents/opinionway-cnews-10319/`
- `/en/sondages/documents/opinionway-cnews-10319/`
- `/sondages/documents/opinionway-cnews-10333/`
- `/en/sondages/documents/opinionway-cnews-10333/`

Only the explicit `standalone_pages` allowlist publishes documentary routes.
A later [10264 publication review](bonnal_10264_source_evidence.md) adds the authenticated Bonnal table to the same documentary mechanism; its numerical warning remains unresolved. `poll_pages_manifest.json` keeps
`pages`, `wave_count` and `page_count` numerical; `source_pages` and
`source_page_count` separately describe documentary pages. The route registry
uses kind `poll-source-evidence` in the polling family; the existing sitemap
builder consumes these registered routes without special extraction logic.
The hub static-link builder adds a separate `#source-evidence` section outside
the numerical directory and runtime analytics containers. Pages reuse the poll
detail shell, source-only card, header/footer and language navigation.

Normal build/check commands remain:

```sh
python -B build_poll_pages.py
python -B build_poll_hub_static_links.py
python -B build_route_registry.py --effective-date YYYY-MM-DD
python -B build_sitemaps.py
python -B build_poll_pages.py --check
python -B build_poll_hub_static_links.py --check
python -B build_route_registry.py --check
python -B build_sitemaps.py --check
python -B -m unittest -v test_poll_pages.CnewsSourcePublicationTests
```

The usual publication-manifest finalization follows route/sitemap generation.
This adds no scheduling, ingestion hooks or workflow changes. Publication can
rebuild the frozen documentary pages; it does not discover or import polls.
Numerical analytics do not consume this source collection. Bounded values lack an exact
`percent` and the whole table is excluded from numerical comparisons, including
when the exact subtotal is 100. The Phase 2B diagnostic and its historical pins
are unchanged: documentary publication does not turn either scenario into a
numerical match or authorize a new baseline attestation.

The public page states are `SOURCE_DOCUMENT_VERIFIED`,
`DOCUMENTARY_COVERAGE_PUBLISHED` and `NUMERICAL_OBSERVATION_ABSENT`. In local
review builds, “published” describes the generated public page representation;
deployment still requires separate review. The separate
[26 October reconciliation review](commission_notice_reconciliation_20261026.md)
rejects the false Commission 10319 association to PrésiTrack. Its first-round
numerical gap remains open; both documentary records and all runoffs are retained.

## Historical Phase 3B browsing projection

`build_poll_explorer.py` projects only the authenticated 10319 and 10333 records
into the additive `source_scenarios` read-model array. Original numerical
`waves`, `candidates`, `institutes`, metrics and event IDs retain their semantics.
A source scenario reuses its reviewed source-table ID and official notice ID;
it has no numerical `event_id`, `wave_id`, `scenarios` vector or scalar `score`.
All candidate values, including exact values, remain under typed `result`
objects. `analysis_eligible` is false for the whole source scenario.

The latest-polls, complete, institute and candidate browsing views combine the
two entry types chronologically. Static and JavaScript directories expose the
same source scenarios, commissioner/status and existing bilingual detail links.
Candidate browsing displays published literals, including Lisnard's 4% and 6%
and all three `<1%` rows, without treating them as numerical observations.
Counts distinguish numerical waves/scenarios from reviewed source scenarios.

Charts, ranges, comparisons, candidate picker/headline indicators and runoffs
continue to use numerical inputs exclusively. Documentary candidates outside
the active numerical picker can still be browsed; browsing does not add them
to a numerical comparison. Future analytical admission requires a separate
verified typed-score contract. No PDF is fetched or parsed by this projection,
and the source collection pin, source-page records and Phase 2B diagnostic are
unchanged. The two first-round numerical gaps remain open.
