# Reviewed study projection: Cluster17 / Politico, October 2026

`poll_study_bindings.json` binds exactly three immutable numerical observations
to one study, outside `polls.json`. It is authenticated by the complete canonical
JSON hash in `poll_studies.py`; each member has a complete event-object hash.
Any changed member, incomplete collection, duplicate member or additional event
colliding with the reviewed canonical study fails closed. No general institute
aliasing or ingestion change is introduced.

The original [Cluster17 / Politico PDF](https://cluster17.com/wp-content/uploads/2026/10/ITV-Politico-Octobre-C17.pdf)
has SHA-256 `f97e63a028f809d62db0d961a4a271ef38581dac2fda6c58ec36f8be35ac8448`.
Its methodology identifies fieldwork 19–22 October 2026 and sample 3,000;
the three first-round hypotheses appear on PDF pages 5 (H1), 9 (H2), 13 (H3).
Authenticate a local copy with `python -B poll_studies.py --authenticate-pdf PATH`.
The PDF is not fetched during builds.

| Documentary hypothesis | Immutable event ID | Canonical numeric anchor |
| --- | --- | --- |
| H2, p. 9 | `26e5f0ab3df1861400351a6794f56ca2e3b51099bd12941866aaae7d23d56fa6` | `#scenario-1` |
| H1, p. 5 | `2b452c95a3681f12d01f1d1524977e951d13da68ab124fb6d83db16ebfddcea6` | `#scenario-2` |
| H3, p. 13 | `335645e494e1d3665674719bd7406dc07f7f8f6fe960bba8cd2f0a2b468e773d` | `#scenario-3` |

The existing compact-label wave `wave-579f7297a9eba38c` remains canonical in both
languages. Its old `#scenario-1` continues to identify H2. Canonical order is
H2, H1, H3 so that the most-comparable-ballot selector's H2/H1 tie (10 comparable
candidates each; H3 has 0) retains H2 as default. The overall homepage default
remains the Ipsos study. Documentary H labels are retained separately from
numeric anchor positions. All three have additional `#scenario-EVENT_ID` anchors.

`wave-92ed602a62b416e0` remains a real compatibility page in French and English.
Its old `#scenario-1` links to H3 and `#scenario-2` links to H1, using the new
event anchors on the canonical page. Compatibility pages have canonical and
language alternates pointing to the combined study and `noindex,follow`.
They are recorded separately in the poll manifest and route registry, excluded
from canonical study counts, search routes and sitemaps.

The combined study uses the projected institute `Cluster17`. Every original raw
pollster label, source URL, scenario key, event ID and score stays unchanged.
Raw labels and documentary page references are also exposed on its scenario
cards. Python and the generated browser asset share the reviewed binding. The
browser additionally authenticates full canonical JSON after integral-number
normalization because JavaScript represents both JSON `100.0` and `100` as the
same number; the original Python object pins retain that type distinction.

Study counts decrease from 84 to 83; institute counts from 12 to 11. Scenario
counts stay 349. Thirteen candidate histories now contain one combined study;
nine lose one duplicate study observation. Ranges use only ballots where the
candidate is present; absence in default H2 produces `selected_score: null`,
never zero. No scores are averaged. Canonicalizing H1/H3's institute also makes
their previous-study comparison eligible for the existing Cluster17 exact-ballot
series when an earlier matching ballot exists. The previous-poll panel retains
its distinct latest-previous-study logic and pollster-change disclosure.

Regenerate `assets/poll-study-bindings.js` with `python -B poll_studies.py`; verify
with `--check`. Run `test_poll_studies.py` alongside the existing production,
homepage, explorer, page, candidate, route, search and publication contracts.
Any future member or document change requires a separate documentary review and
new explicit pins. The homepage's separate 101/102 completeness defect (Gate 2)
is deliberately unchanged.
