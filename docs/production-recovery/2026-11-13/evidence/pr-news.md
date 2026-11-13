WIP / NO-MERGE — preservation and review for the ASUS handoff only.

Validated base: `caada6984cdb4719ac2cab5310c4d27b5ac7d093`. Before push, main advanced to `b4f737c0ba577e3225b3cc8b1c7d9b1672340759` through two automated data-only refreshes (Claims and Candidate Attention). None overlaps this fix's files. This branch deliberately retains the tested base; it has not been rebased or revalidated against that newer input state. No additional broad test cycle was started for the handoff.

The real snapshot validates at 01:59:59.882576 UTC with 22 publisher-site feeds due. The test advances its timestamp one second across 02:00 UTC, where 35 feeds are due, but kept the old counters. This is demonstrated fixture inconsistency; publisher policy/configuration and the production validator are unchanged.

Exactly one file: `test_live_projections.py`. Synthetic due counters now follow their timestamp. Publisher-site successes are zeroed and old site successes removed from the total; no publisher success is fabricated. Existing semantic-change, no-op, inventory, stale-repair and failure-atomicity assertions remain. No classifier, Architecture-B oracle, production input or artifact changes.

Local Windows / Python 3.13.5 validation:
- Complete News production selection: **474 tests, OK** (473 original + 1 new).
- Additional Agenda page contracts: **78 tests, OK**.
- Executed no-op: zero published-file changes. Source-status change: Wire + Agenda/Issue live projections change. Invalid projection: all nine files unchanged.

**Failing cross-family gate:** 161 tests, **5 failures**. All five reproduce on unchanged authenticated main with identical assertions: four Issue static-render/artifact contracts and `test_policy_agenda_frontend.PolicyAgendaFrontendTests.test_poll_compare_is_not_a_workspace`. Expectations and artifacts were not changed to conceal them. Preserve these counterexamples and obtain separate scope/disposition; exact-source hosted validation and current-main compatibility remain pending.

Commit: `dcd8c2a0700fd04165b5dc7c7667bcce5bafabab`.

[Consolidated handoff, raw evidence and Windows resume commands](https://github.com/openeventbits/france-2027-signal-lab/blob/codex/recovery-handoff-2026-11-13/docs/production-recovery/2026-11-13/HANDOFF.md). Do not merge, dispatch production workflows, or publish.