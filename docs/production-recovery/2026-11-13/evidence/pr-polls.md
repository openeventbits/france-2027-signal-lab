WIP / NO-MERGE — preservation and review for the ASUS handoff only.

Validated base: `caada6984cdb4719ac2cab5310c4d27b5ac7d093`. Before push, main advanced to `b4f737c0ba577e3225b3cc8b1c7d9b1672340759` through two automated data-only refreshes (Claims and Candidate Attention). None overlaps this fix's files. This branch deliberately retains the tested base; it has not been rebased or revalidated against that newer input state. No additional broad test cycle was started for the handoff.

The historical-success method embedded a current-corpus negative control expecting the runoff guard. Approved additions expanded first round to 360 observations: the unchanged 90% guard now rejects 284 extracted rows against 316 before reaching runoff.

Exactly one file: `test_reviewed_cluster17_source_retention.py`. The original pinned 326/97 success assertions remain unchanged. Current-corpus rejection is tested separately for all three old snapshots; runoff rejection is independently tested using the approved runner's authenticated first-round scope. No production guard, historical corpus pin, source-retention decision, mutation expectation, polling value, normalization or Commission registry record changes.

Local Windows / Python 3.13.5 validation:
- Complete production selection: **480 tests, OK** (478 original + 2 new), including all three authenticated historical methods.
- Independent runoff scope probe passed for all three revisions.
- All original-review 349 first-round / 108 runoff objects retain typed content and relative order; all 11 later first-round additions are preserved.

**Incomplete:** the separately queued historical-runner mutation/publication/search expansion was stopped after the handoff instruction; its partial log is retained and is not green. Finish that command on ASUS, then obtain exact-source hosted Linux/Python 3.12 validation and revalidate current-main compatibility. Frozen Commission work is untouched.

Commit: `3f58a50434bbb70defad4bba69cf339be2924639`.

[Consolidated handoff, raw evidence and Windows resume commands](https://github.com/openeventbits/france-2027-signal-lab/blob/codex/recovery-handoff-2026-11-13/docs/production-recovery/2026-11-13/HANDOFF.md). Do not merge, dispatch production workflows, or publish.