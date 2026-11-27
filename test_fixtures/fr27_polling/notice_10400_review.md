# Commission notice 10400 and the French runoff source

[Update Polls run 45898268903](https://github.com/openeventbits/france-2027-signal-lab/actions/runs/45898268903) checked out `6185d14ec` and failed before staging data. The [MediaWiki revision history](https://fr.wikipedia.org/w/api.php?action=query&pageids=15568607&prop=revisions&rvprop=ids%7Ctimestamp&rvstart=2026-11-26T21%3A39%3A37Z&rvlimit=5&format=json&formatversion=2) puts revision `241704906` at 19:44:19 UTC on 26 November 2026, before the 21:34–21:39 UTC fetch. The job did not log the revision ID. The pinned render reproduces its exact parser error on the unpatched code.

- `fr_mediawiki_241704906.json.gz` contains the unmodified [MediaWiki parse response](https://fr.wikipedia.org/w/api.php?action=parse&format=json&formatversion=2&oldid=241704906&prop=text%7Crevid%7Ctocdata) for page `15568607`. SHA-256 of the uncompressed response is `e76862e67512e915c040b1fe5940b06cce7738ca260a593c22ed3f61c4501a5e`.
- `notice_10400_previous_387_123.json.gz` freezes the 387 first-round and 123 runoff events from the last valid publication at `b01f5c907`. Its uncompressed SHA-256 is `71f9ef2046eabc889b18ac49efd41a4e72357e7d5d30e6f4cfbff73d39dc05c6`.

The Wikipedia family has one survey row and three timeline annotations. Its survey row and the other three OpinionWay runoff rows all link directly to [Commission notice 10400](https://www.commission-des-sondages.fr/notices/files/notices/2026/novembre/10400-pres-iv-vague-5-opinionway-26-novembre.pdf). The PDF SHA-256 is `0b74da87d845aa1320aacc32e455cf74b7a9e28b01b0c1401647ee29e370d943`. Pages 2–3 identify OpinionWay for CNews, fieldwork on 25–26 November 2026, and 912 registered voters. Pages 13–16 confirm the published columns below. The Wikipedia rows spell the pollster `OpinonWay`. The correction to `OpinionWay` is scoped to rows that match the notice.

| Runoff | Published scores | No voting intention | New source locator | Event ID |
| --- | --- | --- | --- | --- |
| Philippe–Le Pen | 41–59 | 29% | `FR-R4r1` | `ab8f43fbb5436da370e6f2f9421e199d5f22f7b4fa4cfda69e51e72b1fcf3dbd` |
| Mélenchon–Le Pen | 31–69 | 33% | `FR-R3r1` | `49bc30a98a9d4d5d55c14f3d3ff35b9f29b1bdb31552ca5d311ffaa96c04e25e` |
| Glucksmann–Le Pen | 42–58 | 25% | `FR-R2r1` | `fae9a4da1e518bfa8b84fd4ffe73e1d127ce64837933f19f290c2032d62596e6` |
| Lisnard–Le Pen | 45–55 | 33% | `FR-POST-LISNARD-LE-PENr1` | `79b589c857b147047c5fb742b61abfbc60d96cb8c393a6202d471abfe72b1fda` |

The no-intention percentages are outside the candidate score totals. On page 12, Bouamrane's published first-round score is `<1%`. The captured row preserves that censoring, so the existing first-round parser excludes it. Compared with pre-wave revision `241633669`, the capture adds four runoff facts and one censored first-round row. A first-round column rearrangement changes candidate order without changing accepted facts. Five YouGov runoff links and one Harris runoff link changed to Commission notices 10382 and 10393. Replay retains all 510 previously published events byte-for-byte at the object level, including their source provenance and historical locators.

A scheduled-mode replay using the pinned MediaWiki response and real Commission discovery wrote only temporary outputs. It added four runoffs and zero first-round observations. Validation and staging on disposable copies passed, and applying the same fetched files a second time was a no-op. Commission discovery confirmed notice 10400 but left first-round coverage unresolved because no supported official parser handles the censored ballot.

The notice regressions run in `test_poll_migration.FrozenFixtureTests`. They verify exact scores, sample and dates, the four new event IDs, published-object retention, deterministic replay, and fail-closed source mutations.

Local validation passed all 489 tests in the exact Update Polls contract selection, with zero skips, plus five targeted historical and drift checks. The changed-file audit and git diff --check passed.
