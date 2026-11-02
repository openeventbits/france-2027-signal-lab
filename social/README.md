# Manual research and dashboard capture

The dashboard's published data and shared metric contracts support source-backed
research and manually written posts. No automated delivery, queue, scheduler or
publication-state manager is provided here.

## Analytical authorities

- `coverage_metric_contract.py` exposes `build_issue_metric_snapshot` and
  `build_agenda_metric_snapshot`, with explicit current/prior dates, numerators,
  denominators, raw/displayed shares, signed displayed differences, bilingual
  labels, canonical URLs and interpretation boundaries. Use `complete_day` or
  `complete_week`; weekly windows are complete Monday-Sunday UTC weeks.
- `issue_page_contract.py` and `agenda_page_contract.py` own the source-day
  calculations used by dashboard pages. Issues are multilabel incidence among
  accepted relevant-news publisher-days; Agenda is composition among classified
  campaign-topic source-days. These quantities must not be ranked against one
  another as if they had the same denominator.
- `candidate_visibility_history.json` retains daily record counts and lane
  denominators. `candidate_visibility_history_contract.py` validates it, and
  `build_candidate_visibility_history.py` remains its producer. General visibility
  and campaign attention have separate denominators. Published current Media
  Pulse also remains in `news_wire.json` and `candidate_signals.json`.
- `news_wire.json`, `recent_changes.json`, `campaign_events.json` and the dossier
  pages provide source links for checking observations before writing.

For example, run this read-only command from the repository root to inspect an
Issues comparison (substitute `build_agenda_metric_snapshot` and
`agenda_coverage_history.json` for Campaign Agenda):

```sh
python -B -c "import json; from pathlib import Path; from dataclasses import asdict; from coverage_metric_contract import build_issue_metric_snapshot; print(json.dumps(asdict(build_issue_metric_snapshot(json.loads(Path('issue_coverage_history.json').read_text(encoding='utf-8')), window_mode='complete_week')), ensure_ascii=False, indent=2))"
```

Use the supplied denominators and semantic boundaries. A zero observation is not
missing evidence; an unavailable comparison is not zero. Complete calendar days
do not imply exhaustive publisher coverage. Historical source snapshots are
preserved by their existing builders and publication contracts.

## Optional publisher URL lookup

The standalone `tools/resolve_source_urls.py` preserves the original publisher
URL lookup for manual source checking. Direct publisher URLs need no extra
package. For Google News links, install its optional research dependencies:

```sh
python -m pip install -r tools/research-requirements.txt
python -B tools/resolve_source_urls.py https://publisher.example/article
```

Pass Google News URLs from the evidence when a lookup is wanted. Only those
lookups may contact the public decoder/network. The command prints a JSON mapping
and leaves news evidence, publication records and account state untouched.
Unresolved Google News URLs are omitted. Inspect the original publisher page
before citing dates or claims; URL lookup supplies navigation, not authentication
of article content. No production workflow installs these optional packages or
runs this utility.

## Optional panel capture

`capture_social_panel.py` is a standalone manual utility. It captures an existing
Media Pulse, Agenda or Issues panel and can export metrics from the same stable
render. It has no delivery client, credentials, scheduling, post selection or
publication state.

Install optional capture dependencies separately from production workflows:

```sh
python -m pip install playwright
python -m playwright install chromium
python -B social/capture_social_panel.py --kind issues --base-url http://localhost:8000 --output _trace_output/issues.png --metrics-output _trace_output/issues-metrics.json
```

Run a local HTTP server first, or explicitly choose a published site with
`--base-url`. The utility only reads that site and writes the requested capture
files. Keep generated research output outside versioned evidence directories.

## Retirement and historical records

The automated FR27-to-X publisher has been retired from this checkout. Historical
publishing records and the separate `social-assets` Git branch remain intact.
No external credentials, scheduled posts, existing posts or account settings
were changed by the local removal. See
[`docs/X_PUBLISHER_REMOVAL_2026-11-02.md`](../docs/X_PUBLISHER_REMOVAL_2026-11-02.md)
for the inventory, validation and separately authorized external cleanup.
