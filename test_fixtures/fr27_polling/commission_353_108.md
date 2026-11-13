# Commission 10342 historical numerical positive control

`commission_353_108.json.gz` contains the complete parsed `polls.json` and
`second_round_polls.json` documents from accepted PR #334's merge,
[`fd7091515849dcc83bee56d620fdc938141ca5b8`](https://github.com/openeventbits/france-2027-signal-lab/commit/fd7091515849dcc83bee56d620fdc938141ca5b8).
It is an archival test input, not a replacement for current production data.

The two original blobs are byte-identical at the admission commit
`c7206e441494bcef0f6579376a9adbb3d7d63863`, review commit
`8ec679cb809d87d03144eaab7657d8ec29829d81`, and accepted merge above:

| File | Git blob | Original raw SHA-256 |
| --- | --- | --- |
| polls.json | `64b4a64293f9c2fda40c9724ddcba020161d15fa` | `9d4f83d459bfd2ce52c10fb79e4ff90122b62857ac9c689320aa1a712bfd46a4` |
| second_round_polls.json | `7724ee7f868ef1670a2f22b9b3d8dcb659bcb979` | `d89cc256bdd369cef2405fc33ea1c9b8ae9ce48946a686abbc1ac337336e8f3a` |

The accepted merge is an ancestor of current main. All 346 original first-round
and 108 runoff objects equal their complete objects at
`920e515ad73714a1b9a2d959e18fc1dc237ee7a6`, compared by event identity and every
field. The unchanged original canonical digests are:

- 346: `ca7e55432462366ca44d395a8a3d53d14312346af2e1138d3649de4408b9a730`.
- 108: `44993718ac263f57029767521739dc309289671e508f77dbbebc4a331419c811`.

The unchanged authenticator validates the seven previously approved additions
individually: three Cluster17 and four Ifop objects. The four Ifop objects were
also reconstructed in full from the committed `fr_mediawiki_240992329.json.gz`
source fixture (raw SHA-256
`e91ee2a93dea0a2bc3b41e0fd525c714c01c96552744d04bff573083b2e2de4c`),
through the existing parser and normal event constructor, and compared to the
accepted objects and their existing pins. No score, source URL, metadata or
identity was normalized for this fixture.

Reproduce by reading both Git blobs at the accepted merge, decoding their JSON,
and serializing the dictionary with those two filenames as keys using:
`json.dumps(payload, ensure_ascii=False, sort_keys=True, separators=(",", ":"), allow_nan=False).encode("utf-8")`.
Compress with `gzip.compress(raw, mtime=0)`. The loader authenticates the entire
uncompressed payload, including original document metadata, before invoking the
unchanged historical corpus authenticator. Its SHA-256 is:

`d33745280a060212c65168bbf89b322bde40462533aa5e093314caac31a1ab8c`.

This control does not select objects from current inputs. Later 10362 objects
and other later additions are not admitted; the full current corpus still fails
the historical authenticator. Current registry/manifest consistency is tested
separately. 10362 remains unsupported and unresolved, 10342 remains excluded,
and existing 10339 historical-evidence drift rejection remains in place.
