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
Bonnal 10264 stays a local, noindex preview. `poll_pages_manifest.json` keeps
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
No analytics builder reads this source collection. Bounded values lack an exact
`percent` and the whole table is excluded from numerical comparisons, including
when the exact subtotal is 100. The Phase 2B diagnostic and its historical pins
are unchanged: documentary publication does not turn either scenario into a
numerical match or authorize a new baseline attestation.

The public page states are `SOURCE_DOCUMENT_VERIFIED`,
`DOCUMENTARY_COVERAGE_PUBLISHED` and `NUMERICAL_OBSERVATION_ABSENT`. In local
review builds, “published” describes the generated public page representation;
deployment still requires separate review. The known false Commission 10319
association remains untouched and needs a separate reviewed correction.
