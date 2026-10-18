# Elabe configuration 5: reviewed Commission source link

## Decision and scope

This is a source-equivalent link refresh, not a new survey or a factual correction.
Accept only the exact Commission notice URL for the exact reviewed `FR-T0R5` incoming
row, from Wikipedia revision **240485523** onward. Every other field must equal the
existing reviewed row, including its sample scope and candidate ordering. Later
page revisions may replay that identical row; unrelated rows, prior revisions and
near matches receive no provenance exception.

Keep the canonical event ID
`63aecb7f3bd59f50845e47dc628ed7d480330d1a028228561ad2cc6a3bb1afb0`,
the original stored Elabe source URL, and its existing `supersedes_event_id`.
Do not calculate a replacement event ID from the Commission URL or rewrite a
published event's source. The incomplete predecessor remains absent.

## Independently verified primary evidence

The [official listing](https://www.commission-des-sondages.fr/notices/) lists
`10324 Pres IV ELABE 17 octobre` and links to
[entry 2339](https://www.commission-des-sondages.fr/notices/medias/fichiers/add/2339).
Following that entry returns the identical bytes as the direct
[Commission notice 10324](https://www.commission-des-sondages.fr/notices/files/notices/2026/octobre/10324-pres-iv-elabe-17-octobre.pdf).
The [original Elabe report](https://elabe.fr/fichier-pdf/13329-les-francais-et-lelection-presidentielle-2027/)
is independent corroboration. Both PDFs were retrieved and their relevant pages
rendered and visually reviewed on October 18, 2026. No PDF fetch is needed by tests.

| Survey field | Commission notice | Elabe report |
|---|---|---|
| Pollster / sponsors | Elabe / BFMTV, La Tribune Dimanche, p1 | Same, p2 |
| Fieldwork / collection | October 14-16, 2026 / online, p1 and p6 | Same, p2 |
| Adults / registered voters | 1701 / 1553, p1 and p6 | Same, p2 |
| Configuration | Q7, fifth of Q3-Q8, p3; fifth results table, p8 | Configuration 5, p7 and p18 |
| Voting denominator | Expressed intentions among registered likely voters, p5 | Likelihood 8-10, expressed intentions, p18 |
| No expressed intention | 11%, p8 | 11%, p18 |

The stored sample remains **1701 / reported**. Neither the URL update nor the
1553 registered-voter subgroup authorizes a sample correction.

All eleven percentages were extracted independently from each PDF and compared
with the reviewed row:

| Candidate | Percentage |
|---|---:|
| Nathalie Arthaud | 0.5 |
| Jean-Luc Melenchon | 15.5 |
| Fabien Roussel | 1.5 |
| Marine Tondelier | 2.5 |
| Raphael Glucksmann | 15.5 |
| Gabriel Attal | 4.5 |
| Edouard Philippe | 13.5 |
| Bruno Retailleau | 7.5 |
| Nicolas Dupont-Aignan | 3 |
| Marine Le Pen | 32.5 |
| Eric Zemmour | 3.5 |

Total: 100%. The questionnaire and results distinguish this from the other five
configurations; configuration 5 includes both Attal and Philippe.

SHA-256:

- Commission PDF: `a8a95533cad304be016080af5960ec928c8a6d4c49089e6c11b851feb4f235d8`
- Elabe PDF: `edbb125fd84f90b26fe6d98e8e42563ca0e876fb46804e23937e99d2e1dd8f99`
- Frozen revision-240485606 JSON, UTF-8/LF: `b1f8478756a50f29302a19596e3538cfbfd501a4c3a484c8d3f015bd40ebf3de`

The offline evidence metadata is `test_fixtures/fr27_polling/elabe_10324_source_review.json`.

## Exact Wikipedia edit and complete row comparison

The actual first-round link edit is **240485523**, timestamp 2026-10-18 12:35:17 UTC,
comment `Lien commission des sondages`; its parent is **240482337**. Comparing their
parsed `FR-T0R5` rows changes exactly one field:

- `source_url`: original Elabe URL -> direct HTTPS Commission PDF URL.

Unchanged: `source_locator`, `round`, `pollster`, `fieldwork_start`, `fieldwork_end`,
`sample_size`, `sample_scope`, and the complete ordered `candidates` list (all names
and percentages). The previous reviewed expansion revision **240470913** agrees
with that parent row. Revision **240485606** (parent 240485523, 12:38:48 UTC)
already contains the first-round source refresh; it is the frozen full-page
regression fixture. A later live snapshot, **240490172**, has the same Elabe row.
The other two reviewed candidate expansions remain exact matches.

The full page also has independent additions and edits outside this row; this
acceptance neither normalizes nor approves those changes. They continue through
the existing parser and reconciliation guards.

## Guard trace and retained protections

1. `parse_french_frozen_fixture` preserves the incoming notice URL as evidence.
2. `_assert_reviewed_post_audit_semantics` and its
   `REVIEWED_ACCEPTED_SOURCE_REFRESHES` set cover the older audit corpus. Their
   Cluster17 refresh is not a generic alias mechanism for this later Elabe row.
   Neither that set nor rejected-row refreshes change here.
3. `reconcile_first_round_corrections` remains unchanged. The expansion-specific
   exact-row guard was the failure point, even when the canonical successor was
   already published.
4. `reconcile_reviewed_candidate_expansions` now accepts one explicit old/new URL
   pair after the verified revision boundary and only when every other incoming
   field is identical. Its registry, old/new identity, canonical construction,
   historical-facts and mixed-identity checks remain in force. Canonical creation
   still uses the original reviewed row and original source URL.
5. Full reconciliation retains the event through its exact factual index. Review
   anchor, unregistered candidate expansion, historical retention, duplicate and
   runoff guards are unchanged. The fetch integration still validates all reported
   canonical and superseded IDs.

Tests cover both sources, the real full-page snapshot, exact revision boundaries,
deterministic and idempotent replay, complete historical record retention,
unchanged existing runoffs, and rejection of altered facts, sample/scope, locator,
round, candidate order, unknown/nearby/HTTP/query URLs, other expansions, missing or
mixed identities, duplicate incoming rows, and rewritten stored successor sources.

No published polling dataset, workflow configuration, general reconciliation rule
or reviewed registry is edited. The supplied Actions run URL returned 404 through
the GitHub API during investigation; the unmodified code independently reproduced
the FR-T0R5 error against the exact frozen and saved live source revisions.
