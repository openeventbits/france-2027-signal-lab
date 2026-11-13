WIP / NO-MERGE — preservation and review for the ASUS handoff only.

Validated base: `caada6984cdb4719ac2cab5310c4d27b5ac7d093`. Before push, main advanced to `b4f737c0ba577e3225b3cc8b1c7d9b1672340759` through two automated data-only refreshes (Claims and Candidate Attention). None overlaps this fix's files. This branch deliberately retains the tested base; it has not been rebased or revalidated against that newer input state. No additional broad test cycle was started for the handoff.

English polling labels retained a French decimal comma in the lower range bound. The nested substitution now converts digit-to-digit commas only inside the existing recognized compositional-label branch.

Exactly two files: `build_candidate_reference.py`, `test_candidate_reference.py`. Regression coverage adds integer/fractional bounds, singular/plural labels, bounded translation, and unchanged French rendering/projection. No polling inputs, evidence, schemas, routes, historical expectations or publication artifacts change.

Local Windows / Python 3.13.5 validation:
- Complete Candidate production selection: **591 tests, OK** (588 original + 3 new).
- Lifecycle/registry/orchestration and Agenda/Issue contracts: **116 tests, OK**.
- Complete generation/check chain passed. Same-date comparison: 139/143 artifacts identical; only four English polling labels change. All 47 data JSON and 48 French HTML artifacts remain identical.

**Remaining blocker:** the independent Paris-midnight defect still reproduces: full-family check passes immediately before midnight and rejects Anasse's data JSON immediately afterward. No code or workflow pin from PR #339 was imported. Exact-source hosted Linux/Python 3.12 validation and current-main compatibility remain pending. This is not a claim of a green production workflow.

Commit: `a8af897c70dff2ca5ea76ad6951457a07b59ca32`.

[Consolidated handoff, raw evidence and Windows resume commands](https://github.com/openeventbits/france-2027-signal-lab/blob/codex/recovery-handoff-2026-11-13/docs/production-recovery/2026-11-13/HANDOFF.md). Do not merge, dispatch production workflows, or publish.