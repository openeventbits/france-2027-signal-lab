# Commission notice 10381 turnout review

The false coverage first appeared in the [20 November polling update](https://github.com/openeventbits/france-2027-signal-lab/commit/949a8abb58ac5e6382303538e4e2fe61587b9b1f). It borrowed the event for the David Lisnard first-round scenario from the Sud Radio study.

## Official evidence

Follow the Commission index entries to the PDFs on the Commission host. The registry records the official HTTP redirects. The downloads used their HTTPS equivalents. All four PDF hashes matched the existing registry.

| Notice | Commissioner and fieldwork | Evidence | SHA-256 |
| --- | --- | --- | --- |
| [10381, Ifop](https://www.commission-des-sondages.fr/notices/files/notices/2026/novembre/10381-pres-participation-2nd-tour-jl-melenchon-m-le-pen-ifop-franc-tireur-18-novembre.pdf) | Franc-Tireur. Online 2–4 November 2026. 1,834 registered voters from 1,978 adults. | Printed pages 6–8 ask about plans to turn out on 18 April, willingness to turn out on 2 May under three hypothetical pairings, and reasons to abstain in a Mélenchon–Le Pen runoff. The weighted first-round estimate was 68% voting and 32% abstaining. Under Mélenchon–Le Pen it was 62% and 38%. The tables report participation, certainty and reasons for abstention. | `3c23709951d424e7d0e3848b335b8b3275472679ff72b21c803ec070436bf151` |
| [10392, Ifop-Fiducial](https://www.commission-des-sondages.fr/notices/files/notices/2026/novembre/10392-pres-iv-ifop-sud-radio-20-novembre.pdf) | Sud Radio. Online 2–4 November 2026. 1,834 registered voters from 1,978 adults. | Printed pages 7–10 ask which listed candidate respondents would be most likely to vote for if the first round took place the following Sunday. The four scenarios substitute Philippe, Retailleau, Lisnard or Attal. In the Lisnard scenario, Le Pen received 37%, Glucksmann 18%, Mélenchon 17% and Lisnard 14% of expressed votes. The nine candidate scores total 100%. | `176be3ccfd68b40df531e1812b28b9c5084dcb43c58ae36c687b84b930499c09` |
| [10382, YouGov](https://www.commission-des-sondages.fr/notices/files/notices/2026/novembre/10382-pres-iv-yougov-le-huffpost-19-novembre.pdf) | Le HuffPost. Online 12–17 November 2026. | The PDF contains candidate voting intentions. The production extractor returns no structured fieldwork window for this file. Coverage stays unresolved with `missing_structured_metadata`. | `b6f93bfa317307bb063f37b0baffe153d6fa4c48d0383c433a6cf6fe8b5de3a3` |
| [10393, Toluna Harris Interactive](https://www.commission-des-sondages.fr/notices/files/notices/2026/novembre/10393-pres-iv-vague-10-toluna-harris-interactive-23-novembre.pdf) | M6, RTL and L’Express. Online 18–19 November 2026. | The PDF contains candidate voting intentions. The identified dates have no exact published wave in this snapshot, so coverage stays unresolved with `no_exact_published_wave`. | `1c2100e959efa837f898e4b2963c14494a34b3bacef4fa7ec115c33d246e2619` |

Both Ifop files include turnout material. Printed page 6 of 10381 asks “envisagez-vous d’aller voter” and page 7 asks “iriez-vous voter”. The 10392 candidate tables ask “pour lequel des candidats suivants” respondents would be most likely to vote. Candidate names in a turnout scenario or in recalled 2022 weighting do not convert it into a candidate-choice question.

Notice 10381 is `excluded_non_voting` on the evidence of its inspected PDF. The registry retains the original identity, digest, and detected round mentions. Discovery treats round-only listings as requiring inspection, and the fallback question check requires candidate-choice language. Generic reconciliation blocks a legacy unsupported record when its inspection explicitly found no voting-intention language. Direct provenance and separately authenticated reviewed coverage retain their existing rules.

## Reproduce the artifact update

Save the [official index](https://www.commission-des-sondages.fr/notices/) as `index.html` and the four linked PDFs under their original filenames in a temporary evidence directory. Set `evidence_dir` to that directory and run the following from the repository root. It authenticates the source bytes, replays only 10381 through discovery, and checks the three comparison records against the existing polling observations.

```sh
python -B - "$evidence_dir" <<'PY'
from hashlib import sha256
from pathlib import Path
import json
import sys

from commission_notice_coverage import reconcile_commission_notices
from commission_notice_discovery import (
    INDEX_URL, FetchResult, atomic_write_registry, discover_registry,
    extract_document_text, confirm_document_eligibility, load_registry,
    parse_notice_index, validate_registry,
)
from test_commission_notice_discovery import index_html

evidence = Path(sys.argv[1])
registry_path = Path("commission_notice_registry.json")
registry = load_registry(registry_path)
before = {n["notice_id"]: n for n in registry["notices"]}
turnout_id = "commission:10381"
reviewed = {
    turnout_id: "3c23709951d424e7d0e3848b335b8b3275472679ff72b21c803ec070436bf151",
    "commission:10382": "b6f93bfa317307bb063f37b0baffe153d6fa4c48d0383c433a6cf6fe8b5de3a3",
    "commission:10392": "176be3ccfd68b40df531e1812b28b9c5084dcb43c58ae36c687b84b930499c09",
    "commission:10393": "1c2100e959efa837f898e4b2963c14494a34b3bacef4fa7ec115c33d246e2619",
}
official_index = {r["notice_id"]: r for r in parse_notice_index(
    (evidence / "index.html").read_bytes(),
)}
documents = {}
for notice_id, expected_digest in reviewed.items():
    old = before[notice_id]
    listing = official_index[notice_id]
    for field in ("listed_date", "category", "title", "institute", "commissioner", "listed_url"):
        assert listing[field] == old[field], (notice_id, field, listing[field], old[field])
    document_path = evidence / old["resolved_url"].rsplit("/", 1)[1]
    raw = document_path.read_bytes()
    assert sha256(raw).hexdigest() == expected_digest == old["content_sha256"], notice_id
    document = FetchResult(raw, old["resolved_url"], "application/pdf")
    eligible, _, reason = confirm_document_eligibility(extract_document_text(document))
    assert eligible == (notice_id != turnout_id), (notice_id, reason)
    documents[notice_id] = document

turnout = before[turnout_id]
scoped_index = index_html((turnout["listed_url"], turnout["title"])).replace(
    "Juillet 2026", "Novembre 2026",
).encode()

def replay_fetch(url, method):
    assert method == "GET"
    if url == INDEX_URL:
        return FetchResult(scoped_index, INDEX_URL, "text/html")
    assert url == turnout["listed_url"], url
    return documents[turnout_id]

replay = discover_registry(
    registry, fetch=replay_fetch, discovered_at=turnout["first_discovered_at"],
).registry
after = {n["notice_id"]: n for n in replay["notices"]}
assert before.keys() == after.keys()
changed = {key for key in before if before[key] != after[key]}
assert changed in ({turnout_id}, set()), changed
assert after[turnout_id]["classification"] == "excluded_non_voting"
assert after[turnout_id]["classification_reason"] == "document lacks voting-intention language"
assert {"parser", "survey_metadata", "coverage"}.isdisjoint(after[turnout_id])

first = json.loads(Path("polls.json").read_bytes())
second = json.loads(Path("second_round_polls.json").read_bytes())["events"]
scoped = {"notices": [dict(after[key]) for key in reviewed]}
reconcile_commission_notices(scoped, first, reviewed_events=first + second)
assert scoped["notices"] == [after[key] for key in reviewed]
validate_registry(replay)
print("Changed registry notices:", sorted(changed))
atomic_write_registry(registry_path, replay)
PY
python -B build_publication_manifest.py --published-at 2026-11-24T02:26:16Z
git diff --check
```

The manifest keeps the snapshot publication time and derives the new registry digest, snapshot ID and coverage counts. The nine current unresolved warnings include 10382 and 10393 and the original five historical warnings. The four 10392 events remain in the published corpus, including `4b5284f46605201037bb1050cb726b3343975317018cbe03ced78a1a37fafdf3`. The cutover contract records the two exact classifier and coverage hashes under this review, `FR27-COMMISSION-10381-TURNOUT`, with the original cutover hashes and earlier review history retained.
