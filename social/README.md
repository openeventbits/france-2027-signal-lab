# FR27 → X publisher

This directory contains the deterministic French X publishing lane for France 2027 Signal Lab.

## What it publishes

- `updates`: newly detected Campaign / Fact-check / Legal `recent_changes.json` developments as headline + direct publisher URL, and newly added future `campaign_events.json` entries as event title + date + source URL. Google News RSS wrappers are decoded before posting; an unresolved wrapper is never posted. Near-duplicate coverage of the same development is collapsed conservatively. No screenshot and no generative rewriting. Polling and runoff changes are excluded.
- `media`: one daily screenshot of the Media Pulse overview. Its caption deterministically surfaces the three largest comparable mention-rate changes visible in the panel.
- `agenda`: one daily screenshot of the Agenda Evolution panel. Its caption deterministically surfaces the three largest complete-week movements visible in the panel.
- `issues`: one daily screenshot of the Issues Evolution panel. Its caption deterministically surfaces the three largest incidence movements visible in the panel.

Race-at-a-Glance, polling updates and runoff updates are deliberately excluded from this lane.

## Safety / idempotence

The lane has three independent safeguards:

1. A persistent state file on the `social-assets` branch records already-seen `recent_changes` and campaign-event IDs. The first manual `bootstrap` run snapshots everything that already exists, so historical items are not posted when automation is enabled.
2. The social layer conservatively clusters same-day/adjacent-day near-duplicate `recent_changes` records. In addition to lexical similarity, a small allowlist of one-off candidate-status action groups (such as candidacy launch, withdrawal, or suspension) can collapse differently worded coverage when the same candidate and time window match. If an equivalent development already exists in the baseline/seen set, later duplicate coverage does not resurrect it as a new X post. Separate endorsements/events are kept separate.
3. Before publishing, Buffer is queried for recent sent/scheduled text. Exact duplicates are skipped. This also protects against a successful X post followed by a failed state-file commit.

A scheduled update run publishes at most four new items, leaving any remaining unseen items for the next 30-minute run. The entire scheduled workflow is inert until the repository variable `FR27_SOCIAL_ENABLED` is exactly `true`.

## Buffer configuration

Create a Buffer personal API key and connect the FR27 X account. Configure:

GitHub secret:

- `BUFFER_API_KEY`

GitHub repository variables:

- `BUFFER_ORGANIZATION_ID`
- `BUFFER_X_CHANNEL_ID`
- `FR27_SOCIAL_ENABLED` — leave unset/false during testing, then set to `true`

To discover the Buffer organization/channel IDs, run the workflow manually in `buffer-info` mode after adding `BUFFER_API_KEY`.

## Activation order

1. Merge the publishing PR while `FR27_SOCIAL_ENABLED` is unset/false.
2. Connect X in Buffer and add `BUFFER_API_KEY`.
3. Run `buffer-info` to obtain the organization and X channel IDs; store them as repository variables.
4. Run `bootstrap`. This writes the current `recent_changes` and event IDs into `social/x/state.json` on the `social-assets` branch without posting anything.
5. Before committing, run `python -B social/social_publish.py preview` to inspect exact current Évolutions and event text samples.
6. Run `media`, `agenda`, and `issues` manually with `publish=false`; inspect both the uploaded screenshots and extracted metric JSON. The dry-run log prints the exact caption that would accompany each screenshot.
7. Run `updates` manually with `publish=false`; inspect the candidate posts.
8. Only then set `FR27_SOCIAL_ENABLED=true`.

## Schedules (Europe/Paris)

- update scan: 07:17–23:47, every 30 minutes
- media visual: 12:13
- agenda visual: 15:07
- issues visual: 17:37

The non-round minutes reduce exposure to top-of-hour GitHub scheduled-workflow congestion.

## Screenshot handling

Playwright renders the production French site in a fixed `1707 × 932` virtual viewport. Physical laptop dimensions are irrelevant. Agenda and Issues capture only the evolution panel; Media captures the overview panel. All three captures isolate the target DOM so fixed/sticky dashboard chrome cannot paint over the exported image. The Media capture widens the actual Media Pulse parent, forces six candidate rows visible, hides the capture-only CTA, and lets the overview grow to its natural height. Agenda/Issues use a retrying stable-element capture because their analytical workspace can be replaced asynchronously while its data contracts settle. The capture waits for real data rows rather than merely waiting for the container to exist.

Published screenshots are written to the `social-assets` branch and exposed through a `raw.githubusercontent.com` URL for Buffer to fetch. Manual visual runs default to dry-run mode and upload the screenshot as a short-lived GitHub Actions artifact instead of publishing it.

## Google News URL resolution

Some FR27 discovery records originate from Google News RSS and therefore contain `news.google.com/rss/articles/...` wrapper URLs. X posts must link to the publisher, not to the wrapper. The social lane pins `googlenewsdecoder==0.2.1` (MIT) in `social/requirements.txt`, decodes wrappers at publication/preview time, and fails closed for any individual URL it cannot resolve. Direct publisher URLs pass through unchanged.
